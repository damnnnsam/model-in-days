from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from engine.inputs import ModelInputs


@dataclass
class SimulationResult:
    days: np.ndarray
    # Customers
    new_customers_inbound: np.ndarray
    new_customers_outbound: np.ndarray
    new_customers_organic: np.ndarray
    new_customers_viral: np.ndarray
    new_customers_total: np.ndarray
    cumulative_customers: np.ndarray
    active_customers: np.ndarray
    churned_customers: np.ndarray
    renewed_customers: np.ndarray
    refunded_customers: np.ndarray
    # Revenue & cash
    revenue_new: np.ndarray  # booked revenue from new sales
    revenue_renewal: np.ndarray
    revenue_total: np.ndarray
    cash_collected_new: np.ndarray  # actual cash arriving (timing)
    cash_collected_renewal: np.ndarray
    cash_collected_total: np.ndarray
    # Costs
    cost_marketing: np.ndarray
    cost_sales: np.ndarray
    cost_fulfillment: np.ndarray
    cost_fixed: np.ndarray
    cost_transaction_fees: np.ndarray
    cost_interest: np.ndarray
    cost_refunds: np.ndarray
    cost_total: np.ndarray
    # P&L
    gross_profit: np.ndarray
    ebitda: np.ndarray
    ebit: np.ndarray
    net_income: np.ndarray
    free_cash_flow: np.ndarray
    cumulative_fcf: np.ndarray
    cash_balance: np.ndarray
    # Leads
    leads_inbound: np.ndarray
    leads_outbound: np.ndarray
    leads_organic: np.ndarray


def run_simulation(inp: ModelInputs) -> SimulationResult:
    T = inp.time_max
    days = np.arange(T)

    # ── Pre-compute daily lead generation rates (steady-state per day) ──

    # Inbound: media_spend/month → impressions → clicks → leads/day
    if inp.use_inbound and inp.cpm > 0:
        impressions_per_day = (inp.media_spend / inp.cpm) * 1000.0 / 30.0
        clicks_per_day = impressions_per_day * (inp.ctr / 100.0)
        leads_per_day_inbound = clicks_per_day * (inp.funnel_conversion_rate / 100.0)
    elif inp.use_inbound:
        leads_per_day_inbound = 0.0
    else:
        leads_per_day_inbound = 0.0

    # Outbound: SDRs × contacts/month × conversion → leads/day
    if inp.use_outbound:
        contacts_per_day = (inp.number_of_sdrs * inp.contacts_per_month) / 30.0
        leads_per_day_outbound = contacts_per_day * (inp.outbound_conversion_rate / 100.0)
    else:
        leads_per_day_outbound = 0.0

    # Organic: views/month × conversion → leads/day
    if inp.use_organic:
        leads_per_day_organic = (inp.organic_views_per_month / 30.0) * (inp.organic_view_to_lead_rate / 100.0)
    else:
        leads_per_day_organic = 0.0

    # ── Delay calculations ──
    # Total delay from impression to customer = time_to_market + time_to_sell
    delay_inbound = inp.time_to_market_inbound + inp.time_to_sell
    delay_outbound = inp.time_to_market_outbound + inp.time_to_sell
    delay_organic = inp.time_to_market_organic + inp.time_to_sell

    # ── Allocate arrays ──
    new_cust_inbound = np.zeros(T)
    new_cust_outbound = np.zeros(T)
    new_cust_organic = np.zeros(T)
    new_cust_viral = np.zeros(T)
    leads_inbound_arr = np.zeros(T)
    leads_outbound_arr = np.zeros(T)
    leads_organic_arr = np.zeros(T)

    # Fill daily leads (constant rate)
    leads_inbound_arr[:] = leads_per_day_inbound if inp.use_inbound else 0
    leads_outbound_arr[:] = leads_per_day_outbound if inp.use_outbound else 0
    leads_organic_arr[:] = leads_per_day_organic if inp.use_organic else 0

    # New customers = leads (delayed) × lead→customer conversion
    for d in range(T):
        lead_day_in = d - delay_inbound
        if lead_day_in >= 0 and inp.use_inbound:
            new_cust_inbound[d] = leads_inbound_arr[lead_day_in] * (inp.lead_conversion_rate_inbound / 100.0)

        lead_day_out = d - delay_outbound
        if lead_day_out >= 0 and inp.use_outbound:
            new_cust_outbound[d] = leads_outbound_arr[lead_day_out] * (inp.lead_conversion_rate_outbound / 100.0)

        lead_day_org = d - delay_organic
        if lead_day_org >= 0 and inp.use_organic:
            new_cust_organic[d] = leads_organic_arr[lead_day_org] * (inp.lead_to_customer_rate_organic / 100.0)

    new_cust_total = new_cust_inbound + new_cust_outbound + new_cust_organic  # viral added below

    # ── Churn, renewals, refunds tracking ──
    # Track cohorts: each day's new customers go through contract_length, then churn/renew
    active_customers = np.zeros(T)
    churned_cum = np.zeros(T)
    renewed_cum = np.zeros(T)
    refunded_cum = np.zeros(T)
    revenue_new = np.zeros(T)
    revenue_renewal = np.zeros(T)
    cash_collected_new = np.zeros(T)
    cash_collected_renewal = np.zeros(T)
    cost_refunds = np.zeros(T)
    cost_sales_new = np.zeros(T)
    cost_fulfill_new = np.zeros(T)
    cost_sales_renewal = np.zeros(T)
    cost_fulfill_renewal = np.zeros(T)
    cost_transaction = np.zeros(T)

    # We'll track "customer events" using arrays for when cohorts convert, churn, renew
    # Approach: accumulate fractional customers, process renewals via shifted arrays

    # For viral: we need active_customers computed before we can add viral
    # So we do two passes or compute viral inside the loop

    P = inp.price_of_offer
    RR = inp.realization_rate / 100.0
    c_s = inp.cost_to_sell / 100.0
    c_f = inp.cost_to_fulfill / 100.0
    t_c = inp.time_to_collect
    churn = inp.churn_rate / 100.0
    refund_r = inp.refund_rate / 100.0
    contract_len = max(inp.contract_length, 1)
    TF = inp.transaction_fee / 100.0

    p_ren = inp.price_of_renewal
    c_s_ren = inp.cost_to_sell_renewal / 100.0
    c_f_ren = inp.cost_to_fulfill_renewal / 100.0
    t_c_ren = inp.time_to_collect_renewal
    ren_of_ren = inp.renewal_rate_of_renewals / 100.0

    # Viral params
    viral_inv = inp.invites_per_customer
    viral_conv = inp.conversion_rate_per_invite / 100.0
    viral_delay = inp.viral_time + inp.time_to_sell
    viral_start = inp.viral_start
    c_s_viral = inp.cost_to_sell_viral / 100.0
    c_m_viral = inp.cost_to_market_viral / 100.0

    # Track new customer events per day (fractional)
    # and renewal events per day
    new_events = np.zeros(T)  # new customers arriving (all channels)
    renewal_events = np.zeros(T)  # renewals happening

    # Add initial customers at day 0
    initial_custs = float(inp.customer_count)

    # Build day-by-day
    cumulative_new = np.zeros(T)
    active = np.zeros(T)

    for d in range(T):
        # Viral contribution: based on active customers viral_delay days ago
        if inp.use_viral and d >= viral_start + viral_delay:
            source_day = d - viral_delay
            if source_day >= 0:
                active_at_source = active[source_day] if source_day > 0 else initial_custs
                # Each active customer sends invites spread over contract length
                viral_customers_today = active_at_source * (viral_inv / max(contract_len, 1)) * viral_conv
                new_cust_viral[d] = viral_customers_today

        day_new = new_cust_inbound[d] + new_cust_outbound[d] + new_cust_organic[d] + new_cust_viral[d]
        if d == 0:
            day_new += initial_custs

        new_events[d] = day_new

        # Revenue from new sales (booked on the day of sale)
        revenue_new[d] = day_new * P * RR

        # Cash collection: spread over time_to_collect
        if t_c > 0:
            daily_cash = (day_new * P * RR) / t_c
            end = min(d + t_c, T)
            cash_collected_new[d:end] += daily_cash
        else:
            cash_collected_new[d] += day_new * P * RR

        # Sales cost on new
        cost_sales_new[d] += day_new * P * c_s

        # Fulfillment cost on new (spread over contract)
        if contract_len > 0:
            daily_fulfill = (day_new * P * c_f) / contract_len
            end = min(d + contract_len, T)
            cost_fulfill_new[d:end] += daily_fulfill
        else:
            cost_fulfill_new[d] += day_new * P * c_f

        # Transaction fees on cash collected
        cost_transaction[d] += cash_collected_new[d] * TF

        # Refunds: customers acquired on day d may refund after refund_period
        refund_day = d + inp.refund_period
        if refund_day < T:
            refunded = day_new * refund_r
            refunded_cum[refund_day] += refunded
            cost_refunds[refund_day] += refunded * P * RR

        # Renewals: customers acquired on day d renew at d + contract_length
        renewal_day = d + contract_len
        if renewal_day < T and churn < 1.0:
            renewing = day_new * (1.0 - churn) * (1.0 - refund_r)
            renewal_events[renewal_day] += renewing

        # Process renewals happening today
        if renewal_events[d] > 0:
            ren_count = renewal_events[d]
            renewed_cum[d] += ren_count

            revenue_renewal[d] += ren_count * p_ren * RR
            cost_sales_renewal[d] += ren_count * p_ren * c_s_ren
            cost_fulfill_renewal[d] += ren_count * p_ren * c_f_ren

            # Cash collection for renewals
            if t_c_ren > 0:
                daily_cash_ren = (ren_count * p_ren * RR) / t_c_ren
                end_ren = min(d + t_c_ren, T)
                cash_collected_renewal[d:end_ren] += daily_cash_ren
            else:
                cash_collected_renewal[d] += ren_count * p_ren * RR

            cost_transaction[d] += cash_collected_renewal[d] * TF

            # Schedule next renewal (renewal of renewals)
            next_renewal = d + contract_len
            if next_renewal < T:
                renewal_events[next_renewal] += ren_count * ren_of_ren

        # Churned = everyone who didn't renew at a renewal boundary
        if d > 0 and d % contract_len == 0:
            pass  # churn is already handled by not adding them to renewal_events

        # Compute active customers
        cumulative_new[d] = np.sum(new_events[:d + 1])
        total_refunded = np.sum(refunded_cum[:d + 1])
        # Active = cumulative new - churned - refunded
        # Churned is implicit: cumulative new - renewed - still_in_first_contract - refunded
        # Simpler: track active directly
        if d == 0:
            active[d] = day_new
        else:
            # Active = previous active + today's new - today's churn losses + today's renewals that keep them
            # At renewal boundaries, the renewal_events already represent who stays
            active[d] = active[d - 1] + day_new - refunded_cum[d]
            # Remove customers whose contract expired today without renewing
            # Customers from day (d - contract_len) had contract_len, expiring today
            expire_day = d - contract_len
            if expire_day >= 0:
                expired_cohort = new_events[expire_day]
                already_refunded = expired_cohort * refund_r
                remaining = expired_cohort - already_refunded
                churned_today = remaining * churn
                active[d] -= churned_today
                churned_cum[d] += churned_today

            # Handle renewal-of-renewal expirations
            expire_renewal_day = d - contract_len
            if expire_renewal_day >= 0 and renewed_cum[expire_renewal_day] > 0:
                ren_expired = renewed_cum[expire_renewal_day]
                ren_churned = ren_expired * (1.0 - ren_of_ren)
                active[d] -= ren_churned
                churned_cum[d] += ren_churned

        # Cap active at 0
        active[d] = max(active[d], 0)

        # Cap at TAM
        if inp.total_addressable_market > 0:
            active[d] = min(active[d], inp.total_addressable_market)

    new_cust_total = new_cust_inbound + new_cust_outbound + new_cust_organic + new_cust_viral

    # ── Marketing costs ──
    cost_marketing = np.zeros(T)
    daily_media = inp.media_spend / 30.0 if inp.use_inbound else 0
    daily_outbound = (inp.number_of_sdrs * inp.outbound_salary) / 30.0 if inp.use_outbound else 0
    daily_organic = inp.organic_cost_per_month / 30.0 if inp.use_organic else 0
    cost_marketing[:] = daily_media + daily_outbound + daily_organic

    # Viral marketing cost
    if inp.use_viral:
        cost_marketing += new_cust_viral * P * c_m_viral

    # ── Fixed costs ──
    cost_fixed = np.zeros(T)
    daily_fc = inp.fixed_costs_per_month / 30.0
    for d in range(T):
        scaling = (active[d] / 100.0) * (inp.fixed_cost_increase_per_100_customers / 30.0)
        cost_fixed[d] = daily_fc + scaling

    # ── Interest costs ──
    cost_interest = np.full(T, (inp.debt * (inp.interest_rate / 100.0)) / 365.0)

    # ── Viral sales costs ──
    cost_sales_viral = np.zeros(T)
    if inp.use_viral:
        cost_sales_viral = new_cust_viral * P * c_s_viral

    # ── Aggregate costs ──
    cost_sales = cost_sales_new + cost_sales_renewal + cost_sales_viral
    cost_fulfillment = cost_fulfill_new + cost_fulfill_renewal

    cost_total = (
        cost_marketing
        + cost_sales
        + cost_fulfillment
        + cost_fixed
        + cost_transaction
        + cost_interest
        + cost_refunds
    )

    # ── P&L ──
    revenue_total = revenue_new + revenue_renewal
    cash_collected_total = cash_collected_new + cash_collected_renewal

    gross_revenue = cash_collected_total
    cogs = cost_fulfillment + cost_transaction
    gross_profit = gross_revenue - cogs

    operating_expenses = cost_marketing + cost_sales + cost_fixed + cost_refunds
    ebitda = gross_profit - operating_expenses
    ebit = ebitda  # no depreciation/amortization modeled
    tax_daily = np.where(ebit > 0, ebit * (inp.tax_rate / 100.0), 0)
    net_income = ebit - tax_daily - cost_interest

    # FCF = net income (simplified: no capex, no working capital changes beyond what's modeled)
    free_cash_flow = net_income.copy()
    cumulative_fcf = np.cumsum(free_cash_flow)

    # Cash balance
    cash_balance = np.zeros(T)
    cash_balance[0] = inp.cash_in_bank - inp.upfront_investment_costs + free_cash_flow[0]
    for d in range(1, T):
        cash_balance[d] = cash_balance[d - 1] + free_cash_flow[d]

    return SimulationResult(
        days=days,
        new_customers_inbound=new_cust_inbound,
        new_customers_outbound=new_cust_outbound,
        new_customers_organic=new_cust_organic,
        new_customers_viral=new_cust_viral,
        new_customers_total=new_cust_total,
        cumulative_customers=np.cumsum(new_cust_total) + inp.customer_count,
        active_customers=active,
        churned_customers=np.cumsum(churned_cum),
        renewed_customers=np.cumsum(renewed_cum),
        refunded_customers=np.cumsum(refunded_cum),
        revenue_new=revenue_new,
        revenue_renewal=revenue_renewal,
        revenue_total=revenue_total,
        cash_collected_new=cash_collected_new,
        cash_collected_renewal=cash_collected_renewal,
        cash_collected_total=cash_collected_total,
        cost_marketing=cost_marketing,
        cost_sales=cost_sales,
        cost_fulfillment=cost_fulfillment,
        cost_fixed=cost_fixed,
        cost_transaction_fees=cost_transaction,
        cost_interest=cost_interest,
        cost_refunds=cost_refunds,
        cost_total=cost_total,
        gross_profit=gross_profit,
        ebitda=ebitda,
        ebit=ebit,
        net_income=net_income,
        free_cash_flow=free_cash_flow,
        cumulative_fcf=cumulative_fcf,
        cash_balance=cash_balance,
        leads_inbound=leads_inbound_arr,
        leads_outbound=leads_outbound_arr,
        leads_organic=leads_organic_arr,
    )


def to_monthly(result: SimulationResult) -> pd.DataFrame:
    """Aggregate daily simulation results into a monthly DataFrame."""
    T = len(result.days)
    months = T // 30

    data = {}
    fields = [
        "new_customers_total", "new_customers_inbound", "new_customers_outbound",
        "new_customers_organic", "new_customers_viral",
        "revenue_total", "revenue_new", "revenue_renewal",
        "cash_collected_total", "cash_collected_new", "cash_collected_renewal",
        "cost_marketing", "cost_sales", "cost_fulfillment", "cost_fixed",
        "cost_transaction_fees", "cost_interest", "cost_refunds", "cost_total",
        "gross_profit", "ebitda", "ebit", "net_income", "free_cash_flow",
    ]

    for f in fields:
        arr = getattr(result, f)
        monthly_vals = []
        for m in range(months):
            start = m * 30
            end = min(start + 30, T)
            monthly_vals.append(np.sum(arr[start:end]))
        data[f] = monthly_vals

    # Point-in-time values (take end-of-month snapshot)
    snapshot_fields = ["active_customers", "cumulative_customers", "cash_balance",
                       "cumulative_fcf", "churned_customers", "renewed_customers"]
    for f in snapshot_fields:
        arr = getattr(result, f)
        monthly_vals = []
        for m in range(months):
            end = min((m + 1) * 30 - 1, T - 1)
            monthly_vals.append(arr[end])
        data[f] = monthly_vals

    data["month"] = list(range(1, months + 1))
    return pd.DataFrame(data)
