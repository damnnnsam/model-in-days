"""
Standalone model viewer — business valuation dashboard.

Extracted from model_1_linear/app.py. Renders the full valuation view
for a single ModelInputs: hero chart, KPIs, calculation audit trail,
GTM Alpha, charts, sensitivity, and export.
"""
from __future__ import annotations

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from engine.inputs import ModelInputs
from engine.simulation import run_simulation, to_monthly, to_daily_df
from engine.valuation import compute_valuation
from engine.metrics import compute_kpis
from ui.charts import (
    COLORS, DAILY_LAYOUT,
    customers_chart, new_customers_by_channel,
    revenue_chart, cash_collected_chart,
    cost_breakdown_chart, pnl_chart, cash_balance_chart,
    fcf_chart, valuation_waterfall, add_cursor, hero_chart,
)
from ui.dashboard import (
    render_kpi_cards, render_valuation_panel, render_sensitivity,
    render_scenario_comparison, render_export,
)


def _fd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:,.1f}K"
    return f"${v:,.0f}"


def render_model_view(inp: ModelInputs, model_name: str = "Model") -> None:
    """Render the full standalone model view for a given ModelInputs."""

    sim = run_simulation(inp)
    daily = to_daily_df(sim)
    monthly = to_monthly(sim)
    val = compute_valuation(inp, sim)

    # ── Hero chart ─────────────────────────────────────────────────
    total_days = inp.time_max
    st.plotly_chart(hero_chart(daily, cursor_day=None), use_container_width=True)

    # ── Time cursor ────────────────────────────────────────────────
    col_slider, col_label = st.columns([5, 1])
    with col_slider:
        cursor_day = st.slider(
            "View metrics at day",
            min_value=1, max_value=total_days, value=total_days,
            key=f"mv_cursor_{model_name}",
        )
    with col_label:
        years = cursor_day / 365
        st.markdown(f"**≈ {years:.1f} years**")

    kpis = compute_kpis(inp, sim, at_day=cursor_day)
    render_kpi_cards(kpis)
    st.divider()

    # ── Tabs ───────────────────────────────────────────────────────
    tab_val, tab_calc, tab_alpha, tab_cust, tab_rev, tab_costs, tab_pnl, tab_sens, tab_compare, tab_export = st.tabs([
        "Valuation", "Calculations", "GTM Alpha", "Customers",
        "Revenue & Cash", "Costs", "P&L & FCF",
        "Sensitivity", "Compare Scenarios", "Export",
    ])

    with tab_val:
        render_valuation_panel(val, inp)
        st.divider()
        st.plotly_chart(
            valuation_waterfall(
                pv_fcf=val.pv_fcf, pv_terminal=val.pv_terminal_value,
                debt=inp.debt, cash=val.cash_at_valuation, equity=val.equity_value_dcf,
            ),
            use_container_width=True,
        )

    with tab_calc:
        _render_calculations(inp, sim, val, cursor_day)

    with tab_alpha:
        _render_gtm_alpha(inp, sim, val)

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

    with st.expander("Monthly Data Table"):
        st.dataframe(monthly, use_container_width=True, height=400)


# ── Calculation audit trail ────────────────────────────────────────────

def _render_calculations(inp: ModelInputs, sim, val, cursor_day: int) -> None:
    """Full calculation audit trail at a given day."""
    st.markdown("Every number, every formula, every step. Verify anything.")

    d = min(cursor_day - 1, len(sim.days) - 1)
    prev = max(d - 1, 0)
    trail_start = max(0, d - 29)
    contract_len = max(inp.contract_length, 1)
    delay_ob = inp.time_to_market_outbound + inp.time_to_sell
    delay_in = inp.time_to_market_inbound + inp.time_to_sell

    # Step 0: Full trace
    st.markdown(f"### 0. Full Simulation Trace — Day {cursor_day}")
    lead_source_day_ob = d - delay_ob
    lead_source_day_in = d - delay_in
    ob_leads = (inp.contacts_per_month / 30) * (inp.outbound_conversion_rate / 100) if inp.use_outbound and lead_source_day_ob >= 0 else 0
    in_leads = 0
    if inp.use_inbound and inp.cpm > 0 and lead_source_day_in >= 0:
        in_leads = ((inp.media_spend / inp.cpm) * 1000 / 30) * (inp.ctr / 100) * (inp.funnel_conversion_rate / 100)

    st.code(f"""STEP 1: NEW CUSTOMER ARRIVALS ON DAY {cursor_day}
────────────────────────────────────────────────────
{"OUTBOUND:" if inp.use_outbound else "OUTBOUND: (disabled)"}
  Leads generated on day {max(lead_source_day_ob, 0)} (today - {delay_ob} days)
  leads_that_day       = {ob_leads:.2f}
  customers_from_ob    = {sim.new_customers_outbound[d]:.4f}
{"" if not inp.use_inbound else f"""
INBOUND:
  Leads generated on day {max(lead_source_day_in, 0)} (today - {delay_in} days)
  leads_that_day       = {in_leads:.2f}
  customers_from_in    = {sim.new_customers_inbound[d]:.4f}
"""}{"" if not inp.use_viral else f"""VIRAL:
  customers_from_viral = {sim.new_customers_viral[d]:.4f}
"""}
  TOTAL NEW TODAY       = {sim.new_customers_total[d]:.4f}""", language=None)

    # Step 2: Churn & renewals
    expire_day = d - contract_len
    if expire_day >= 0:
        expired_cohort_size = sim.new_customers_total[expire_day]
        refunded_from_cohort = expired_cohort_size * (inp.refund_rate / 100)
        remaining = expired_cohort_size - refunded_from_cohort
        churned_today = remaining * (inp.churn_rate / 100)
        renewed_today = remaining * (1 - inp.churn_rate / 100)
    else:
        expired_cohort_size = churned_today = renewed_today = 0

    st.code(f"""STEP 2: CHURN & RENEWALS ON DAY {cursor_day}
────────────────────────────────────────────────────
  Contract length = {contract_len} days
  Cohort expiring = day {max(expire_day, 0)}
  {"(no cohort expires — too early)" if expire_day < 0 else f"""
  cohort_size          = {expired_cohort_size:.4f}
  churned              = {churned_today:.4f}
  renewed              = {renewed_today:.4f}"""}""", language=None)

    # Step 3: Active customers
    st.code(f"""STEP 3: ACTIVE CUSTOMER COUNT
────────────────────────────────────────────────────
  active_yesterday     = {sim.active_customers[prev]:.1f}
  + new_today          = {sim.new_customers_total[d]:.4f}
  - churned            = {churned_today:.4f}
  = active_today       = {sim.active_customers[d]:.1f}
  (cumulative          = {sim.cumulative_customers[d]:.1f})""", language=None)

    # Step 4: Revenue
    st.code(f"""STEP 4: REVENUE ON DAY {cursor_day}
────────────────────────────────────────────────────
  revenue_new          = ${sim.revenue_new[d]:,.2f}
  revenue_renewal      = ${sim.revenue_renewal[d]:,.2f}
  cash_collected_total = ${sim.cash_collected_total[d]:,.2f}""", language=None)

    # Step 5: Costs
    st.code(f"""STEP 5: COSTS ON DAY {cursor_day}
────────────────────────────────────────────────────
  Marketing            = ${sim.cost_marketing[d]:,.2f}
  Sales                = ${sim.cost_sales[d]:,.2f}
  Fulfillment          = ${sim.cost_fulfillment[d]:,.2f}
  Fixed                = ${sim.cost_fixed[d]:,.2f}
  Transaction fees     = ${sim.cost_transaction_fees[d]:,.2f}
  Interest             = ${sim.cost_interest[d]:,.2f}
  Refunds              = ${sim.cost_refunds[d]:,.2f}
  TOTAL                = ${sim.cost_total[d]:,.2f}""", language=None)

    # Step 6: P&L
    st.code(f"""STEP 6: P&L ON DAY {cursor_day}
────────────────────────────────────────────────────
  Gross Profit         ${sim.gross_profit[d]:>12,.2f}
  EBITDA               ${sim.ebitda[d]:>12,.2f}
  Net Income           ${sim.net_income[d]:>12,.2f}
  Free Cash Flow       ${sim.free_cash_flow[d]:>12,.2f}
  Cumulative FCF       ${sim.cumulative_fcf[d]:>12,.2f}
  Cash Balance         ${sim.cash_balance[d]:>12,.2f}""", language=None)

    # Trailing 30 days
    st.code(f"""TRAILING 30 DAYS (day {trail_start + 1} to {d + 1}):
  revenue              = ${float(sum(sim.revenue_total[trail_start:d + 1])):>12,.0f}
  cash collected       = ${float(sum(sim.cash_collected_total[trail_start:d + 1])):>12,.0f}
  FCF                  = ${float(sum(sim.free_cash_flow[trail_start:d + 1])):>12,.0f}
  new customers        = {float(sum(sim.new_customers_total[trail_start:d + 1])):>12.1f}""", language=None)

    st.markdown("---")

    # Channel math
    st.markdown("### 1. Customer Acquisition")
    if inp.use_outbound:
        contacts_day = inp.contacts_per_month / 30
        leads_day = contacts_day * (inp.outbound_conversion_rate / 100)
        custs_day = leads_day * (inp.lead_conversion_rate_outbound / 100)
        delay = inp.time_to_market_outbound + inp.time_to_sell
        st.markdown("**Outbound**")
        st.code(f"""contacts/day     = {contacts_day:,.1f}
leads/day        = {leads_day:,.2f}
customers/day    = {custs_day:,.4f}  ({custs_day * 30:,.1f}/month)
delay            = {delay} days""", language=None)

    if inp.use_inbound and inp.cpm > 0:
        imp_day = (inp.media_spend / inp.cpm) * 1000 / 30
        clicks_day = imp_day * (inp.ctr / 100)
        leads_day_in = clicks_day * (inp.funnel_conversion_rate / 100)
        custs_day_in = leads_day_in * (inp.lead_conversion_rate_inbound / 100)
        delay_in_val = inp.time_to_market_inbound + inp.time_to_sell
        st.markdown("**Inbound**")
        st.code(f"""impressions/day  = {imp_day:,.0f}
clicks/day       = {clicks_day:,.1f}
leads/day        = {leads_day_in:,.2f}
customers/day    = {custs_day_in:,.4f}  ({custs_day_in * 30:,.1f}/month)
delay            = {delay_in_val} days""", language=None)

    if inp.use_viral:
        k = inp.invites_per_customer * (inp.conversion_rate_per_invite / 100)
        st.markdown("**Viral**")
        st.code(f"""K value = {k:.3f}  {"(exponential)" if k > 1 else "(decaying)"}
viral starts day {inp.viral_start}, delay = {inp.viral_time + inp.time_to_sell} days""", language=None)

    # Revenue per customer
    st.markdown("### 2. Revenue Per Customer")
    rev_collected = inp.price_of_offer * (inp.realization_rate / 100)
    fulfill_cost = inp.price_of_offer * (inp.cost_to_fulfill / 100)
    sales_cost = inp.price_of_offer * (inp.cost_to_sell / 100)
    txn_cost = rev_collected * (inp.transaction_fee / 100)
    contribution = rev_collected - fulfill_cost - sales_cost - txn_cost
    st.code(f"""revenue_collected = ${rev_collected:,.0f}
- fulfillment     = ${fulfill_cost:,.0f}
- sales           = ${sales_cost:,.0f}
- transaction     = ${txn_cost:,.0f}
= contribution    = ${contribution:,.0f}

cash collected over {inp.time_to_collect} days""", language=None)

    # LTV
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
    exp_ren = p_first * ren_val / (1 - p_sub) if 0 < p_sub < 1 else p_first * ren_val
    ltv = first_val + exp_ren
    st.code(f"""first_purchase = ${first_val:,.0f}
expected_renewals = ${exp_ren:,.0f}
LTV = ${ltv:,.0f}""", language=None)

    # CAC
    st.markdown("### 4. CAC")
    total_mkt = float(sum(sim.cost_marketing))
    total_sal = float(sum(sim.cost_sales))
    total_custs = float(sum(sim.new_customers_total))
    cac = (total_mkt + total_sal) / max(total_custs, 1)
    st.code(f"""CAC (blended) = ${cac:,.0f}
LTV / CAC     = {ltv / max(cac, 1):.1f}x""", language=None)

    # DCF
    st.markdown("### 5. DCF Valuation")
    st.code(f"""PV of FCF        = ${val.pv_fcf:,.0f}
Terminal Value   = ${val.terminal_value:,.0f}
PV of Terminal   = ${val.pv_terminal_value:,.0f}
Enterprise Value = ${val.enterprise_value_dcf:,.0f}
Equity Value     = ${val.equity_value_dcf:,.0f}
Share Price      = ${val.share_price_dcf:,.2f}
TV as % of EV    = {val.pv_terminal_value / max(val.enterprise_value_dcf, 1) * 100:.0f}%""", language=None)


# ── GTM Alpha ──────────────────────────────────────────────────────────

def _render_gtm_alpha(inp: ModelInputs, sim, val) -> None:
    """Stress-test a single metric and see how it shifts equity value."""
    st.markdown("<span style='color:#666;font-size:13px'>Stress-test a single metric.</span>", unsafe_allow_html=True)

    ac1, ac2 = st.columns(2)
    with ac1:
        alpha_metric = st.selectbox("Metric to stress-test", [
            "Reply rate (contact → lead %)",
            "Lead → customer rate (%)",
            "Sends per month",
            "Price of offer ($)",
            "Churn rate (%)",
            "Cost to fulfill (%)",
        ], key="mv_alpha_metric")
    with ac2:
        alpha_years = st.selectbox("Evaluate equity at", [
            "3 years", "5 years", "7 years",
        ], index=1, key="mv_alpha_years")

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
        test_inp = ModelInputs(**p)
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

    eq_values = [r["equity"] for r in results]
    labels = [f"{unit}{v:,.0f}" if unit == "$" else f"{v:g}{unit}" for v in test_values]
    bar_colors = ["#e0e0e0" if abs(r["value"] - current_val) < 0.01 else "#404040" for r in results]

    fig_eq = go.Figure(go.Bar(
        x=labels, y=eq_values, marker_color=bar_colors,
        text=[f"${v / 1_000_000:,.1f}M" for v in eq_values],
        textposition="outside", textfont=dict(size=10, color="#888"),
        hovertemplate="%{x}: $%{y:,.0f}<extra></extra>",
    ))
    fig_eq.update_layout(
        title=f"Equity Value (DCF) by {alpha_metric}",
        yaxis_title="Equity Value ($)",
        template="plotly_dark", height=380,
        margin=dict(l=50, r=16, t=32, b=36),
        font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,10,10,1)",
        yaxis=dict(gridcolor="#1a1a1a"),
    )
    st.plotly_chart(fig_eq, use_container_width=True)

    # Delta table
    st.markdown("### Impact Breakdown")
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

    if len(results) >= 2:
        low, high = results[0], results[-1]
        delta = high["equity"] - low["equity"]
        low_label = f"{unit}{low['value']:,.0f}" if unit == "$" else f"{low['value']:g}{unit}"
        high_label = f"{unit}{high['value']:,.0f}" if unit == "$" else f"{high['value']:g}{unit}"
        st.markdown(f"""---
**The takeaway:** Moving **{alpha_metric.lower()}** from **{low_label}** to **{high_label}**
{"creates" if delta > 0 else "destroys"} **${abs(delta) / 1_000_000:,.1f}M** in equity value over {alpha_years}.""")
