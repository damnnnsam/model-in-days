"""
Side-by-side deal comparison for sales calls.

Supports 2-4 deals with table view (analytical) and card view (presentation).
"""
from __future__ import annotations

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from engine.inputs import ModelInputs
from engine.simulation import run_simulation
from engine.valuation import compute_valuation
from engine.metrics import compute_kpis
from model_2_operator.deal import DealTerms, compute_deal
from model_2_operator.compensation import CompensationStructure, compute_compensation
from ui.charts import COLORS

from store.model import resolve_model
from store.deal import list_deals, load_deal, get_compensation_structure, get_engagement_config


def _fd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:,.1f}K"
    return f"${v:,.0f}"


def _compute_deal_results(client_slug: str, deal_slug: str) -> dict | None:
    """Compute full results for a deal. Returns dict with all metrics or None on error."""
    from store.deal import load_deal
    deal_file = load_deal(client_slug, deal_slug)
    if deal_file is None:
        return None

    try:
        inp_before = resolve_model(client_slug, deal_file.before_model)
        inp_after = resolve_model(client_slug, deal_file.after_model)
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e), "name": deal_file.name}

    comp = get_compensation_structure(deal_file)
    eng = get_engagement_config(deal_file)

    sim_before = run_simulation(inp_before)
    sim_after = run_simulation(inp_after)
    val_before = compute_valuation(inp_before, sim_before)
    val_after = compute_valuation(inp_after, sim_after)

    # Build DealTerms
    _rs_basis_map = {"gross_revenue": "total_revenue", "gross_profit": "gross_profit"}
    deal_terms = DealTerms(
        revenue_share_pct=comp.rev_share_percentage if comp.rev_share_mode != "none" else 0.0,
        revenue_share_basis=_rs_basis_map.get(comp.rev_share_basis, "delta"),
        revenue_share_cap=comp.rev_share_cap_total,
        monthly_retainer=comp.retainer_amount,
        pay_per_close=comp.per_deal_amount,
        upfront_fee=comp.upfront_fee_amount,
        ramp_days=eng["ramp_days"],
        ramp_curve=eng["ramp_curve"],
        engagement_duration=eng["duration_days"],
        post_engagement_retention=eng["post_engagement"],
        decay_rate_days=eng.get("decay_rate_days", 180),
    )

    result = compute_deal(inp_before, inp_after, deal_terms, sim_before, sim_after, val_before, val_after)
    comp_result = compute_compensation(comp, sim_after, inp_after)

    # KPIs
    T = len(sim_after.days)
    op_cost_daily = np.zeros(T)
    n_months = comp_result.n_months
    for m in range(n_months):
        s, e = m * 30, min((m + 1) * 30, T)
        daily_val = comp_result.total_compensation[m] / max(e - s, 1)
        op_cost_daily[s:e] = daily_val

    kpis_before = compute_kpis(inp_before, sim_before)
    kpis_after = compute_kpis(inp_after, sim_after, operator_cost_daily=op_cost_daily)

    return {
        "name": deal_file.name,
        "slug": deal_slug,
        "notes": deal_file.notes,
        "before_model": deal_file.before_model,
        "after_model": deal_file.after_model,
        "result": result,
        "comp_result": comp_result,
        "comp": comp,
        "kpis_before": kpis_before,
        "kpis_after": kpis_after,
        "val_before": val_before,
        "val_after": val_after,
        "sim_before": sim_before,
        "sim_after": sim_after,
    }


def render_deal_comparison(client_slug: str, deal_slugs: list[str]) -> None:
    """Render side-by-side comparison of 2-4 deals."""
    st.markdown("## Deal Comparison")
    st.caption("Compare deal structures side by side. Optimized for sales calls.")

    # Select deals to compare
    all_deals = list_deals(client_slug)
    deal_options = {slug: df.name for slug, df in all_deals}

    if not deal_options:
        st.warning("No deals found for this client.")
        return

    selected = st.multiselect(
        "Select deals to compare (2-4)",
        options=list(deal_options.keys()),
        default=deal_slugs[:4],
        format_func=lambda s: deal_options.get(s, s),
        key="dc_select",
    )

    if len(selected) < 2:
        st.info("Select at least 2 deals to compare.")
        return

    selected = selected[:4]

    # Compute all deals
    results = []
    with st.spinner("Computing deal models..."):
        for slug in selected:
            r = _compute_deal_results(client_slug, slug)
            if r is not None:
                results.append(r)

    if len(results) < 2:
        st.error("Could not compute enough deals for comparison.")
        return

    # View toggle
    view_mode = st.radio("View", ["Table", "Cards"], horizontal=True, key="dc_view_mode")

    if view_mode == "Table":
        _render_table_view(results)
    else:
        _render_card_view(results)

    # Overlay charts (always shown)
    st.markdown("---")
    _render_overlay_charts(results)


def _render_table_view(results: list[dict]) -> None:
    """Dense comparison table."""
    st.markdown("### Comparison")

    rows = []
    metrics = [
        ("Operator Earned", lambda r: _fd(r["result"].operator_total_earned)),
        ("Avg Monthly", lambda r: _fd(r["result"].monthly_earnings_avg)),
        ("Client Net Gain", lambda r: _fd(r["result"].client_net_gain)),
        ("Client ROI", lambda r: f"{r['result'].client_roi:.1%}"),
        ("Break-Even Day", lambda r: f"{r['result'].break_even_day}" if r["result"].break_even_day >= 0 else "Never"),
        ("Equity Before", lambda r: _fd(r["val_before"].equity_value_dcf)),
        ("Equity After", lambda r: _fd(r["val_after"].equity_value_dcf)),
        ("Equity Delta", lambda r: _fd(r["result"].equity_delta)),
        ("Lifetime ROI", lambda r: f"{r['result'].lifetime_roi:.1%}"),
        ("Total Retainer", lambda r: _fd(r["comp_result"].total_retainer)),
        ("Total Rev Share", lambda r: _fd(r["comp_result"].total_rev_share)),
        ("Total Per-Deal", lambda r: _fd(r["comp_result"].total_per_deal)),
        ("Eff $/Customer", lambda r: _fd(r["result"].effective_rate_per_customer)),
        ("Eff RS Rate", lambda r: f"{r['comp_result'].effective_rev_share_rate:.1f}%"),
    ]

    for metric_name, extractor in metrics:
        row = {"Metric": metric_name}
        for r in results:
            if "error" in r:
                row[r["name"]] = "Error"
            else:
                row[r["name"]] = extractor(r)
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Highlight best
    valid = [r for r in results if "error" not in r]
    if valid:
        best_client = max(valid, key=lambda r: r["result"].client_net_gain)
        best_operator = max(valid, key=lambda r: r["result"].operator_total_earned)
        st.markdown(f"""
**Best for client:** {best_client['name']} (net gain {_fd(best_client['result'].client_net_gain)})
**Best for operator:** {best_operator['name']} (earned {_fd(best_operator['result'].operator_total_earned)})
""")


def _render_card_view(results: list[dict]) -> None:
    """Visual card layout — one column per deal."""
    cols = st.columns(len(results))

    for i, r in enumerate(results):
        with cols[i]:
            st.markdown(f"### {r['name']}")
            if "error" in r:
                st.error(r["error"])
                continue

            st.metric("Operator Earned", _fd(r["result"].operator_total_earned))
            st.metric("Client Net Gain", _fd(r["result"].client_net_gain))
            st.metric("Client ROI", f"{r['result'].client_roi:.0%}")
            be = r["result"].break_even_day
            st.metric("Break-Even", f"Day {be}" if be >= 0 else "Never")
            st.metric("Equity Delta", _fd(r["result"].equity_delta))
            st.metric("Lifetime ROI", f"{r['result'].lifetime_roi:.0%}")

            st.markdown("---")
            st.caption("Compensation Breakdown")
            st.markdown(f"""
- Retainer: {_fd(r['comp_result'].total_retainer)}
- Rev Share: {_fd(r['comp_result'].total_rev_share)}
- Per-Deal: {_fd(r['comp_result'].total_per_deal)}
- Upfront: {_fd(r['comp_result'].total_upfront)}
""")
            if r.get("notes"):
                st.caption(f"Notes: {r['notes']}")


def _render_overlay_charts(results: list[dict]) -> None:
    """Overlay charts comparing all deals."""
    valid = [r for r in results if "error" not in r]
    if not valid:
        return

    colors = [COLORS.get(c, "#888") for c in ["blue", "amber", "green", "red"]]

    # ROI curves
    st.markdown("### ROI Over Time")
    fig_roi = go.Figure()
    for i, r in enumerate(valid):
        days = r["result"].days
        fig_roi.add_trace(go.Scatter(
            x=days, y=r["result"].roi_curve,
            name=r["name"], line=dict(color=colors[i % len(colors)], width=2),
        ))
    fig_roi.add_hline(y=0, line_dash="dot", line_color="#555")
    fig_roi.update_layout(
        template="plotly_dark", height=350,
        margin=dict(l=50, r=16, t=32, b=36),
        font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,10,10,1)",
        yaxis=dict(title="Client ROI", tickformat=".0%", gridcolor="#1a1a1a"),
        xaxis=dict(title="Day", gridcolor="#1a1a1a"),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_roi, use_container_width=True)

    # Operator cumulative earnings
    st.markdown("### Operator Cumulative Earnings")
    fig_earn = go.Figure()
    for i, r in enumerate(valid):
        days = r["result"].days
        fig_earn.add_trace(go.Scatter(
            x=days, y=r["result"].operator_cumulative_earnings,
            name=r["name"], line=dict(color=colors[i % len(colors)], width=2),
        ))
    fig_earn.update_layout(
        template="plotly_dark", height=350,
        margin=dict(l=50, r=16, t=32, b=36),
        font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,10,10,1)",
        yaxis=dict(title="Cumulative ($)", gridcolor="#1a1a1a"),
        xaxis=dict(title="Day", gridcolor="#1a1a1a"),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_earn, use_container_width=True)

    # Client cumulative gain
    st.markdown("### Client Cumulative Gain")
    fig_gain = go.Figure()
    for i, r in enumerate(valid):
        days = r["result"].days
        fig_gain.add_trace(go.Scatter(
            x=days, y=r["result"].client_cumulative_gain,
            name=r["name"], line=dict(color=colors[i % len(colors)], width=2),
        ))
    fig_gain.add_hline(y=0, line_dash="dot", line_color="#555")
    fig_gain.update_layout(
        template="plotly_dark", height=350,
        margin=dict(l=50, r=16, t=32, b=36),
        font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,10,10,1)",
        yaxis=dict(title="Cumulative Gain ($)", gridcolor="#1a1a1a"),
        xaxis=dict(title="Day", gridcolor="#1a1a1a"),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_gain, use_container_width=True)
