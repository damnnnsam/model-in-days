"""
Side-by-side model comparison — no deal or compensation, just business economics.

Select 2 models and see KPI deltas, charts overlay, and field differences.
"""
from __future__ import annotations

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from engine.inputs import ModelInputs
from engine.simulation import run_simulation, to_daily_df
from engine.valuation import compute_valuation
from engine.metrics import compute_kpis
from ui.charts import COLORS

from store.model import list_models, resolve_model
from store.serialization import compute_overrides


def _fd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:,.1f}K"
    return f"${v:,.0f}"


def render_model_comparison(client_slug: str) -> None:
    """Render side-by-side comparison of two models."""
    st.markdown("## Compare Models")
    st.caption("Compare two business scenarios — no compensation, just economics.")

    models = list_models(client_slug)
    if len(models) < 2:
        st.warning("Need at least 2 models to compare.")
        return

    model_options = {slug: mf.name for slug, mf in models}
    slugs = list(model_options.keys())

    col1, col2 = st.columns(2)
    with col1:
        model_a = st.selectbox("Model A", slugs,
                               format_func=lambda s: model_options[s],
                               key="mc_model_a")
    with col2:
        model_b = st.selectbox("Model B", slugs,
                               format_func=lambda s: model_options[s],
                               index=min(1, len(slugs) - 1),
                               key="mc_model_b")

    if model_a == model_b:
        st.info("Select two different models to compare.")
        return

    st.markdown("---")

    # Resolve and compute
    inp_a = resolve_model(client_slug, model_a)
    inp_b = resolve_model(client_slug, model_b)

    sim_a = run_simulation(inp_a)
    sim_b = run_simulation(inp_b)
    val_a = compute_valuation(inp_a, sim_a)
    val_b = compute_valuation(inp_b, sim_b)
    kpis_a = compute_kpis(inp_a, sim_a)
    kpis_b = compute_kpis(inp_b, sim_b)

    name_a = model_options[model_a]
    name_b = model_options[model_b]

    # ── Input differences ──────────────────────────────────────────
    deltas = compute_overrides(inp_a, inp_b)
    with st.expander(f"Input differences ({len(deltas)} fields)", expanded=True):
        if deltas:
            rows = []
            for k, v in deltas.items():
                rows.append({
                    "Field": k,
                    name_a: getattr(inp_a, k),
                    name_b: v,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Models have identical inputs.")

    # ── KPI comparison ─────────────────────────────────────────────
    st.markdown("### Key Metrics")

    metrics = [
        ("Equity (DCF)", val_a.equity_value_dcf, val_b.equity_value_dcf, True),
        ("Equity (EBITDA)", val_a.equity_value_ebitda, val_b.equity_value_ebitda, True),
        ("Monthly Revenue", kpis_a.monthly_revenue, kpis_b.monthly_revenue, True),
        ("Monthly FCF", kpis_a.monthly_fcf, kpis_b.monthly_fcf, True),
        ("Active Customers", kpis_a.active_customers, kpis_b.active_customers, False),
        ("CAC (Blended)", kpis_a.cac_blended, kpis_b.cac_blended, True),
        ("LTV", kpis_a.ltv, kpis_b.ltv, True),
        ("LTV/CAC", kpis_a.ltv_cac_ratio, kpis_b.ltv_cac_ratio, False),
        ("Time to Profit (days)", kpis_a.time_to_profitability_days, kpis_b.time_to_profitability_days, False),
        ("Cash Needed", kpis_a.cash_needed, kpis_b.cash_needed, True),
        ("Gross Margin", kpis_a.gross_margin, kpis_b.gross_margin, False),
        ("EBITDA Margin", kpis_a.ebitda_margin, kpis_b.ebitda_margin, False),
    ]

    rows = []
    for label, va, vb, is_dollar in metrics:
        fmt = _fd if is_dollar else lambda x: f"{x:,.1f}"
        delta = vb - va
        pct = (delta / abs(va) * 100) if va != 0 else 0
        rows.append({
            "Metric": label,
            name_a: fmt(va),
            name_b: fmt(vb),
            "Delta": fmt(delta) if is_dollar else f"{delta:+,.1f}",
            "Change": f"{pct:+.0f}%",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Charts ─────────────────────────────────────────────────────
    st.markdown("### Charts")

    chart_layout = dict(
        template="plotly_dark", height=350,
        margin=dict(l=50, r=16, t=40, b=36),
        font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,10,10,1)",
        xaxis=dict(title="Day", gridcolor="#1a1a1a"),
        legend=dict(orientation="h", y=1.1),
    )

    days = sim_a.days

    # FCF
    fig_fcf = go.Figure()
    fig_fcf.add_trace(go.Scatter(x=days, y=sim_a.free_cash_flow, name=name_a,
                                  line=dict(color=COLORS["sky"], width=2)))
    fig_fcf.add_trace(go.Scatter(x=days, y=sim_b.free_cash_flow, name=name_b,
                                  line=dict(color=COLORS["green"], width=2)))
    fig_fcf.update_layout(title="Daily Free Cash Flow", yaxis=dict(title="FCF ($)", gridcolor="#1a1a1a"), **chart_layout)
    st.plotly_chart(fig_fcf, use_container_width=True)

    # Active customers
    fig_cust = go.Figure()
    fig_cust.add_trace(go.Scatter(x=days, y=sim_a.active_customers, name=name_a,
                                   line=dict(color=COLORS["sky"], width=2)))
    fig_cust.add_trace(go.Scatter(x=days, y=sim_b.active_customers, name=name_b,
                                   line=dict(color=COLORS["green"], width=2)))
    fig_cust.update_layout(title="Active Customers", yaxis=dict(title="Customers", gridcolor="#1a1a1a"), **chart_layout)
    st.plotly_chart(fig_cust, use_container_width=True)

    # Cash balance
    fig_cash = go.Figure()
    fig_cash.add_trace(go.Scatter(x=days, y=sim_a.cash_balance, name=name_a,
                                   line=dict(color=COLORS["sky"], width=2)))
    fig_cash.add_trace(go.Scatter(x=days, y=sim_b.cash_balance, name=name_b,
                                   line=dict(color=COLORS["green"], width=2)))
    fig_cash.update_layout(title="Cash Balance", yaxis=dict(title="Cash ($)", gridcolor="#1a1a1a"), **chart_layout)
    st.plotly_chart(fig_cash, use_container_width=True)

    # Cumulative revenue
    fig_rev = go.Figure()
    fig_rev.add_trace(go.Scatter(x=days, y=np.cumsum(sim_a.cash_collected_total), name=name_a,
                                  line=dict(color=COLORS["sky"], width=2)))
    fig_rev.add_trace(go.Scatter(x=days, y=np.cumsum(sim_b.cash_collected_total), name=name_b,
                                  line=dict(color=COLORS["green"], width=2)))
    fig_rev.update_layout(title="Cumulative Cash Collected", yaxis=dict(title="Cash ($)", gridcolor="#1a1a1a"), **chart_layout)
    st.plotly_chart(fig_rev, use_container_width=True)
