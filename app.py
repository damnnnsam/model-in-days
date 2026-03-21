import streamlit as st

st.set_page_config(
    page_title="Model In Days",
    layout="wide",
    initial_sidebar_state="expanded",
)

from engine.simulation import run_simulation, to_monthly, to_daily_df
from engine.valuation import compute_valuation
from engine.metrics import compute_kpis
from ui.sidebar import render_sidebar
from ui.dashboard import (
    render_kpi_cards, render_valuation_panel, render_sensitivity,
    render_scenario_comparison, render_export,
)
from ui.charts import (
    customers_chart,
    new_customers_by_channel,
    revenue_chart,
    cash_collected_chart,
    cost_breakdown_chart,
    pnl_chart,
    cash_balance_chart,
    fcf_chart,
    valuation_waterfall,
    add_cursor,
    hero_chart,
)

st.markdown("# Model In Days")
st.markdown("<span style='color:#666;font-size:14px'>Use this model to find the most profitable direction for your business and to understand what metrics really matter.</span>", unsafe_allow_html=True)

inp = render_sidebar()

import json, os
with open(os.path.join(os.path.dirname(__file__), "current_model.json"), "w") as _f:
    json.dump(inp.__dict__, _f, indent=2, default=str)

from engine.url_state import encode_model
encoded = encode_model(inp)
current_url_param = st.query_params.get("m", "")
if encoded != current_url_param:
    st.query_params["m"] = encoded
st.sidebar.markdown("---")
if st.sidebar.button("Copy Share Link", key="share_btn"):
    st.sidebar.code(f"?m={encoded}", language=None)
    st.sidebar.success("Copy the URL from your browser address bar to share this model.")

sim = run_simulation(inp)
daily = to_daily_df(sim)
monthly = to_monthly(sim)
val = compute_valuation(inp, sim)

# ── Hero chart ──────────────────────────────────────────────────────
total_days = inp.time_max
cursor_day = total_days  # default, updated by slider below
st.plotly_chart(hero_chart(daily, cursor_day=None), use_container_width=True)

# ── Time cursor (between charts and metrics) ────────────────────────
col_slider, col_label = st.columns([5, 1])
with col_slider:
    cursor_day = st.slider(
        "View metrics at day",
        min_value=1, max_value=total_days, value=total_days,
        key="time_cursor",
    )
with col_label:
    years = cursor_day / 365
    st.markdown(f"**≈ {years:.1f} years**")

kpis = compute_kpis(inp, sim, at_day=cursor_day)

# ── KPI strip ───────────────────────────────────────────────────────
def _fd(v):
    if abs(v) >= 1_000_000: return f"${v/1_000_000:,.1f}M"
    if abs(v) >= 1_000: return f"${v/1_000:,.1f}K"
    return f"${v:,.0f}"

render_kpi_cards(kpis)

st.divider()

# ── Tabs for different views ────────────────────────────────────────
tab_val, tab_calc, tab_alpha, tab_cust, tab_rev, tab_costs, tab_pnl, tab_sens, tab_compare, tab_export = st.tabs([
    "Valuation", "Calculations", "GTM Alpha", "Customers", "Revenue & Cash", "Costs", "P&L & FCF",
    "Sensitivity", "Compare Scenarios", "Export",
])

with tab_val:
    render_valuation_panel(val, inp)
    st.divider()
    st.plotly_chart(
        valuation_waterfall(
            pv_fcf=val.pv_fcf,
            pv_terminal=val.pv_terminal_value,
            debt=inp.debt,
            cash=val.cash_at_valuation,
            equity=val.equity_value_dcf,
        ),
        use_container_width=True,
    )

with tab_calc:
    st.markdown("Every number, every formula, every step. Verify anything.")

    # ── 0. Full logic trace for this day ──
    d = min(cursor_day - 1, len(sim.days) - 1)
    prev = max(d - 1, 0)
    trail_start = max(0, d - 29)
    contract_len = max(inp.contract_length, 1)
    delay_ob = inp.time_to_market_outbound + inp.time_to_sell
    delay_in = inp.time_to_market_inbound + inp.time_to_sell

    st.markdown(f"### 0. Full Simulation Trace — Day {cursor_day}")
    st.markdown(f"Step-by-step logic that produced every value on this day.")

    # Step 1: Where did new customers come from?
    lead_source_day_ob = d - delay_ob
    lead_source_day_in = d - delay_in
    ob_leads_that_day = (inp.contacts_per_month / 30) * (inp.outbound_conversion_rate / 100) if inp.use_outbound and lead_source_day_ob >= 0 else 0
    in_leads_that_day = 0
    if inp.use_inbound and inp.cpm > 0 and lead_source_day_in >= 0:
        in_leads_that_day = ((inp.media_spend / inp.cpm) * 1000 / 30) * (inp.ctr / 100) * (inp.funnel_conversion_rate / 100)

    st.code(f"""STEP 1: NEW CUSTOMER ARRIVALS ON DAY {cursor_day}
────────────────────────────────────────────────────
{"OUTBOUND:" if inp.use_outbound else "OUTBOUND: (disabled)"}
  Leads were generated on day {max(lead_source_day_ob, 0)} (today - delay of {delay_ob} days)
  leads_that_day       = contacts/day × contact_to_lead_rate
                       = {inp.contacts_per_month/30:.0f} × {inp.outbound_conversion_rate}%
                       = {ob_leads_that_day:.2f} leads
  customers_from_ob    = leads × lead_to_customer_rate
                       = {ob_leads_that_day:.2f} × {inp.lead_conversion_rate_outbound}%
                       = {sim.new_customers_outbound[d]:.4f}
{"" if not inp.use_inbound else f"""
INBOUND:
  Leads were generated on day {max(lead_source_day_in, 0)} (today - delay of {delay_in} days)
  leads_that_day       = {in_leads_that_day:.2f}
  customers_from_in    = {sim.new_customers_inbound[d]:.4f}
"""}{"" if not inp.use_viral else f"""VIRAL:
  Based on active customers {inp.viral_time + inp.time_to_sell} days ago
  customers_from_viral = {sim.new_customers_viral[d]:.4f}
"""}
  TOTAL NEW TODAY       = {sim.new_customers_total[d]:.4f}""", language=None)

    # Step 2: Cohort expirations and churn
    expire_day = d - contract_len
    if expire_day >= 0:
        expired_cohort_size = sim.new_customers_total[expire_day]
        refunded_from_cohort = expired_cohort_size * (inp.refund_rate / 100)
        remaining = expired_cohort_size - refunded_from_cohort
        churned_today = remaining * (inp.churn_rate / 100)
        renewed_today = remaining * (1 - inp.churn_rate / 100)
    else:
        expired_cohort_size = 0
        churned_today = 0
        renewed_today = 0

    st.code(f"""STEP 2: CHURN & RENEWALS ON DAY {cursor_day}
────────────────────────────────────────────────────
  Contract length = {contract_len} days
  Cohort expiring today = customers acquired on day {max(expire_day, 0)}
  {"(no cohort expires today — too early)" if expire_day < 0 else f"""
  cohort_size            = {expired_cohort_size:.4f} customers
  already_refunded       = {expired_cohort_size:.4f} × {inp.refund_rate}% = {expired_cohort_size * inp.refund_rate / 100:.4f}
  remaining at expiry    = {expired_cohort_size - expired_cohort_size * inp.refund_rate / 100:.4f}
  churned (lost)         = remaining × {inp.churn_rate}% = {churned_today:.4f}
  renewed (stayed)       = remaining × {100 - inp.churn_rate}% = {renewed_today:.4f}"""}""", language=None)

    # Step 3: Active customer calculation
    st.code(f"""STEP 3: ACTIVE CUSTOMER COUNT
────────────────────────────────────────────────────
  active_yesterday       = {sim.active_customers[prev]:.1f}
  + new_today            = {sim.new_customers_total[d]:.4f}
  - churned_today        = {churned_today:.4f}
  - refunded_today       = {sim.refunded_customers[d] - sim.refunded_customers[prev] if d > 0 else 0:.4f}
  ──────────────────────
  = active_today         = {sim.active_customers[d]:.1f}

  (cumulative all time   = {sim.cumulative_customers[d]:.1f})""", language=None)

    # Step 4: Revenue
    st.code(f"""STEP 4: REVENUE ON DAY {cursor_day}
────────────────────────────────────────────────────
  From new sales:
    {sim.new_customers_total[d]:.4f} customers × ${inp.price_of_offer:,.0f} × {inp.realization_rate}%
    = ${sim.revenue_new[d]:,.2f}

  From renewals:
    revenue_renewal      = ${sim.revenue_renewal[d]:,.2f}

  Cash actually collected today (from all past cohorts' payment schedules):
    cash_collected_new   = ${sim.cash_collected_new[d]:,.2f}
    cash_collected_ren   = ${sim.cash_collected_renewal[d]:,.2f}
    cash_collected_total = ${sim.cash_collected_total[d]:,.2f}

  Note: cash_collected ≠ revenue because of time_to_collect.
  Revenue is booked on sale day. Cash arrives over {inp.time_to_collect} days.""", language=None)

    # Step 5: Costs
    fc_scaling = (sim.active_customers[d] / 100) * (inp.fixed_cost_increase_per_100_customers / 30)
    st.code(f"""STEP 5: COSTS ON DAY {cursor_day}
────────────────────────────────────────────────────
  Marketing:
    {"media_spend/30 = $" + f"{inp.media_spend/30:,.0f}" if inp.use_inbound else "(inbound disabled)"}
    {"SDRs × salary/30 = " + str(inp.number_of_sdrs) + " × $" + f"{inp.outbound_salary:,.0f}/30 = ${inp.number_of_sdrs * inp.outbound_salary / 30:,.0f}" if inp.use_outbound else "(outbound disabled)"}
    = ${sim.cost_marketing[d]:,.2f}

  Sales commission:
    new_customers × P × c_s = {sim.new_customers_total[d]:.4f} × ${inp.price_of_offer:,.0f} × {inp.cost_to_sell}%
    = ${sim.cost_sales[d]:,.2f}

  Fulfillment (accumulated from active cohorts):
    = ${sim.cost_fulfillment[d]:,.2f}

  Fixed costs:
    base = ${inp.fixed_costs_per_month:,.0f}/30 = ${inp.fixed_costs_per_month/30:,.0f}/day
    + scaling = ({sim.active_customers[d]:.0f} / 100) × ${inp.fixed_cost_increase_per_100_customers:,.0f}/30 = ${fc_scaling:,.0f}
    = ${sim.cost_fixed[d]:,.2f}

  Transaction fees:
    cash_collected × {inp.transaction_fee}% = ${sim.cost_transaction_fees[d]:,.2f}

  Interest:
    ${inp.debt:,.0f} × {inp.interest_rate}% / 365 = ${sim.cost_interest[d]:,.2f}

  Refunds:
    = ${sim.cost_refunds[d]:,.2f}

  TOTAL COSTS          = ${sim.cost_total[d]:,.2f}""", language=None)

    # Step 6: P&L
    st.code(f"""STEP 6: P&L ON DAY {cursor_day}
────────────────────────────────────────────────────
  Cash collected         ${sim.cash_collected_total[d]:>12,.2f}
  - COGS (fulfill+txn)  {-(sim.cost_fulfillment[d] + sim.cost_transaction_fees[d]):>12,.2f}
  ──────────────────────────────────────
  = Gross Profit         ${sim.gross_profit[d]:>12,.2f}

  - Marketing            {-sim.cost_marketing[d]:>12,.2f}
  - Sales                {-sim.cost_sales[d]:>12,.2f}
  - Fixed                {-sim.cost_fixed[d]:>12,.2f}
  - Refunds              {-sim.cost_refunds[d]:>12,.2f}
  ──────────────────────────────────────
  = EBITDA               ${sim.ebitda[d]:>12,.2f}

  - Tax ({inp.tax_rate}% if positive) {-(sim.ebitda[d] * inp.tax_rate / 100) if sim.ebitda[d] > 0 else 0:>12,.2f}
  - Interest             {-sim.cost_interest[d]:>12,.2f}
  ──────────────────────────────────────
  = Net Income           ${sim.net_income[d]:>12,.2f}
  = Free Cash Flow       ${sim.free_cash_flow[d]:>12,.2f}

RUNNING TOTALS:
  cumulative FCF         ${sim.cumulative_fcf[d]:>12,.2f}
  cash balance           ${sim.cash_balance[d]:>12,.2f}""", language=None)

    # Trailing summary
    st.code(f"""TRAILING 30 DAYS (day {trail_start+1} to {d+1}):
  revenue              = ${float(sum(sim.revenue_total[trail_start:d+1])):>12,.0f}
  cash collected       = ${float(sum(sim.cash_collected_total[trail_start:d+1])):>12,.0f}
  costs                = ${float(sum(sim.cost_total[trail_start:d+1])):>12,.0f}
  FCF                  = ${float(sum(sim.free_cash_flow[trail_start:d+1])):>12,.0f}
  new customers        = {float(sum(sim.new_customers_total[trail_start:d+1])):>12.1f}""", language=None)

    st.markdown("---")

    # ── 1. Channel Math ──
    st.markdown("### 1. Customer Acquisition")
    if inp.use_outbound:
        contacts_day = inp.contacts_per_month / 30
        leads_day = contacts_day * (inp.outbound_conversion_rate / 100)
        custs_day = leads_day * (inp.lead_conversion_rate_outbound / 100)
        delay = inp.time_to_market_outbound + inp.time_to_sell
        st.markdown("**Outbound**")
        st.code(f"""contacts/day     = contacts_per_month / 30
                 = {inp.contacts_per_month:,} / 30
                 = {contacts_day:,.1f}

leads/day        = contacts/day × (outbound_conversion_rate / 100)
                 = {contacts_day:,.1f} × ({inp.outbound_conversion_rate} / 100)
                 = {leads_day:,.2f}

customers/day    = leads/day × (lead_conversion_rate / 100)
                 = {leads_day:,.2f} × ({inp.lead_conversion_rate_outbound} / 100)
                 = {custs_day:,.4f}

customers/month  = {custs_day * 30:,.1f}

delay            = time_to_market + time_to_sell
                 = {inp.time_to_market_outbound} + {inp.time_to_sell}
                 = {delay} days (first customer arrives on day {delay})""", language=None)

    if inp.use_inbound:
        if inp.cpm > 0:
            imp_day = (inp.media_spend / inp.cpm) * 1000 / 30
            clicks_day = imp_day * (inp.ctr / 100)
            leads_day_in = clicks_day * (inp.funnel_conversion_rate / 100)
        else:
            imp_day = clicks_day = leads_day_in = 0
        custs_day_in = leads_day_in * (inp.lead_conversion_rate_inbound / 100)
        delay_in = inp.time_to_market_inbound + inp.time_to_sell
        st.markdown("**Inbound**")
        st.code(f"""impressions/day  = (media_spend / cpm) × 1000 / 30
                 = (${inp.media_spend:,.0f} / ${inp.cpm:,.0f}) × 1000 / 30
                 = {imp_day:,.0f}

clicks/day       = impressions/day × (ctr / 100)
                 = {imp_day:,.0f} × ({inp.ctr} / 100)
                 = {clicks_day:,.1f}

leads/day        = clicks/day × (funnel_conversion_rate / 100)
                 = {clicks_day:,.1f} × ({inp.funnel_conversion_rate} / 100)
                 = {leads_day_in:,.2f}

customers/day    = leads/day × (lead_conversion_rate / 100)
                 = {leads_day_in:,.2f} × ({inp.lead_conversion_rate_inbound} / 100)
                 = {custs_day_in:,.4f}

customers/month  = {custs_day_in * 30:,.1f}

delay            = {inp.time_to_market_inbound} + {inp.time_to_sell} = {delay_in} days""", language=None)

    if inp.use_viral:
        k = inp.invites_per_customer * (inp.conversion_rate_per_invite / 100)
        st.markdown("**Viral**")
        st.code(f"""K value          = invites_per_customer × (conversion_rate / 100)
                 = {inp.invites_per_customer} × ({inp.conversion_rate_per_invite} / 100)
                 = {k:.3f}  {"(> 1 = exponential growth)" if k > 1 else "(< 1 = decaying contribution)"}

viral starts     = day {inp.viral_start}
viral delay      = viral_time + time_to_sell = {inp.viral_time} + {inp.time_to_sell} = {inp.viral_time + inp.time_to_sell} days""", language=None)

    # ── 2. Revenue Per Customer ──
    st.markdown("### 2. Revenue Per Customer")
    rev_collected = inp.price_of_offer * (inp.realization_rate / 100)
    fulfill_cost = inp.price_of_offer * (inp.cost_to_fulfill / 100)
    sales_cost = inp.price_of_offer * (inp.cost_to_sell / 100)
    txn_cost = rev_collected * (inp.transaction_fee / 100)
    contribution = rev_collected - fulfill_cost - sales_cost - txn_cost
    st.code(f"""NEW CUSTOMER:
  revenue_collected = P × RR = ${inp.price_of_offer:,.0f} × {inp.realization_rate}% = ${rev_collected:,.0f}
  - fulfillment     = P × c_f = ${inp.price_of_offer:,.0f} × {inp.cost_to_fulfill}% = ${fulfill_cost:,.0f}
  - sales commission = P × c_s = ${inp.price_of_offer:,.0f} × {inp.cost_to_sell}% = ${sales_cost:,.0f}
  - transaction fee  = revenue × TF = ${rev_collected:,.0f} × {inp.transaction_fee}% = ${txn_cost:,.0f}
  = contribution     = ${contribution:,.0f}

  cash collected over {inp.time_to_collect} days (${rev_collected / max(inp.time_to_collect, 1):,.0f}/day)
  refund rate: {inp.refund_rate}% after {inp.refund_period} days""", language=None)

    if inp.churn_rate < 100:
        rev_ren = inp.price_of_renewal * (inp.realization_rate / 100)
        ful_ren = inp.price_of_renewal * (inp.cost_to_fulfill_renewal / 100)
        sal_ren = inp.price_of_renewal * (inp.cost_to_sell_renewal / 100)
        txn_ren = rev_ren * (inp.transaction_fee / 100)
        cont_ren = rev_ren - ful_ren - sal_ren - txn_ren
        renewal_rate = 100 - inp.churn_rate
        st.code(f"""RENEWAL:
  renewal rate       = 100% - churn = 100% - {inp.churn_rate}% = {renewal_rate}%
  renewal price      = ${inp.price_of_renewal:,.0f}
  revenue_collected  = ${rev_ren:,.0f}
  - fulfillment      = ${ful_ren:,.0f} ({inp.cost_to_fulfill_renewal}%)
  - sales commission = ${sal_ren:,.0f} ({inp.cost_to_sell_renewal}%)
  - transaction fee  = ${txn_ren:,.0f} ({inp.transaction_fee}%)
  = contribution     = ${cont_ren:,.0f}

  contract length: {inp.contract_length} days
  renewal of renewals: {inp.renewal_rate_of_renewals}%
  cash collected over {inp.time_to_collect_renewal} days""", language=None)

    # ── 3. LTV ──
    st.markdown("### 3. Lifetime Value")
    P = inp.price_of_offer
    RR = inp.realization_rate / 100
    c_f = inp.cost_to_fulfill / 100
    refund_r = inp.refund_rate / 100
    churn = inp.churn_rate / 100
    first_val = P * RR * (1 - refund_r) - P * c_f
    p_ren = inp.price_of_renewal
    c_f_r = inp.cost_to_fulfill_renewal / 100
    c_s_r = inp.cost_to_sell_renewal / 100
    ren_val = p_ren * RR - p_ren * c_f_r - p_ren * c_s_r
    p_first = (1 - churn) * (1 - refund_r)
    p_sub = inp.renewal_rate_of_renewals / 100
    if 0 < p_sub < 1:
        exp_ren = p_first * ren_val / (1 - p_sub)
    else:
        exp_ren = p_first * ren_val
    ltv = first_val + exp_ren
    st.code(f"""first_purchase_value = P × RR × (1 - refund_rate) - P × c_f
                    = ${P:,.0f} × {RR:.2f} × {1-refund_r:.2f} - ${P:,.0f} × {c_f:.2f}
                    = ${first_val:,.0f}

renewal_value       = p_renewal × RR - p_renewal × c_f_ren - p_renewal × c_s_ren
                    = ${p_ren:,.0f} × {RR:.2f} - ${p_ren:,.0f} × {c_f_r:.2f} - ${p_ren:,.0f} × {c_s_r:.2f}
                    = ${ren_val:,.0f}

p(first renewal)    = (1 - churn) × (1 - refund) = {1-churn:.2f} × {1-refund_r:.2f} = {p_first:.3f}
p(subsequent)       = renewal_rate_of_renewals = {p_sub:.2f}

expected_renewals   = p(first) × renewal_value / (1 - p(subsequent))
                    = {p_first:.3f} × ${ren_val:,.0f} / (1 - {p_sub:.2f})
                    = ${exp_ren:,.0f}

LTV                 = first_purchase + expected_renewals
                    = ${first_val:,.0f} + ${exp_ren:,.0f}
                    = ${ltv:,.0f}""", language=None)

    # ── 4. CAC ──
    st.markdown("### 4. Customer Acquisition Cost")
    total_mkt = float(sum(sim.cost_marketing))
    total_sal = float(sum(sim.cost_sales))
    total_custs = float(sum(sim.new_customers_total))
    cac = (total_mkt + total_sal) / max(total_custs, 1)
    st.code(f"""total_marketing_spend  = ${total_mkt:,.0f} (over {inp.time_max} days)
total_sales_spend     = ${total_sal:,.0f}
total_new_customers   = {total_custs:,.0f}

CAC (blended)         = (marketing + sales) / customers
                      = (${total_mkt:,.0f} + ${total_sal:,.0f}) / {total_custs:,.0f}
                      = ${cac:,.0f}

LTV / CAC             = ${ltv:,.0f} / ${cac:,.0f} = {ltv/max(cac,1):.1f}x""", language=None)

    # ── 5. Costs ──
    st.markdown("### 5. Monthly Cost Structure")
    daily_media = inp.media_spend / 30 if inp.use_inbound else 0
    daily_ob = (inp.number_of_sdrs * inp.outbound_salary) / 30 if inp.use_outbound else 0
    daily_org = inp.organic_cost_per_month / 30 if inp.use_organic else 0
    daily_fc = inp.fixed_costs_per_month / 30
    daily_interest = (inp.debt * inp.interest_rate / 100) / 365
    st.code(f"""MARKETING (monthly):
  inbound media     = ${inp.media_spend:,.0f}/mo {"(disabled)" if not inp.use_inbound else ""}
  outbound SDRs     = {inp.number_of_sdrs} × ${inp.outbound_salary:,.0f} = ${inp.number_of_sdrs * inp.outbound_salary:,.0f}/mo {"(disabled)" if not inp.use_outbound else ""}
  organic           = ${inp.organic_cost_per_month:,.0f}/mo {"(disabled)" if not inp.use_organic else ""}

FIXED (monthly):
  base              = ${inp.fixed_costs_per_month:,.0f}/mo
  + scaling         = ${inp.fixed_cost_increase_per_100_customers:,.0f}/mo per 100 customers

TRANSACTION FEE     = {inp.transaction_fee}% of cash collected
INTEREST            = ${inp.debt:,.0f} × {inp.interest_rate}% / 365 = ${daily_interest:,.0f}/day
TAX RATE            = {inp.tax_rate}% (on positive EBIT only)""", language=None)

    # ── 6. DCF Valuation ──
    st.markdown("### 6. DCF Valuation")
    st.code(f"""PROJECTION PERIOD    = {inp.projection_period_dcf} days ({inp.projection_period_dcf/365:.1f} years)
DISCOUNT RATE        = {inp.discount_rate}%
PERPETUAL GROWTH     = {inp.perpetual_growth_rate}%

daily_discount       = (1 + {inp.discount_rate/100})^(1/365)

PV of FCF            = Σ FCF(d) / daily_discount^d  for d = 0..{inp.projection_period_dcf}
                     = ${val.pv_fcf:,.0f}

terminal FCF/year    = avg daily FCF in last 365 days × 365
terminal_value       = terminal_FCF × (1 + g) / (r - g)
                     = TV × (1 + {inp.perpetual_growth_rate}%) / ({inp.discount_rate}% - {inp.perpetual_growth_rate}%)
                     = ${val.terminal_value:,.0f}

PV of terminal       = TV / (1 + r)^(projection/365)
                     = ${val.pv_terminal_value:,.0f}

ENTERPRISE VALUE     = PV(FCF) + PV(Terminal)
                     = ${val.pv_fcf:,.0f} + ${val.pv_terminal_value:,.0f}
                     = ${val.enterprise_value_dcf:,.0f}

EQUITY VALUE         = EV - debt + cash
                     = ${val.enterprise_value_dcf:,.0f} - ${inp.debt:,.0f} + ${max(val.cash_at_valuation,0):,.0f}
                     = ${val.equity_value_dcf:,.0f}

SHARE PRICE          = equity / shares
                     = ${val.equity_value_dcf:,.0f} / {inp.number_of_shares:,}
                     = ${val.share_price_dcf:,.2f}

TV as % of EV        = {val.pv_terminal_value / max(val.enterprise_value_dcf, 1) * 100:.0f}%""", language=None)

    # ── 7. EBITDA Multiple ──
    st.markdown("### 7. EBITDA Multiple Valuation")
    st.code(f"""trailing 12M EBITDA  = ${val.trailing_ebitda:,.0f}
EBITDA multiple      = {inp.enterprise_multiple_ebitda:.1f}x

ENTERPRISE VALUE     = EBITDA × multiple
                     = ${val.trailing_ebitda:,.0f} × {inp.enterprise_multiple_ebitda:.1f}
                     = ${val.enterprise_value_ebitda:,.0f}

EQUITY VALUE         = EV - debt + cash
                     = ${val.equity_value_ebitda:,.0f}

SHARE PRICE          = ${val.share_price_ebitda:,.2f}""", language=None)

    # ── 8. Cash Conversion Cycle ──
    st.markdown("### 8. Cash Conversion Cycle")
    ttm = 0
    ttm_label = "none"
    if inp.use_outbound:
        ttm = inp.time_to_market_outbound
        ttm_label = f"time_to_market_outbound = {ttm}"
    elif inp.use_inbound:
        ttm = inp.time_to_market_inbound
        ttm_label = f"time_to_market_inbound = {ttm}"
    ccc = ttm + inp.time_to_sell + inp.time_to_collect
    st.code(f"""CCC = time_to_market + time_to_sell + time_to_collect
    = {ttm_label}
    + time_to_sell = {inp.time_to_sell}
    + time_to_collect = {inp.time_to_collect}
    = {ccc} days

From first contact to cash in hand: {ccc} days""", language=None)

with tab_alpha:
    from engine.inputs import ModelInputs as _MI

    st.markdown("<span style='color:#666;font-size:13px'>Stress-test a single metric and see how it shifts equity value.</span>", unsafe_allow_html=True)

    ac1, ac2 = st.columns(2)
    with ac1:
        alpha_metric = st.selectbox("Metric to stress-test", [
            "Reply rate (contact → lead %)",
            "Lead → customer rate (%)",
            "Sends per month",
            "Price of offer ($)",
            "Churn rate (%)",
            "Cost to fulfill (%)",
        ], key="alpha_metric")
    with ac2:
        alpha_years = st.selectbox("Evaluate equity at", [
            "3 years", "5 years", "7 years",
        ], index=1, key="alpha_years")

    param_map = {
        "Reply rate (contact → lead %)": ("outbound_conversion_rate", "%", [0.05, 0.1, 0.15, 0.25, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0]),
        "Lead → customer rate (%)": ("lead_conversion_rate_outbound", "%", [2, 4, 6, 8, 10, 12, 15, 20]),
        "Sends per month": ("contacts_per_month", "", [5000, 10000, 15000, 20000, 25000, 30000, 40000, 50000]),
        "Price of offer ($)": ("price_of_offer", "$", [3000, 5000, 7000, 10000, 15000, 20000, 30000, 50000]),
        "Churn rate (%)": ("churn_rate", "%", [2, 5, 8, 10, 15, 20, 30, 50]),
        "Cost to fulfill (%)": ("cost_to_fulfill", "%", [10, 20, 30, 40, 50, 60, 70, 80]),
    }

    proj_days = {"3 years": 1095, "5 years": 1825, "7 years": 2500}[alpha_years]
    param_name, unit, test_values = param_map[alpha_metric]
    current_val = getattr(inp, param_name)

    # Which channel must be enabled for each metric
    channel_requires = {
        "outbound_conversion_rate": "use_outbound",
        "lead_conversion_rate_outbound": "use_outbound",
        "contacts_per_month": "use_outbound",
    }

    results = []
    for v in test_values:
        p = inp.__dict__.copy()
        p[param_name] = v
        p["projection_period_dcf"] = proj_days
        if param_name in channel_requires:
            p[channel_requires[param_name]] = True
        test_inp = _MI(**p)
        test_sim = run_simulation(test_inp)
        test_val = compute_valuation(test_inp, test_sim)
        test_kpis = compute_kpis(test_inp, test_sim, at_day=proj_days)
        results.append({
            "value": v,
            "equity": test_val.equity_value_dcf,
            "active": test_kpis.active_customers,
            "monthly_fcf": test_kpis.monthly_fcf,
            "monthly_rev": test_kpis.monthly_revenue,
        })

    base_eq = [r for r in results if abs(r["value"] - current_val) < 0.01]
    base_equity = base_eq[0]["equity"] if base_eq else results[0]["equity"]

    import plotly.graph_objects as go
    from ui.charts import COLORS

    eq_values = [r["equity"] for r in results]
    labels = [f"{unit}{v:,.0f}" if unit == "$" else f"{v:g}{unit}" for v in test_values]
    bar_colors = []
    for i, r in enumerate(results):
        if abs(r["value"] - current_val) < 0.01:
            bar_colors.append("#e0e0e0")
        else:
            bar_colors.append("#404040")

    fig_eq = go.Figure(go.Bar(
        x=labels, y=eq_values, marker_color=bar_colors,
        text=[f"${v/1_000_000:,.1f}M" for v in eq_values],
        textposition="outside", textfont=dict(size=10, color="#888"),
        hovertemplate="%{x}: $%{y:,.0f}<extra></extra>",
    ))
    fig_eq.update_layout(
        title=f"Equity Value (DCF) by {alpha_metric}",
        yaxis_title="Equity Value ($)",
        template="plotly_dark", height=380,
        margin=dict(l=50, r=16, t=32, b=36),
        font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,10,10,1)",
        yaxis=dict(gridcolor="#1a1a1a"),
    )
    st.plotly_chart(fig_eq, use_container_width=True)

    # Delta table
    st.markdown("### Impact Breakdown")
    import pandas as pd
    rows = []
    for r in results:
        delta = r["equity"] - base_equity
        pct = (delta / abs(base_equity) * 100) if base_equity != 0 else 0
        is_current = abs(r["value"] - current_val) < 0.01
        label = f"{unit}{r['value']:,.0f}" if unit == "$" else f"{r['value']:g}{unit}"
        rows.append({
            "": "→" if is_current else "",
            alpha_metric: label,
            "Active Customers": f"{r['active']:,.0f}",
            "Monthly Revenue": f"${r['monthly_rev']:,.0f}",
            "Monthly FCF": f"${r['monthly_fcf']:,.0f}",
            "Equity Value": f"${r['equity']:,.0f}",
            "Delta": f"${delta:+,.0f}",
            "Change": f"{pct:+.0f}%",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # The punchline — find lowest and highest, compute the full range delta
    if len(results) >= 2:
        low = results[0]
        high = results[-1]
        delta = high["equity"] - low["equity"]
        low_label = f"{unit}{low['value']:,.0f}" if unit == "$" else f"{low['value']:g}{unit}"
        high_label = f"{unit}{high['value']:,.0f}" if unit == "$" else f"{high['value']:g}{unit}"
        direction = "increasing" if delta > 0 else "decreasing"
        st.markdown(f"""
---
**The takeaway:** Moving **{alpha_metric.lower()}** from **{low_label}** to **{high_label}** 
{"creates" if delta > 0 else "destroys"} **${abs(delta)/1_000_000:,.1f}M** in equity value over {alpha_years} — 
a **{abs(delta / low['equity'] * 100) if low['equity'] != 0 else 0:,.0f}%** change from the low end.
""")

with tab_cust:
    st.plotly_chart(add_cursor(customers_chart(daily), cursor_day), use_container_width=True)
    st.plotly_chart(add_cursor(new_customers_by_channel(daily), cursor_day), use_container_width=True)

with tab_rev:
    st.plotly_chart(add_cursor(revenue_chart(daily), cursor_day), use_container_width=True)
    st.plotly_chart(add_cursor(cash_collected_chart(daily), cursor_day), use_container_width=True)

with tab_costs:
    st.plotly_chart(add_cursor(cost_breakdown_chart(daily), cursor_day), use_container_width=True)

with tab_pnl:
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(add_cursor(pnl_chart(daily), cursor_day), use_container_width=True)
    with col2:
        st.plotly_chart(add_cursor(fcf_chart(daily), cursor_day), use_container_width=True)
    st.plotly_chart(add_cursor(cash_balance_chart(daily), cursor_day), use_container_width=True)

with tab_sens:
    render_sensitivity(inp)

with tab_compare:
    render_scenario_comparison(inp)

with tab_export:
    render_export(inp, kpis, val, monthly)

# ── Raw Data ────────────────────────────────────────────────────────
with st.expander("Monthly Data Table"):
    st.dataframe(monthly, use_container_width=True, height=400)
