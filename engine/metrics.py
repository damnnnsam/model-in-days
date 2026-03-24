from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.inputs import ModelInputs
from engine.simulation import SimulationResult


@dataclass
class KPIMetrics:
    # Unit economics
    cac_blended: float
    cac_inbound: float
    cac_outbound: float
    ltv: float
    ltv_cac_ratio: float
    payback_period_days: float

    # Margins (trailing 30 days)
    gross_margin: float
    ebitda_margin: float
    net_margin: float

    # Snapshot
    monthly_revenue: float
    monthly_cash_collected: float
    monthly_fcf: float
    total_customers: float
    active_customers: float
    monthly_new_customers: float

    # Nick Kozmin metrics
    time_to_profitability_days: int
    time_to_profitability_months: int
    cash_consumption: float
    profit_per_customer_per_month: float
    k_value: float
    cash_needed: float
    cash_conversion_cycle: int  # days from first contact to cash collected
    time_to_self_fund_days: int  # day cash balance goes positive
    time_to_self_fund_months: int


def compute_kpis(inp: ModelInputs, sim: SimulationResult, at_day: int | None = None,
                  operator_cost_daily: np.ndarray | None = None) -> KPIMetrics:
    T = len(sim.days)
    end = min(at_day, T) if at_day is not None else T
    trail = min(30, end)
    start = end - trail

    # ── CAC ──────────────────────────────────────────────────────────
    total_marketing_spend = float(np.sum(sim.cost_marketing[:end]))
    total_sales_spend = float(np.sum(sim.cost_sales[:end]))
    total_acquisition_cost = total_marketing_spend + total_sales_spend

    total_new_customers = float(np.sum(sim.new_customers_total[:end]))
    cac_blended = total_acquisition_cost / max(total_new_customers, 1)

    # Per-channel CAC
    total_inbound_custs = float(np.sum(sim.new_customers_inbound[:end]))
    if inp.use_inbound and total_inbound_custs > 0:
        inbound_spend = float(np.sum(np.full(end, inp.media_spend / 30.0)))
        inbound_sales = float(np.sum(sim.new_customers_inbound[:end])) * inp.price_of_offer * (inp.cost_to_sell / 100.0)
        cac_inbound = (inbound_spend + inbound_sales) / total_inbound_custs
    else:
        cac_inbound = 0.0

    total_outbound_custs = float(np.sum(sim.new_customers_outbound[:end]))
    if inp.use_outbound and total_outbound_custs > 0:
        outbound_spend = float(np.sum(np.full(end, (inp.number_of_sdrs * inp.outbound_salary) / 30.0)))
        outbound_sales = total_outbound_custs * inp.price_of_offer * (inp.cost_to_sell / 100.0)
        cac_outbound = (outbound_spend + outbound_sales) / total_outbound_custs
    else:
        cac_outbound = 0.0

    # ── LTV ──────────────────────────────────────────────────────────
    P = inp.price_of_offer
    RR = inp.realization_rate / 100.0
    c_f = inp.cost_to_fulfill / 100.0
    refund_r = inp.refund_rate / 100.0
    churn = inp.churn_rate / 100.0

    # First purchase contribution
    first_purchase_value = P * RR * (1 - refund_r) - P * c_f

    # Renewal value per renewal cycle
    p_ren = inp.price_of_renewal
    c_f_ren = inp.cost_to_fulfill_renewal / 100.0
    c_s_ren = inp.cost_to_sell_renewal / 100.0
    renewal_value = p_ren * RR - p_ren * c_f_ren - p_ren * c_s_ren

    # Expected renewals: geometric series
    # Probability of first renewal = (1 - churn)(1 - refund_r)
    p_first_renewal = (1 - churn) * (1 - refund_r)
    p_subsequent = inp.renewal_rate_of_renewals / 100.0

    if p_subsequent < 1.0 and p_subsequent > 0:
        expected_renewal_revenue = p_first_renewal * renewal_value / (1 - p_subsequent)
    elif p_subsequent >= 1.0:
        expected_renewal_revenue = p_first_renewal * renewal_value * 10  # cap at 10 renewals
    else:
        expected_renewal_revenue = p_first_renewal * renewal_value

    ltv = first_purchase_value + expected_renewal_revenue
    ltv_cac = ltv / max(cac_blended, 1)

    # ── Payback period ──────────────────────────────────────────────
    # Days until cumulative revenue from a customer covers the CAC
    daily_revenue_rate = (P * RR) / max(inp.time_to_collect, 1)
    payback_days = cac_blended / max(daily_revenue_rate, 0.01)

    # ── Margins (trailing 30 days) ──────────────────────────────────
    trailing_revenue = float(np.sum(sim.cash_collected_total[start:end]))
    trailing_cogs = float(np.sum(sim.cost_fulfillment[start:end] + sim.cost_transaction_fees[start:end]))
    trailing_gp = trailing_revenue - trailing_cogs
    trailing_ebitda = float(np.sum(sim.ebitda[start:end]))
    trailing_ni = float(np.sum(sim.net_income[start:end]))

    gross_margin = (trailing_gp / trailing_revenue * 100) if trailing_revenue > 0 else 0
    ebitda_margin = (trailing_ebitda / trailing_revenue * 100) if trailing_revenue > 0 else 0
    net_margin = (trailing_ni / trailing_revenue * 100) if trailing_revenue > 0 else 0

    # ── Adjust for operator costs if provided ──────────────────────
    T_full = len(sim.days)
    if operator_cost_daily is not None:
        op_cost = operator_cost_daily[:T_full]
        adj_fcf = sim.free_cash_flow[:T_full] - op_cost
        adj_cumulative_fcf = np.cumsum(adj_fcf)
        adj_cash_balance = sim.cash_balance.copy()
        cum_op = np.cumsum(op_cost)
        adj_cash_balance[:T_full] -= cum_op
    else:
        adj_fcf = sim.free_cash_flow[:T_full]
        adj_cumulative_fcf = sim.cumulative_fcf[:T_full]
        adj_cash_balance = sim.cash_balance

    monthly_rev = float(np.sum(sim.revenue_total[start:end]))
    monthly_cash = trailing_revenue
    monthly_fcf = float(np.sum(adj_fcf[start:end]))
    monthly_new = float(np.sum(sim.new_customers_total[start:end]))

    # ── Time to profitability (simulation-wide, not cursor-scoped) ──
    # Find the last day cumulative FCF is negative. The day after that
    # is when the business is sustainably profitable (stays positive).
    last_negative_day = -1
    for d in range(T_full):
        if adj_cumulative_fcf[d] < 0:
            last_negative_day = d
    if last_negative_day == -1:
        ttp_days = 0
    elif last_negative_day < T_full - 1:
        ttp_days = last_negative_day + 1
    else:
        ttp_days = T_full
    ttp_months = max(1, round(ttp_days / 30)) if ttp_days < T_full else -1

    # ── Cash consumption (simulation-wide) ────────────────────────
    min_cash = float(np.min(adj_cash_balance[:T_full]))
    cash_consumption = abs(min(min_cash, 0))
    cash_needed = max(-min_cash, 0)

    # ── Profit per customer per month ───────────────────────────────
    active_end = float(sim.active_customers[end - 1])
    if active_end > 0 and trailing_revenue > 0:
        trailing_costs = float(np.sum(sim.cost_total[start:end]))
        profit_per_cust_month = (trailing_revenue - trailing_costs) / active_end
    else:
        profit_per_cust_month = 0.0

    # ── K value (viral coefficient) ─────────────────────────────────
    if inp.use_viral:
        k_value = inp.invites_per_customer * (inp.conversion_rate_per_invite / 100.0)
    else:
        k_value = 0.0

    # ── Cash conversion cycle ────────────────────────────────────────
    ttm = 0
    if inp.use_outbound:
        ttm = inp.time_to_market_outbound
    elif inp.use_inbound:
        ttm = inp.time_to_market_inbound
    elif inp.use_organic:
        ttm = inp.time_to_market_organic
    ccc = ttm + inp.time_to_sell + inp.time_to_collect

    # ── Time to self-fund ────────────────────────────────────────────
    # First day cash balance crosses from negative to positive
    ttsf_days = T_full
    if adj_cash_balance[0] >= 0:
        ttsf_days = 0
    else:
        for d in range(1, T_full):
            if adj_cash_balance[d] >= 0 and adj_cash_balance[d - 1] < 0:
                ttsf_days = d
                break
    ttsf_months = max(1, round(ttsf_days / 30)) if ttsf_days < T_full else -1

    return KPIMetrics(
        cac_blended=cac_blended,
        cac_inbound=cac_inbound,
        cac_outbound=cac_outbound,
        ltv=ltv,
        ltv_cac_ratio=ltv_cac,
        payback_period_days=payback_days,
        gross_margin=gross_margin,
        ebitda_margin=ebitda_margin,
        net_margin=net_margin,
        monthly_revenue=monthly_rev,
        monthly_cash_collected=monthly_cash,
        monthly_fcf=monthly_fcf,
        total_customers=float(sim.cumulative_customers[end - 1]),
        active_customers=float(sim.active_customers[end - 1]),
        monthly_new_customers=monthly_new,
        time_to_profitability_days=ttp_days,
        time_to_profitability_months=ttp_months,
        cash_consumption=cash_consumption,
        profit_per_customer_per_month=profit_per_cust_month,
        k_value=k_value,
        cash_needed=cash_needed,
        cash_conversion_cycle=ccc,
        time_to_self_fund_days=ttsf_days,
        time_to_self_fund_months=ttsf_months,
    )
