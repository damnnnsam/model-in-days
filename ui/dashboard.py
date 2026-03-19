from __future__ import annotations

import json
import streamlit as st
import numpy as np
import pandas as pd

from engine.inputs import ModelInputs
from engine.metrics import KPIMetrics, compute_kpis
from engine.valuation import ValuationResult
from engine.simulation import SimulationResult, run_simulation, to_monthly, to_daily_df
from engine.valuation import compute_valuation


def _fmt_dollar(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:,.1f}K"
    return f"${v:,.0f}"


def _fmt_number(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:,.1f}K"
    return f"{v:,.0f}"


def render_kpi_cards(kpis: KPIMetrics) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Customers", _fmt_number(kpis.active_customers))
    c2.metric("Monthly Revenue", _fmt_dollar(kpis.monthly_revenue))
    c3.metric("Monthly FCF", _fmt_dollar(kpis.monthly_fcf))
    ttp_label = f"{kpis.time_to_profitability_months} months" if kpis.time_to_profitability_months > 0 else "Never"
    c4.metric("Time to Profitability", ttp_label)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("CAC (Blended)", _fmt_dollar(kpis.cac_blended))
    c6.metric("LTV", _fmt_dollar(kpis.ltv))
    c7.metric("LTV / CAC", f"{kpis.ltv_cac_ratio:.1f}x")
    c8.metric("Payback Period", f"{kpis.payback_period_days:.0f} days")

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Profit / Customer / Month", _fmt_dollar(kpis.profit_per_customer_per_month))
    c10.metric("Cash Needed", _fmt_dollar(kpis.cash_needed))
    c11.metric("Gross Margin", f"{kpis.gross_margin:.1f}%")
    c12.metric("EBITDA Margin", f"{kpis.ebitda_margin:.1f}%")

    c13, c14, c15, c16 = st.columns(4)
    c13.metric("Net Margin", f"{kpis.net_margin:.1f}%")
    c14.metric("Monthly New Customers", _fmt_number(kpis.monthly_new_customers))
    c15.metric("Total Customers (All Time)", _fmt_number(kpis.total_customers))
    c16.metric("K Value (Viral)", f"{kpis.k_value:.2f}")


def render_valuation_panel(val: ValuationResult, inp: ModelInputs) -> None:
    st.subheader("Valuation Summary")

    col_dcf, col_ebitda = st.columns(2)

    with col_dcf:
        st.markdown("**DCF Method**")
        st.metric("Enterprise Value (DCF)", _fmt_dollar(val.enterprise_value_dcf))
        st.metric("Equity Value (DCF)", _fmt_dollar(val.equity_value_dcf))
        st.metric("Share Price (DCF)", f"${val.share_price_dcf:,.2f}")
        st.caption(f"PV of FCF: {_fmt_dollar(val.pv_fcf)}")
        st.caption(f"Terminal Value: {_fmt_dollar(val.terminal_value)}")
        st.caption(f"PV of Terminal Value: {_fmt_dollar(val.pv_terminal_value)}")

    with col_ebitda:
        st.markdown("**EBITDA Multiple Method**")
        st.metric("Enterprise Value (EBITDA)", _fmt_dollar(val.enterprise_value_ebitda))
        st.metric("Equity Value (EBITDA)", _fmt_dollar(val.equity_value_ebitda))
        st.metric("Share Price (EBITDA)", f"${val.share_price_ebitda:,.2f}")
        st.caption(f"Trailing 12M EBITDA: {_fmt_dollar(val.trailing_ebitda)}")
        st.caption(f"Multiple: {inp.enterprise_multiple_ebitda:.1f}x")

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Net Debt", _fmt_dollar(val.net_debt))
    c2.metric("Cash at Valuation Point", _fmt_dollar(val.cash_at_valuation))
    c3.metric("Shares Outstanding", _fmt_number(inp.number_of_shares))


def render_sensitivity(inp: ModelInputs) -> None:
    st.subheader("Sensitivity Analysis")
    st.caption("How equity value (DCF) changes with key assumptions.")

    col1, col2 = st.columns(2)
    with col1:
        row_param = st.selectbox("Row Variable", [
            "discount_rate", "churn_rate", "media_spend", "cpm",
            "price_of_offer", "cost_to_sell", "cost_to_fulfill",
            "lead_conversion_rate_inbound", "funnel_conversion_rate",
        ], index=0, key="sens_row")
    with col2:
        col_param = st.selectbox("Column Variable", [
            "churn_rate", "discount_rate", "media_spend", "cpm",
            "price_of_offer", "cost_to_sell", "cost_to_fulfill",
            "lead_conversion_rate_inbound", "perpetual_growth_rate",
        ], index=0, key="sens_col")

    base_row = getattr(inp, row_param)
    base_col = getattr(inp, col_param)

    # Generate 5 values around the base
    if base_row > 0:
        row_vals = [base_row * m for m in [0.5, 0.75, 1.0, 1.25, 1.5]]
    else:
        row_vals = [0, 1, 2, 5, 10]

    if base_col > 0:
        col_vals = [base_col * m for m in [0.5, 0.75, 1.0, 1.25, 1.5]]
    else:
        col_vals = [0, 1, 2, 5, 10]

    z_matrix = []
    for rv in row_vals:
        row_results = []
        for cv in col_vals:
            params = inp.__dict__.copy()
            params[row_param] = rv
            params[col_param] = cv
            test_inp = ModelInputs(**params)
            sim = run_simulation(test_inp)
            val = compute_valuation(test_inp, sim)
            row_results.append(val.equity_value_dcf)
        z_matrix.append(row_results)

    from ui.charts import sensitivity_heatmap
    fig = sensitivity_heatmap(
        row_values=row_vals,
        col_values=col_vals,
        z_matrix=z_matrix,
        row_label=row_param,
        col_label=col_param,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_scenario_comparison(inp_a: ModelInputs) -> None:
    st.subheader("Scenario Comparison")
    st.caption("Save current inputs as Scenario A, tweak values below to create Scenario B, and compare.")

    if st.button("Save current inputs as Scenario A", key="save_a"):
        st.session_state["scenario_a"] = json.dumps(inp_a.__dict__, default=str)
        st.success("Scenario A saved.")

    if "scenario_a" not in st.session_state:
        st.info("Click the button above to save your current inputs as Scenario A, then adjust the sidebar and come back here.")
        return

    a_params = json.loads(st.session_state["scenario_a"])
    # Restore types
    for k, v in a_params.items():
        field_type = type(getattr(ModelInputs, k, v))
        if field_type == int:
            a_params[k] = int(v)
        elif field_type == float:
            a_params[k] = float(v)
        elif field_type == bool:
            a_params[k] = bool(v)
    inp_saved = ModelInputs(**a_params)

    # Current sidebar is Scenario B
    inp_b = inp_a

    # Run both
    sim_a = run_simulation(inp_saved)
    daily_a = to_daily_df(sim_a)
    kpis_a = compute_kpis(inp_saved, sim_a)
    val_a = compute_valuation(inp_saved, sim_a)

    sim_b = run_simulation(inp_b)
    daily_b = to_daily_df(sim_b)
    kpis_b = compute_kpis(inp_b, sim_b)
    val_b = compute_valuation(inp_b, sim_b)

    # Delta summary
    st.markdown("---")
    st.markdown("### Valuation Delta")
    dc1, dc2, dc3 = st.columns(3)

    ev_delta = val_b.equity_value_dcf - val_a.equity_value_dcf
    ev_pct = (ev_delta / abs(val_a.equity_value_dcf) * 100) if val_a.equity_value_dcf != 0 else 0
    dc1.metric(
        "Equity Value (DCF)",
        _fmt_dollar(val_b.equity_value_dcf),
        delta=f"{_fmt_dollar(ev_delta)} ({ev_pct:+.1f}%)",
    )

    ev_eb_delta = val_b.equity_value_ebitda - val_a.equity_value_ebitda
    ev_eb_pct = (ev_eb_delta / abs(val_a.equity_value_ebitda) * 100) if val_a.equity_value_ebitda != 0 else 0
    dc2.metric(
        "Equity Value (EBITDA)",
        _fmt_dollar(val_b.equity_value_ebitda),
        delta=f"{_fmt_dollar(ev_eb_delta)} ({ev_eb_pct:+.1f}%)",
    )

    sp_delta = val_b.share_price_dcf - val_a.share_price_dcf
    dc3.metric(
        "Share Price (DCF)",
        f"${val_b.share_price_dcf:,.2f}",
        delta=f"${sp_delta:+,.2f}",
    )

    # KPI comparison
    st.markdown("### Key Metrics Comparison")
    kpi_data = {
        "Metric": [
            "Time to Profitability", "Cash Needed", "Profit / Cust / Month",
            "CAC (Blended)", "LTV", "LTV/CAC", "EBITDA Margin",
        ],
        "Scenario A": [
            f"{kpis_a.time_to_profitability_months} mo" if kpis_a.time_to_profitability_months > 0 else "Never",
            _fmt_dollar(kpis_a.cash_needed),
            _fmt_dollar(kpis_a.profit_per_customer_per_month),
            _fmt_dollar(kpis_a.cac_blended),
            _fmt_dollar(kpis_a.ltv),
            f"{kpis_a.ltv_cac_ratio:.1f}x",
            f"{kpis_a.ebitda_margin:.1f}%",
        ],
        "Scenario B (Current)": [
            f"{kpis_b.time_to_profitability_months} mo" if kpis_b.time_to_profitability_months > 0 else "Never",
            _fmt_dollar(kpis_b.cash_needed),
            _fmt_dollar(kpis_b.profit_per_customer_per_month),
            _fmt_dollar(kpis_b.cac_blended),
            _fmt_dollar(kpis_b.ltv),
            f"{kpis_b.ltv_cac_ratio:.1f}x",
            f"{kpis_b.ebitda_margin:.1f}%",
        ],
    }
    st.dataframe(pd.DataFrame(kpi_data), use_container_width=True, hide_index=True)

    # Overlay charts
    from ui.charts import scenario_comparison_chart

    chart_options = [
        ("cash_balance", "Cash Balance", "$"),
        ("free_cash_flow", "Free Cash Flow", "$"),
        ("cumulative_fcf", "Cumulative FCF", "$"),
        ("active_customers", "Active Customers", "Customers"),
        ("ebitda", "EBITDA", "$"),
        ("cash_collected_total", "Cash Collected", "$"),
    ]
    for col_name, title, y_title in chart_options:
        fig = scenario_comparison_chart(
            daily_a, daily_b, col_name, title,
            label_a="Scenario A", label_b="Scenario B (Current)",
            y_title=y_title,
        )
        st.plotly_chart(fig, use_container_width=True)


def render_export(
    inp: ModelInputs,
    kpis: KPIMetrics,
    val: ValuationResult,
    monthly: pd.DataFrame,
) -> None:
    st.subheader("Export & Share")

    # JSON snapshot of all inputs
    inp_json = json.dumps(inp.__dict__, indent=2, default=str)
    st.download_button(
        "Download Inputs (JSON)",
        data=inp_json,
        file_name="model_inputs.json",
        mime="application/json",
        key="dl_inputs",
    )

    # CSV of monthly data
    csv = monthly.to_csv(index=False)
    st.download_button(
        "Download Monthly Data (CSV)",
        data=csv,
        file_name="model_monthly_data.csv",
        mime="text/csv",
        key="dl_csv",
    )

    # Summary report as text
    report_lines = [
        "FINANCIAL MODEL SUMMARY",
        "=" * 50,
        "",
        "KEY METRICS (Trailing 30 Days)",
        f"  Active Customers:           {kpis.active_customers:,.0f}",
        f"  Monthly Revenue:            ${kpis.monthly_revenue:,.0f}",
        f"  Monthly FCF:                ${kpis.monthly_fcf:,.0f}",
        f"  Profit / Customer / Month:  ${kpis.profit_per_customer_per_month:,.0f}",
        f"  Time to Profitability:      {kpis.time_to_profitability_months} months ({kpis.time_to_profitability_days} days)",
        f"  Cash Needed:                ${kpis.cash_needed:,.0f}",
        "",
        "UNIT ECONOMICS",
        f"  CAC (Blended):              ${kpis.cac_blended:,.0f}",
        f"  LTV:                        ${kpis.ltv:,.0f}",
        f"  LTV / CAC:                  {kpis.ltv_cac_ratio:.1f}x",
        f"  Payback Period:             {kpis.payback_period_days:.0f} days",
        f"  K Value (Viral):            {kpis.k_value:.2f}",
        "",
        "MARGINS",
        f"  Gross Margin:               {kpis.gross_margin:.1f}%",
        f"  EBITDA Margin:              {kpis.ebitda_margin:.1f}%",
        f"  Net Margin:                 {kpis.net_margin:.1f}%",
        "",
        "VALUATION — DCF METHOD",
        f"  PV of FCF:                  ${val.pv_fcf:,.0f}",
        f"  Terminal Value:             ${val.terminal_value:,.0f}",
        f"  PV of Terminal Value:       ${val.pv_terminal_value:,.0f}",
        f"  Enterprise Value:           ${val.enterprise_value_dcf:,.0f}",
        f"  Equity Value:               ${val.equity_value_dcf:,.0f}",
        f"  Share Price:                ${val.share_price_dcf:,.2f}",
        "",
        "VALUATION — EBITDA MULTIPLE",
        f"  Trailing 12M EBITDA:        ${val.trailing_ebitda:,.0f}",
        f"  Multiple:                   {inp.enterprise_multiple_ebitda:.1f}x",
        f"  Enterprise Value:           ${val.enterprise_value_ebitda:,.0f}",
        f"  Equity Value:               ${val.equity_value_ebitda:,.0f}",
        f"  Share Price:                ${val.share_price_ebitda:,.2f}",
        "",
        "=" * 50,
        "KEY INPUTS",
        f"  Price of Offer:             ${inp.price_of_offer:,.0f}",
        f"  Contract Length:            {inp.contract_length} days",
        f"  Churn Rate:                 {inp.churn_rate:.0f}%",
        f"  Cost to Sell:               {inp.cost_to_sell:.0f}%",
        f"  Cost to Fulfill:            {inp.cost_to_fulfill:.0f}%",
        f"  Media Spend:                ${inp.media_spend:,.0f}/mo" if inp.use_inbound else "",
        f"  CPM:                        ${inp.cpm:,.0f}" if inp.use_inbound else "",
        f"  CTR:                        {inp.ctr:.1f}%" if inp.use_inbound else "",
        f"  Funnel Conv Rate:           {inp.funnel_conversion_rate:.1f}%" if inp.use_inbound else "",
        f"  Lead→Customer (Inbound):    {inp.lead_conversion_rate_inbound:.1f}%" if inp.use_inbound else "",
        f"  Fixed Costs:                ${inp.fixed_costs_per_month:,.0f}/mo",
        f"  Tax Rate:                   {inp.tax_rate:.0f}%",
        f"  Discount Rate:              {inp.discount_rate:.1f}%",
    ]
    report = "\n".join(line for line in report_lines if line is not None)
    st.download_button(
        "Download Summary Report (TXT)",
        data=report,
        file_name="model_summary.txt",
        mime="text/plain",
        key="dl_report",
    )

    # Load saved inputs
    st.markdown("---")
    st.markdown("**Load saved inputs**")
    uploaded = st.file_uploader("Upload a model_inputs.json", type="json", key="upload_inputs")
    if uploaded is not None:
        try:
            loaded = json.loads(uploaded.read().decode())
            st.session_state["loaded_inputs"] = loaded
            st.success("Inputs loaded. Refresh the page to apply them.")
            st.json(loaded)
        except Exception as e:
            st.error(f"Failed to parse: {e}")
