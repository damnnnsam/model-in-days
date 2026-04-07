"""
Deal Builder view -- extracted display/computation logic from model_2_operator/app.py.

Renders the full deal modeling dashboard for pre-resolved ModelInputs and
compensation structure. No sidebar rendering -- the caller handles inputs.
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
from ui.charts import COLORS, DAILY_LAYOUT
from model_2_operator.deal import DealTerms, compute_deal
from model_2_operator.compensation import (
    CompensationStructure, compute_compensation,
)


def _fd(v: float) -> str:
    """Format a dollar value for display."""
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:,.1f}K"
    return f"${v:,.0f}"


def render_deal_view(
    inp_before: ModelInputs,
    inp_after: ModelInputs,
    comp: CompensationStructure,
    engagement: dict,  # {duration_days, ramp_days, ramp_curve, post_engagement, decay_rate_days}
) -> None:
    """Render the full deal builder dashboard.

    Parameters
    ----------
    inp_before : ModelInputs
        Business state before operator engagement.
    inp_after : ModelInputs
        Business state after operator engagement.
    comp : CompensationStructure
        Fully-specified compensation structure.
    engagement : dict
        Engagement timing parameters:
        - duration_days: int (0 = permanent)
        - ramp_days: int
        - ramp_curve: str ("linear" | "step")
        - post_engagement: str ("metrics_persist" | "metrics_decay" | "metrics_partial")
        - decay_rate_days: int
    """
    # ── Unpack engagement parameters ──
    d_duration = engagement.get("duration_days", 365)
    d_ramp = engagement.get("ramp_days", 60)
    d_ramp_curve = engagement.get("ramp_curve", "linear")
    d_post_eng = engagement.get("post_engagement", "metrics_persist")
    d_decay = engagement.get("decay_rate_days", 180)

    # ── Build DealTerms from comp + engagement ──
    _rs_basis_map = {"gross_revenue": "total_revenue", "gross_profit": "gross_profit"}
    deal = DealTerms(
        revenue_share_pct=comp.rev_share_percentage if comp.rev_share_mode != "none" else 0.0,
        revenue_share_basis=_rs_basis_map.get(comp.rev_share_basis, "delta"),
        revenue_share_cap=comp.rev_share_cap_total,
        monthly_retainer=comp.retainer_amount,
        pay_per_close=comp.per_deal_amount,
        upfront_fee=comp.upfront_fee_amount,
        bonuses=[],
        ramp_days=d_ramp,
        ramp_curve=d_ramp_curve,
        engagement_duration=d_duration,
        post_engagement_retention=d_post_eng,
        decay_rate_days=d_decay,
    )

    # ── Run computation chain ──
    sim_before = run_simulation(inp_before)
    sim_after = run_simulation(inp_after)
    val_before = compute_valuation(inp_before, sim_before)
    val_after = compute_valuation(inp_after, sim_after)
    result = compute_deal(inp_before, inp_after, deal, sim_before, sim_after, val_before, val_after)
    T = len(result.days)

    # ── Run compensation engine ──
    comp_result = compute_compensation(comp, sim_after, inp_after)

    # Convert monthly operator compensation to daily array for KPI adjustment
    _T_sim = len(sim_after.days)
    _op_cost_daily = np.zeros(_T_sim)
    for _m in range(comp_result.n_months):
        _s, _e = _m * 30, min((_m + 1) * 30, _T_sim)
        _days_in_month = _e - _s
        if _days_in_month > 0:
            _op_cost_daily[_s:_e] = comp_result.total_compensation[_m] / _days_in_month

    # ── KPI Summary Row ──
    st.markdown("---")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Value Created", _fd(result.total_value_created))
    c2.metric("Operator Earned", _fd(result.operator_total_earned))
    c3.metric("Client Net Gain", _fd(result.client_net_gain))
    c4.metric("Client ROI", f"{result.client_roi:.1f}x")
    if result.break_even_day >= 0:
        c5.metric("Break-Even", f"Day {result.break_even_day}")
    else:
        c5.metric("Break-Even", "Never")

    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("Equity Before", _fd(result.client_equity_before))
    c7.metric("Equity After", _fd(result.client_equity_after))
    c8.metric("Equity Delta", _fd(result.equity_delta))
    eq_pct = (result.equity_delta / abs(result.client_equity_before) * 100) if result.client_equity_before != 0 else 0
    c9.metric("Equity Change", f"{eq_pct:+.0f}%")
    c10.metric("Lifetime ROI", f"{result.lifetime_roi:.1f}x")

    st.markdown("---")

    # ── Tabs ──
    (tab_overview, tab_client, tab_operator, tab_finder, tab_roi,
     tab_calc, tab_comp, tab_comp_cmp, tab_comp_sens) = st.tabs(
        ["Overview", "Client View", "Operator View", "Deal Finder",
         "ROI Timeline", "Calculations", "Comp Structure",
         "Compare Structures", "Comp Sensitivity"]
    )

    # ---------- Tab: Overview ----------
    with tab_overview:
        x = np.arange(T)

        fig_fcf = go.Figure()
        fig_fcf.add_trace(go.Scatter(
            x=x, y=sim_before.free_cash_flow,
            name="Before Operator", line=dict(color=COLORS["gray"], width=1),
        ))
        fig_fcf.add_trace(go.Scatter(
            x=x, y=result.eff_fcf,
            name="After Operator (ramped)", line=dict(color=COLORS["green"], width=1),
        ))
        fig_fcf.add_trace(go.Scatter(
            x=x, y=result.client_fcf_after_fees,
            name="After (net of fees)", line=dict(color=COLORS["sky"], width=1, dash="dash"),
        ))
        fig_fcf.add_hline(y=0, line_dash="dash", line_color="#333")
        if d_duration > 0:
            fig_fcf.add_vline(
                x=d_duration, line_dash="dot", line_color=COLORS["amber"],
                annotation_text="Engagement End", annotation_position="top left",
            )
        fig_fcf.update_layout(title="Daily FCF: Before vs After Operator", **DAILY_LAYOUT)
        st.plotly_chart(fig_fcf, use_container_width=True, key="db_fcf_overview")

        fig_cust = go.Figure()
        fig_cust.add_trace(go.Scatter(
            x=x, y=sim_before.active_customers,
            name="Before", line=dict(color=COLORS["gray"], width=1),
        ))
        fig_cust.add_trace(go.Scatter(
            x=x, y=result.eff_active_customers,
            name="After (ramped)", line=dict(color=COLORS["green"], width=1),
        ))
        fig_cust.update_layout(title="Active Customers: Before vs After", **DAILY_LAYOUT)
        st.plotly_chart(fig_cust, use_container_width=True, key="db_cust_overview")

        fig_gain = go.Figure()
        fig_gain.add_trace(go.Scatter(
            x=x, y=result.client_cumulative_gain,
            name="Client Cumulative Gain", fill="tozeroy",
            line=dict(color=COLORS["green"], width=1),
        ))
        fig_gain.add_hline(y=0, line_dash="dash", line_color="#333")
        if result.break_even_day >= 0:
            fig_gain.add_vline(
                x=result.break_even_day, line_dash="dash", line_color=COLORS["green"],
                annotation_text=f"Break-even (day {result.break_even_day})",
            )
        fig_gain.update_layout(
            title="Client Cumulative Gain (vs doing nothing, after operator fees)", **DAILY_LAYOUT,
        )
        st.plotly_chart(fig_gain, use_container_width=True, key="db_gain_overview")

        fig_roi_ov = go.Figure()
        fig_roi_ov.add_trace(go.Scatter(
            x=x, y=result.roi_curve,
            name="Client ROI", fill="tozeroy",
            fillcolor="rgba(96,165,250,0.1)",
            line=dict(color=COLORS["sky"], width=2),
        ))
        fig_roi_ov.add_hline(y=0, line_dash="dash", line_color="#333")
        if result.break_even_day >= 0:
            fig_roi_ov.add_vline(
                x=result.break_even_day, line_dash="dash", line_color=COLORS["green"],
                annotation_text="Break-even",
            )
        if d_duration > 0:
            fig_roi_ov.add_vline(
                x=d_duration, line_dash="dot", line_color=COLORS["amber"],
                annotation_text="Engagement End",
            )
        fig_roi_ov.update_layout(title="Client ROI Over Time", yaxis_title="ROI (x)", **DAILY_LAYOUT)
        st.plotly_chart(fig_roi_ov, use_container_width=True, key="db_roi_overview")

    # ---------- Tab: Client View ----------
    with tab_client:
        st.markdown("### What the client gets")

        kpis_b = compute_kpis(inp_before, sim_before)
        kpis_a = compute_kpis(inp_after, sim_after, operator_cost_daily=_op_cost_daily)

        comparison = pd.DataFrame({
            "Metric": [
                "Active Customers (end)", "Monthly Revenue", "Monthly FCF",
                "Time to Profitability", "CAC (Blended)", "LTV", "LTV/CAC",
                "Profit/Customer/Month", "Equity Value (DCF)",
            ],
            "Before Operator": [
                f"{kpis_b.active_customers:,.0f}", _fd(kpis_b.monthly_revenue),
                _fd(kpis_b.monthly_fcf), f"{kpis_b.time_to_profitability_days} days",
                _fd(kpis_b.cac_blended), _fd(kpis_b.ltv), f"{kpis_b.ltv_cac_ratio:.1f}x",
                _fd(kpis_b.profit_per_customer_per_month), _fd(val_before.equity_value_dcf),
            ],
            "After Operator": [
                f"{kpis_a.active_customers:,.0f}", _fd(kpis_a.monthly_revenue),
                _fd(kpis_a.monthly_fcf), f"{kpis_a.time_to_profitability_days} days",
                _fd(kpis_a.cac_blended), _fd(kpis_a.ltv), f"{kpis_a.ltv_cac_ratio:.1f}x",
                _fd(kpis_a.profit_per_customer_per_month), _fd(val_after.equity_value_dcf),
            ],
        })
        st.dataframe(comparison, use_container_width=True, hide_index=True, key="db_client_comparison")

        be_text = (
            f"Break-even at **day {result.break_even_day}** (~month {result.break_even_day // 30 + 1})."
            if result.break_even_day >= 0
            else "The engagement **does not break even** within the simulation window."
        )
        st.markdown(
            f"**Bottom line for the client:** The operator creates **{_fd(result.total_value_created)}** "
            f"in FCF over the engagement. After paying the operator **{_fd(result.operator_total_earned)}**, "
            f"the client keeps **{_fd(result.client_net_gain)}** -- a **{result.client_roi:.1f}x ROI** "
            f"on operator fees. Equity value increases by **{_fd(result.equity_delta)}**. {be_text}"
        )

    # ---------- Tab: Operator View ----------
    with tab_operator:
        st.markdown("### What the operator earns")

        eng_days = deal.engagement_duration if deal.engagement_duration > 0 else inp_before.time_max
        retainer_total = float(np.sum(result.operator_retainer))
        revshare_total = float(np.sum(result.operator_rev_share))
        ppc_total = float(np.sum(result.operator_pay_per_close))
        bonus_total = float(np.sum(result.operator_bonus))

        o1, o2, o3, o4, o5 = st.columns(5)
        o1.metric("Retainer", _fd(retainer_total))
        o2.metric("Rev Share", _fd(revshare_total))
        o3.metric("Pay/Close", _fd(ppc_total))
        o4.metric("Bonuses", _fd(bonus_total))
        o5.metric("Total Earned", _fd(result.operator_total_earned))

        o6, o7, o8 = st.columns(3)
        o6.metric("Avg Monthly", _fd(result.monthly_earnings_avg))
        o7.metric("Effective $/Customer", _fd(result.effective_rate_per_customer))
        total_new_eng = float(np.sum(result.eff_new_customers[: min(eng_days, T)]))
        o8.metric("Customers Acquired", f"{total_new_eng:,.0f}")

        fig_earn = go.Figure()
        fig_earn.add_trace(go.Scatter(
            x=np.arange(T), y=result.operator_cumulative_earnings,
            name="Cumulative Earnings", fill="tozeroy",
            line=dict(color=COLORS["amber"], width=1),
        ))
        if d_duration > 0:
            fig_earn.add_vline(
                x=d_duration, line_dash="dot", line_color=COLORS["gray"],
                annotation_text="Engagement End",
            )
        fig_earn.update_layout(title="Operator Cumulative Earnings", **DAILY_LAYOUT)
        st.plotly_chart(fig_earn, use_container_width=True, key="db_earn_operator")

        fig_break = go.Figure()
        fig_break.add_trace(go.Scatter(
            x=np.arange(T), y=np.cumsum(result.operator_retainer),
            name="Retainer", stackgroup="earnings",
            line=dict(color=COLORS["gray"], width=0),
        ))
        fig_break.add_trace(go.Scatter(
            x=np.arange(T), y=np.cumsum(result.operator_rev_share),
            name="Rev Share", stackgroup="earnings",
            line=dict(color=COLORS["green"], width=0),
        ))
        if comp.per_deal_amount > 0:
            fig_break.add_trace(go.Scatter(
                x=np.arange(T), y=np.cumsum(result.operator_pay_per_close),
                name="Pay/Close", stackgroup="earnings",
                line=dict(color=COLORS["sky"], width=0),
            ))
        if bonus_total > 0:
            fig_break.add_trace(go.Scatter(
                x=np.arange(T), y=np.cumsum(result.operator_bonus),
                name="Bonuses", stackgroup="earnings",
                line=dict(color=COLORS["purple"], width=0),
            ))
        fig_break.update_layout(title="Earnings Breakdown (Cumulative, Stacked)", **DAILY_LAYOUT)
        st.plotly_chart(fig_break, use_container_width=True, key="db_break_operator")

    # ---------- Tab: Deal Finder ----------
    with tab_finder:
        st.markdown("### Find the deal that works for both sides")
        finder_mode = st.radio(
            "Mode", ["Revenue Share Sweep", "Deal Comparison"], horizontal=True, key="db_finder_mode",
        )

        if finder_mode == "Revenue Share Sweep":
            st.caption("Sweep the revenue share % and see where both sides are profitable.")
            target_client_roi = st.number_input(
                "Minimum client ROI (x)", value=3.0, step=0.5, key="db_target_roi",
            )

            results_sweep = []
            for rs in np.arange(0, 51, 2.5):
                test_deal = DealTerms(
                    revenue_share_pct=rs, revenue_share_basis=deal.revenue_share_basis,
                    revenue_share_cap=deal.revenue_share_cap, monthly_retainer=comp.retainer_amount,
                    pay_per_close=comp.per_deal_amount, bonuses=[],
                    ramp_days=d_ramp, ramp_curve=d_ramp_curve,
                    engagement_duration=d_duration,
                    post_engagement_retention=d_post_eng, decay_rate_days=d_decay,
                )
                tr = compute_deal(
                    inp_before, inp_after, test_deal, sim_before, sim_after, val_before, val_after,
                )
                results_sweep.append({
                    "rev_share": rs,
                    "operator_earned": tr.operator_total_earned,
                    "client_net_gain": tr.client_net_gain,
                    "client_roi": tr.client_roi,
                    "break_even": tr.break_even_day,
                })

            rs_vals = [r["rev_share"] for r in results_sweep]
            op_vals = [r["operator_earned"] for r in results_sweep]
            cl_vals = [r["client_net_gain"] for r in results_sweep]

            fig_finder = go.Figure()
            fig_finder.add_trace(go.Scatter(
                x=rs_vals, y=op_vals,
                name="Operator Earned", line=dict(color=COLORS["amber"], width=2),
            ))
            fig_finder.add_trace(go.Scatter(
                x=rs_vals, y=cl_vals,
                name="Client Net Gain", line=dict(color=COLORS["green"], width=2),
            ))
            fig_finder.add_hline(y=0, line_dash="dash", line_color="#333")
            fig_finder.update_layout(
                title="Revenue Share % -> Earnings for Both Sides",
                xaxis_title="Revenue Share (%)",
                yaxis_title="$",
                **{k: v for k, v in DAILY_LAYOUT.items() if k != "xaxis"},
            )
            st.plotly_chart(fig_finder, use_container_width=True, key="db_finder_sweep")

            sweet_spots = [
                r for r in results_sweep
                if r["client_roi"] >= target_client_roi and r["operator_earned"] > 0
            ]
            if sweet_spots:
                best = max(sweet_spots, key=lambda r: r["operator_earned"])
                be_label = f"day {best['break_even']}" if best["break_even"] >= 0 else "never"
                st.success(
                    f"**Sweet spot: {best['rev_share']:.1f}% revenue share**  \n"
                    f"Operator earns **{_fd(best['operator_earned'])}** over the engagement.  \n"
                    f"Client keeps **{_fd(best['client_net_gain'])}** net gain "
                    f"({best['client_roi']:.1f}x ROI -- above your {target_client_roi:.0f}x minimum).  \n"
                    f"Break-even: {be_label}."
                )
            else:
                st.warning("No revenue share level meets the client's minimum ROI target.")

            sweep_df = pd.DataFrame(results_sweep)
            sweep_df.columns = ["Rev Share %", "Operator Earned", "Client Net Gain", "Client ROI", "Break-Even"]
            sweep_df["Operator Earned"] = sweep_df["Operator Earned"].apply(_fd)
            sweep_df["Client Net Gain"] = sweep_df["Client Net Gain"].apply(_fd)
            sweep_df["Client ROI"] = sweep_df["Client ROI"].apply(lambda v: f"{v:.1f}x")
            sweep_df["Break-Even"] = sweep_df["Break-Even"].apply(
                lambda v: f"Day {int(v)}" if v >= 0 else "Never",
            )
            st.dataframe(sweep_df, use_container_width=True, hide_index=True, key="db_sweep_table")

        else:
            st.caption(
                "Compare up to 4 deal structures side by side. "
                "All share the same engagement timing, bonuses, and ramp settings."
            )

            struct_defaults = [
                {"label": "High Retainer + Low Share", "ret": 5000.0, "rs": 10.0, "ppc": 0.0},
                {"label": "Low Retainer + High Share", "ret": 3000.0, "rs": 15.0, "ppc": 0.0},
                {"label": "Pure Pay Per Close", "ret": 0.0, "rs": 0.0, "ppc": 500.0},
                {"label": "Balanced Hybrid", "ret": 2000.0, "rs": 5.0, "ppc": 250.0},
            ]

            s_cols = st.columns(4)
            struct_params = []
            for i, col in enumerate(s_cols):
                with col:
                    st.markdown(f"**{struct_defaults[i]['label']}**")
                    s_ret = st.number_input("Retainer ($)", value=struct_defaults[i]["ret"], step=500.0, key=f"db_s{i}_ret")
                    s_rs = st.number_input("Rev Share (%)", value=struct_defaults[i]["rs"], step=1.0, key=f"db_s{i}_rs")
                    s_ppc = st.number_input("Pay/Close ($)", value=struct_defaults[i]["ppc"], step=100.0, key=f"db_s{i}_ppc")
                    struct_params.append({"label": struct_defaults[i]["label"], "ret": s_ret, "rs": s_rs, "ppc": s_ppc})

            comp_results_finder = []
            for sp in struct_params:
                td = DealTerms(
                    revenue_share_pct=sp["rs"], revenue_share_basis=deal.revenue_share_basis,
                    revenue_share_cap=deal.revenue_share_cap, monthly_retainer=sp["ret"],
                    pay_per_close=sp["ppc"], bonuses=[],
                    ramp_days=d_ramp, ramp_curve=d_ramp_curve,
                    engagement_duration=d_duration,
                    post_engagement_retention=d_post_eng, decay_rate_days=d_decay,
                )
                comp_results_finder.append(compute_deal(
                    inp_before, inp_after, td, sim_before, sim_after, val_before, val_after,
                ))

            comp_table = []
            for i, cr in enumerate(comp_results_finder):
                comp_table.append({
                    "Structure": struct_params[i]["label"],
                    "Operator Earned": _fd(cr.operator_total_earned),
                    "Client Net Gain": _fd(cr.client_net_gain),
                    "Client ROI": f"{cr.client_roi:.1f}x",
                    "Break-Even": f"Day {cr.break_even_day}" if cr.break_even_day >= 0 else "Never",
                    "Lifetime ROI": f"{cr.lifetime_roi:.1f}x",
                    "Eff $/Customer": _fd(cr.effective_rate_per_customer),
                })
            st.dataframe(pd.DataFrame(comp_table), use_container_width=True, hide_index=True, key="db_finder_comp_table")

            labels = [sp["label"] for sp in struct_params]
            fig_comp_finder = go.Figure()
            fig_comp_finder.add_trace(go.Bar(
                name="Operator Earned", x=labels,
                y=[cr.operator_total_earned for cr in comp_results_finder],
                marker_color=COLORS["amber"],
            ))
            fig_comp_finder.add_trace(go.Bar(
                name="Client Net Gain", x=labels,
                y=[cr.client_net_gain for cr in comp_results_finder],
                marker_color=COLORS["green"],
            ))
            fig_comp_finder.update_layout(
                title="Deal Structure Comparison",
                barmode="group", yaxis_title="$",
                **{k: v for k, v in DAILY_LAYOUT.items() if k != "xaxis"},
            )
            st.plotly_chart(fig_comp_finder, use_container_width=True, key="db_finder_comp_chart")

    # ---------- Tab: ROI Timeline ----------
    with tab_roi:
        st.markdown("### ROI Over Time")
        st.caption(
            "How the client's return on the operator engagement evolves. "
            "The value compounds after the engagement ends because retained customers keep generating revenue."
        )

        fig_roi_tl = go.Figure()
        x_roi = np.arange(T)

        fig_roi_tl.add_trace(go.Scatter(
            x=x_roi, y=result.roi_curve,
            name="Client ROI", fill="tozeroy",
            fillcolor="rgba(74,222,128,0.1)",
            line=dict(color=COLORS["green"], width=2),
        ))
        fig_roi_tl.add_hline(y=0, line_dash="dash", line_color="#555", line_width=1)

        if result.break_even_day >= 0:
            fig_roi_tl.add_vline(
                x=result.break_even_day, line_dash="dash",
                line_color=COLORS["green"], line_width=1,
                annotation_text=f"Break-even (day {result.break_even_day})",
                annotation_position="top left",
                annotation_font=dict(size=10, color=COLORS["green"]),
            )

        if d_duration > 0:
            fig_roi_tl.add_vline(
                x=d_duration, line_dash="dot",
                line_color=COLORS["amber"], line_width=1,
                annotation_text="Engagement End",
                annotation_position="top right",
                annotation_font=dict(size=10, color=COLORS["amber"]),
            )
            if d_duration < T:
                fig_roi_tl.add_vrect(
                    x0=d_duration, x1=T,
                    fillcolor=COLORS["green"], opacity=0.03, line_width=0,
                    annotation_text="Post-Engagement Value",
                    annotation_position="top left",
                    annotation_font=dict(size=9, color="#666"),
                )

        for label, day in [("6 mo", 180), ("12 mo", 365), ("24 mo", 730)]:
            if day < T and result.cumulative_operator_cost[day] > 0:
                roi_val = float(result.roi_curve[day])
                fig_roi_tl.add_annotation(
                    x=day, y=roi_val,
                    text=f"{label}: {roi_val:.1f}x",
                    showarrow=True, arrowhead=2, arrowwidth=1,
                    arrowcolor="#666", font=dict(size=10, color="#ccc"),
                    bgcolor="rgba(0,0,0,0.7)", bordercolor="#333",
                )

        fig_roi_tl.update_layout(
            title="Client ROI Timeline", yaxis_title="ROI (x)", **DAILY_LAYOUT,
        )
        st.plotly_chart(fig_roi_tl, use_container_width=True, key="db_roi_timeline")

        st.markdown("### Monthly ROI Progression")
        max_months = min(T // 30, 30)
        eng_end_day = d_duration if d_duration > 0 else T
        roi_rows = []
        for m in range(1, max_months + 1):
            d = min(m * 30 - 1, T - 1)
            cv = float(result.cumulative_value_created[d])
            co = float(result.cumulative_operator_cost[d])
            cn = cv - co
            r = float(result.roi_curve[d]) if co > 0 else 0.0
            in_eng = "yes" if d < eng_end_day else ""
            roi_rows.append({
                "Month": m,
                "Active": in_eng,
                "Cum Value Created": _fd(cv),
                "Cum Operator Cost": _fd(co),
                "Cum Client Net": _fd(cn),
                "ROI": f"{r:.1f}x" if co > 0 else "---",
            })
        st.dataframe(pd.DataFrame(roi_rows), use_container_width=True, hide_index=True, key="db_roi_monthly")

    # ---------- Tab: Calculations ----------
    with tab_calc:
        st.markdown("### Computation Audit Trail")
        st.caption("Every number, every formula, every step. Verify anything.")

        # ── Helper: render channel math for a given state ──
        def _channel_math(inp, label):
            lines = ""
            if inp.use_outbound:
                _cd = inp.contacts_per_month / 30
                _ld = _cd * (inp.outbound_conversion_rate / 100)
                _cusd = _ld * (inp.lead_conversion_rate_outbound / 100)
                _delay = inp.time_to_market_outbound + inp.time_to_sell
                lines += f"""OUTBOUND ({label}):
  contacts/day     = {inp.contacts_per_month:,} / 30 = {_cd:,.1f}
  leads/day        = {_cd:,.1f} x {inp.outbound_conversion_rate}% = {_ld:,.2f}
  customers/day    = {_ld:,.2f} x {inp.lead_conversion_rate_outbound}% = {_cusd:,.4f}
  customers/month  = {_cusd * 30:,.1f}
  delay            = {inp.time_to_market_outbound} + {inp.time_to_sell} = {_delay} days
"""
            if inp.use_inbound and inp.cpm > 0:
                _imp = (inp.media_spend / inp.cpm) * 1000 / 30
                _clk = _imp * (inp.ctr / 100)
                _ld = _clk * (inp.funnel_conversion_rate / 100)
                _cusd = _ld * (inp.lead_conversion_rate_inbound / 100)
                _delay = inp.time_to_market_inbound + inp.time_to_sell
                lines += f"""INBOUND ({label}):
  impressions/day  = (${inp.media_spend:,.0f} / ${inp.cpm:,.0f}) x 1000 / 30 = {_imp:,.0f}
  clicks/day       = {_imp:,.0f} x {inp.ctr}% = {_clk:,.1f}
  leads/day        = {_clk:,.1f} x {inp.funnel_conversion_rate}% = {_ld:,.2f}
  customers/day    = {_ld:,.2f} x {inp.lead_conversion_rate_inbound}% = {_cusd:,.4f}
  customers/month  = {_cusd * 30:,.1f}
  delay            = {inp.time_to_market_inbound} + {inp.time_to_sell} = {_delay} days
"""
            if inp.use_organic:
                _vd = inp.organic_views_per_month / 30
                _ld = _vd * (inp.organic_view_to_lead_rate / 100)
                _cusd = _ld * (inp.lead_to_customer_rate_organic / 100)
                _delay = inp.time_to_market_organic + inp.time_to_sell
                lines += f"""ORGANIC ({label}):
  views/day        = {inp.organic_views_per_month:,} / 30 = {_vd:,.0f}
  leads/day        = {_vd:,.0f} x {inp.organic_view_to_lead_rate}% = {_ld:,.2f}
  customers/day    = {_ld:,.2f} x {inp.lead_to_customer_rate_organic}% = {_cusd:,.4f}
  customers/month  = {_cusd * 30:,.1f}
  delay            = {inp.time_to_market_organic} + {inp.time_to_sell} = {_delay} days
"""
            return lines.rstrip()

        # ── 1. Customer Acquisition ──
        st.markdown("### 1. Customer Acquisition -- Before vs After")
        _calc1, _calc2 = st.columns(2)
        with _calc1:
            st.code(_channel_math(inp_before, "Before"), language=None)
        with _calc2:
            st.code(_channel_math(inp_after, "After"), language=None)

        # ── 2. Revenue Per Customer ──
        def _unit_econ(inp, label):
            _rc = inp.price_of_offer * (inp.realization_rate / 100)
            _fc = inp.price_of_offer * (inp.cost_to_fulfill / 100)
            _sc = inp.price_of_offer * (inp.cost_to_sell / 100)
            _tc = _rc * (inp.transaction_fee / 100)
            _contrib = _rc - _fc - _sc - _tc
            lines = f"""NEW CUSTOMER ({label}):
  revenue_collected = ${inp.price_of_offer:,.0f} x {inp.realization_rate}% = ${_rc:,.0f}
  - fulfillment     = ${inp.price_of_offer:,.0f} x {inp.cost_to_fulfill}% = ${_fc:,.0f}
  - sales comm      = ${inp.price_of_offer:,.0f} x {inp.cost_to_sell}% = ${_sc:,.0f}
  - transaction fee  = ${_rc:,.0f} x {inp.transaction_fee}% = ${_tc:,.0f}
  = contribution     = ${_contrib:,.0f}

  cash collected over {inp.time_to_collect} days
  refund rate: {inp.refund_rate}% after {inp.refund_period} days
"""
            if inp.churn_rate < 100:
                _rr = 100 - inp.churn_rate
                _rv = inp.price_of_renewal * (inp.realization_rate / 100)
                _rf = inp.price_of_renewal * (inp.cost_to_fulfill_renewal / 100)
                _rs = inp.price_of_renewal * (inp.cost_to_sell_renewal / 100)
                _rt = _rv * (inp.transaction_fee / 100)
                _rc2 = _rv - _rf - _rs - _rt
                lines += f"""
RENEWAL ({label}):
  renewal rate       = {_rr:.0f}%
  renewal price      = ${inp.price_of_renewal:,.0f}
  revenue_collected  = ${_rv:,.0f}
  - fulfillment      = ${_rf:,.0f}
  - sales comm       = ${_rs:,.0f}
  - transaction fee  = ${_rt:,.0f}
  = contribution     = ${_rc2:,.0f}
  contract: {inp.contract_length} days, renewal of renewals: {inp.renewal_rate_of_renewals}%"""
            return lines.rstrip()

        st.markdown("### 2. Revenue Per Customer")
        _calc3, _calc4 = st.columns(2)
        with _calc3:
            st.code(_unit_econ(inp_before, "Before"), language=None)
        with _calc4:
            st.code(_unit_econ(inp_after, "After"), language=None)

        # ── 3. Lifetime Value ──
        def _ltv_calc(inp):
            _P = inp.price_of_offer
            _RR = inp.realization_rate / 100
            _cf = inp.cost_to_fulfill / 100
            _ref = inp.refund_rate / 100
            _ch = inp.churn_rate / 100
            _fv = _P * _RR * (1 - _ref) - _P * _cf
            _pr = inp.price_of_renewal
            _cfr = inp.cost_to_fulfill_renewal / 100
            _csr = inp.cost_to_sell_renewal / 100
            _rv = _pr * _RR - _pr * _cfr - _pr * _csr
            _pf = (1 - _ch) * (1 - _ref)
            _ps = inp.renewal_rate_of_renewals / 100
            _er = _pf * _rv / (1 - _ps) if 0 < _ps < 1 else _pf * _rv
            _ltv = _fv + _er
            return _ltv, f"""first_purchase = ${_P:,.0f} x {_RR:.2f} x {1-_ref:.2f} - ${_P:,.0f} x {_cf:.2f} = ${_fv:,.0f}
renewal_value  = ${_pr:,.0f} x {_RR:.2f} - fulfill - sales = ${_rv:,.0f}
p(1st renewal) = (1-{_ch:.2f}) x (1-{_ref:.2f}) = {_pf:.3f}
p(subsequent)  = {_ps:.2f}
exp_renewals   = {_pf:.3f} x ${_rv:,.0f} / (1-{_ps:.2f}) = ${_er:,.0f}
LTV            = ${_fv:,.0f} + ${_er:,.0f} = ${_ltv:,.0f}"""

        st.markdown("### 3. Lifetime Value")
        _ltv_b, _ltv_b_text = _ltv_calc(inp_before)
        _ltv_a, _ltv_a_text = _ltv_calc(inp_after)
        _calc5, _calc6 = st.columns(2)
        with _calc5:
            st.code(f"BEFORE:\n{_ltv_b_text}", language=None)
        with _calc6:
            st.code(f"AFTER:\n{_ltv_a_text}", language=None)

        # ── 4. CAC ──
        st.markdown("### 4. Customer Acquisition Cost")

        def _cac_calc(inp, sim, label):
            _tm = float(np.sum(sim.cost_marketing))
            _ts = float(np.sum(sim.cost_sales))
            _tc = float(np.sum(sim.new_customers_total))
            _cac = (_tm + _ts) / max(_tc, 1)
            return _cac, f"""{label}:
  total marketing   = ${_tm:,.0f}
  total sales cost  = ${_ts:,.0f}
  total customers   = {_tc:,.0f}
  CAC (blended)     = ${_cac:,.0f}"""

        _cac_b, _cac_b_text = _cac_calc(inp_before, sim_before, "Before")
        _cac_a, _cac_a_text = _cac_calc(inp_after, sim_after, "After")
        _calc7, _calc8 = st.columns(2)
        with _calc7:
            st.code(f"{_cac_b_text}\n\n  LTV / CAC = ${_ltv_b:,.0f} / ${_cac_b:,.0f} = {_ltv_b/max(_cac_b,1):.1f}x", language=None)
        with _calc8:
            st.code(f"{_cac_a_text}\n\n  LTV / CAC = ${_ltv_a:,.0f} / ${_cac_a:,.0f} = {_ltv_a/max(_cac_a,1):.1f}x", language=None)

        # ── 5. Monthly Cost Structure ──
        st.markdown("### 5. Monthly Cost Structure")

        def _cost_structure(inp, label):
            _dm = inp.media_spend if inp.use_inbound else 0
            _do = (inp.number_of_sdrs * inp.outbound_salary) if inp.use_outbound else 0
            _dg = inp.organic_cost_per_month if inp.use_organic else 0
            _di = (inp.debt * inp.interest_rate / 100) / 365
            return f"""{label}:
  MARKETING (monthly):
    inbound media   = ${_dm:,.0f}/mo {"(disabled)" if not inp.use_inbound else ""}
    outbound SDRs   = {inp.number_of_sdrs} x ${inp.outbound_salary:,.0f} = ${_do:,.0f}/mo {"(disabled)" if not inp.use_outbound else ""}
    organic         = ${_dg:,.0f}/mo {"(disabled)" if not inp.use_organic else ""}
  FIXED:
    base            = ${inp.fixed_costs_per_month:,.0f}/mo
    + scaling       = ${inp.fixed_cost_increase_per_100_customers:,.0f}/mo per 100 customers
  TRANSACTION FEE   = {inp.transaction_fee}%
  INTEREST          = ${inp.debt:,.0f} x {inp.interest_rate}% / 365 = ${_di:,.0f}/day
  TAX RATE          = {inp.tax_rate}%"""

        _calc9, _calc10 = st.columns(2)
        with _calc9:
            st.code(_cost_structure(inp_before, "Before"), language=None)
        with _calc10:
            st.code(_cost_structure(inp_after, "After"), language=None)

        # ── 6. P&L Snapshot (last day of simulation) ──
        st.markdown("### 6. P&L Snapshot -- End of Simulation")

        def _pl_snapshot(sim, inp, label):
            _d = len(sim.days) - 1
            _s = max(0, _d - 29)
            _tr = float(np.sum(sim.cash_collected_total[_s:_d+1]))
            _tc = float(np.sum(sim.cost_total[_s:_d+1]))
            _gp = float(np.sum(sim.gross_profit[_s:_d+1]))
            _eb = float(np.sum(sim.ebitda[_s:_d+1]))
            _ni = float(np.sum(sim.net_income[_s:_d+1]))
            _fcf = float(np.sum(sim.free_cash_flow[_s:_d+1]))
            return f"""{label} -- Trailing 30 Days (day {_s+1} to {_d+1}):
  Cash collected     ${_tr:>12,.0f}
  - Total costs      {-_tc:>12,.0f}
  ────────────────────────────────
  Gross Profit       ${_gp:>12,.0f}
  EBITDA             ${_eb:>12,.0f}
  Net Income         ${_ni:>12,.0f}
  Free Cash Flow     ${_fcf:>12,.0f}

  Active customers   {sim.active_customers[_d]:>12,.0f}
  Cumulative FCF     ${sim.cumulative_fcf[_d]:>12,.0f}
  Cash balance       ${sim.cash_balance[_d]:>12,.0f}"""

        _calc11, _calc12 = st.columns(2)
        with _calc11:
            st.code(_pl_snapshot(sim_before, inp_before, "Before"), language=None)
        with _calc12:
            st.code(_pl_snapshot(sim_after, inp_after, "After"), language=None)

        # ── 7. DCF Valuation ──
        st.markdown("### 7. DCF Valuation -- Before vs After")

        def _dcf_calc(inp, val, label):
            return f"""{label}:
  Projection         = {inp.projection_period_dcf} days ({inp.projection_period_dcf/365:.1f} years)
  Discount rate      = {inp.discount_rate}%
  Perpetual growth   = {inp.perpetual_growth_rate}%

  PV of FCF          = ${val.pv_fcf:>14,.0f}
  Terminal value      = ${val.terminal_value:>14,.0f}
  PV of terminal      = ${val.pv_terminal_value:>14,.0f}
  ────────────────────────────────────
  Enterprise value    = ${val.enterprise_value_dcf:>14,.0f}
  - Debt + Cash       {-inp.debt + max(val.cash_at_valuation, 0):>14,.0f}
  ────────────────────────────────────
  Equity value        = ${val.equity_value_dcf:>14,.0f}

  TV as % of EV      = {val.pv_terminal_value / max(val.enterprise_value_dcf, 1) * 100:.0f}%"""

        _calc13, _calc14 = st.columns(2)
        with _calc13:
            st.code(_dcf_calc(inp_before, val_before, "Before"), language=None)
        with _calc14:
            st.code(_dcf_calc(inp_after, val_after, "After"), language=None)

        st.code(f"""EQUITY DELTA  = ${val_after.equity_value_dcf:,.0f} - ${val_before.equity_value_dcf:,.0f} = ${val_after.equity_value_dcf - val_before.equity_value_dcf:,.0f}
EQUITY CHANGE = {(val_after.equity_value_dcf - val_before.equity_value_dcf) / max(val_before.equity_value_dcf, 1) * 100:+,.0f}%""", language=None)

        # ── 8. Operator Compensation Structure ──
        st.markdown("### 8. Operator Compensation")
        _comp_lines = []
        if comp.upfront_fee_amount > 0:
            _comp_lines.append(
                f"  Upfront Fee        = ${comp.upfront_fee_amount:,.0f}"
                + (f" (split: {comp.upfront_fee_split_pct_signing:.0f}% signing, rest day {comp.upfront_fee_split_day_2})"
                   if comp.upfront_fee_split else " (at signing)")
            )
        _comp_lines.append(f"  Monthly Retainer   = ${comp.retainer_amount:,.0f}/mo")
        if comp.rev_share_mode != "none":
            _comp_lines.append(f"  Rev Share          = {comp.rev_share_percentage:.1f}% on {comp.rev_share_basis}")
            if comp.rev_share_cap_total > 0:
                _comp_lines.append(f"  Rev Share Cap      = ${comp.rev_share_cap_total:,.0f}")
        if comp.per_deal_amount > 0:
            _comp_lines.append(f"  Per-Deal Bonus     = ${comp.per_deal_amount:,.0f}")
        _comp_lines.append(f"  Engagement         = {d_duration} days, ramp {d_ramp} days ({d_ramp_curve})")
        _comp_lines.append(f"  Post-engagement    = {d_post_eng}")
        st.code("\n".join(_comp_lines), language=None)

        st.code(f"""TOTAL EARNED (engagement period):
  Upfront            ${comp_result.total_upfront:>12,.0f}
  Retainer           ${comp_result.total_retainer:>12,.0f}
  Rev Share          ${comp_result.total_rev_share:>12,.0f}
  Per-Deal           ${comp_result.total_per_deal:>12,.0f}
  ────────────────────────────────────
  TOTAL              ${comp_result.total_earned:>12,.0f}

  Avg monthly        ${comp_result.avg_monthly_earnings:>12,.0f}
  Eff $/customer     ${comp_result.effective_rate_per_customer:>12,.0f}
  Eff rev share rate {comp_result.effective_rev_share_rate:>11.1f}%""", language=None)

        # ── 9. Cash Conversion Cycle ──
        st.markdown("### 9. Cash Conversion Cycle")

        def _ccc_calc(inp, label):
            _ttm = 0
            _ttm_src = "none"
            if inp.use_outbound:
                _ttm = inp.time_to_market_outbound
                _ttm_src = f"time_to_market_outbound = {_ttm}"
            elif inp.use_inbound:
                _ttm = inp.time_to_market_inbound
                _ttm_src = f"time_to_market_inbound = {_ttm}"
            elif inp.use_organic:
                _ttm = inp.time_to_market_organic
                _ttm_src = f"time_to_market_organic = {_ttm}"
            _ccc = _ttm + inp.time_to_sell + inp.time_to_collect
            return f"""{label}:
  CCC = time_to_market + time_to_sell + time_to_collect
      = {_ttm_src}
      + time_to_sell = {inp.time_to_sell}
      + time_to_collect = {inp.time_to_collect}
      = {_ccc} days"""

        _calc15, _calc16 = st.columns(2)
        with _calc15:
            st.code(_ccc_calc(inp_before, "Before"), language=None)
        with _calc16:
            st.code(_ccc_calc(inp_after, "After"), language=None)

        # ── 10. Input Delta Summary ──
        st.markdown("### 10. Input Deltas")
        _DIFF_FIELDS = [
            ("use_inbound", "Inbound Enabled"), ("use_outbound", "Outbound Enabled"),
            ("use_organic", "Organic Enabled"), ("use_viral", "Viral Enabled"),
            ("price_of_offer", "Price ($)"), ("realization_rate", "Realization (%)"),
            ("cost_to_fulfill", "Cost to Fulfill (%)"), ("cost_to_sell", "Cost to Sell (%)"),
            ("time_to_collect", "Time to Collect (days)"), ("time_to_sell", "Time to Sell (days)"),
            ("contract_length", "Contract Length (days)"),
            ("churn_rate", "Churn (%)"), ("price_of_renewal", "Renewal Price ($)"),
            ("cost_to_sell_renewal", "Cost to Sell Renewal (%)"),
            ("cost_to_fulfill_renewal", "Cost to Fulfill Renewal (%)"),
            ("renewal_rate_of_renewals", "Renewal of Renewals (%)"),
            ("media_spend", "Media Spend ($/mo)"), ("cpm", "CPM ($)"), ("ctr", "CTR (%)"),
            ("funnel_conversion_rate", "Funnel Conv (%)"),
            ("lead_conversion_rate_inbound", "LCR Inbound (%)"),
            ("outbound_conversion_rate", "Reply Rate (%)"),
            ("lead_conversion_rate_outbound", "LCR Outbound (%)"),
            ("number_of_sdrs", "SDRs"), ("outbound_salary", "SDR Salary ($/mo)"),
            ("contacts_per_month", "Contacts/Mo"),
            ("organic_views_per_month", "Organic Views/Mo"),
            ("organic_view_to_lead_rate", "View->Lead (%)"),
            ("lead_to_customer_rate_organic", "LCR Organic (%)"),
            ("organic_cost_per_month", "Organic Cost ($/mo)"),
            ("invites_per_customer", "Invites/Customer"),
            ("conversion_rate_per_invite", "Viral Conv (%)"),
            ("viral_time", "Viral Time (days)"), ("viral_start", "Viral Start (day)"),
            ("fixed_costs_per_month", "Fixed Costs ($/mo)"),
            ("transaction_fee", "Transaction Fee (%)"),
        ]
        input_rows = []
        for field, label in _DIFF_FIELDS:
            bv = getattr(inp_before, field)
            av = getattr(inp_after, field)
            if bv != av:
                if isinstance(bv, bool):
                    input_rows.append((label, "Off" if not bv else "On", "Off" if not av else "On", "Changed"))
                elif isinstance(bv, int):
                    input_rows.append((label, f"{bv:,}", f"{av:,}", f"{av - bv:+,}"))
                elif abs(bv) >= 1000:
                    input_rows.append((label, f"${bv:,.0f}", f"${av:,.0f}", f"${av - bv:+,.0f}"))
                else:
                    input_rows.append((label, f"{bv:.2f}", f"{av:.2f}", f"{av - bv:+.2f}"))
        if input_rows:
            st.dataframe(
                pd.DataFrame(input_rows, columns=["Metric", "Before", "After", "Delta"]),
                use_container_width=True, hide_index=True, key="db_input_deltas",
            )
        else:
            st.info("Both states are identical -- adjust the 'After Operator' inputs to model improvements.")

        # ── 11. Monthly Computation Chain ──
        st.markdown("### 11. Monthly Computation Chain")
        max_months_calc = min(T // 30, 30)
        calc_rows = []
        for m in range(1, max_months_calc + 1):
            s = (m - 1) * 30
            e = min(m * 30, T)
            d_end = min(e - 1, T - 1)
            fcf_b = float(np.sum(sim_before.free_cash_flow[s:e]))
            fcf_a = float(np.sum(result.eff_fcf[s:e]))
            calc_rows.append({
                "Mo": m,
                "FCF Before": _fd(fcf_b),
                "FCF After": _fd(fcf_a),
                "Delta": _fd(fcf_a - fcf_b),
                "Retainer": _fd(float(np.sum(result.operator_retainer[s:e]))),
                "Rev Share": _fd(float(np.sum(result.operator_rev_share[s:e]))),
                "Pay/Close": _fd(float(np.sum(result.operator_pay_per_close[s:e]))),
                "Bonus": _fd(float(np.sum(result.operator_bonus[s:e]))),
                "Op Total": _fd(float(np.sum(result.operator_total_earnings[s:e]))),
                "Client Net": _fd(float(np.sum(
                    result.client_fcf_after_fees[s:e] - sim_before.free_cash_flow[s:e],
                ))),
                "ROI": (
                    f"{result.roi_curve[d_end]:.1f}x"
                    if result.cumulative_operator_cost[d_end] > 0 else "---"
                ),
                "Ramp": f"{result.ramp_factor[d_end]:.0%}",
            })
        st.dataframe(pd.DataFrame(calc_rows), use_container_width=True, hide_index=True, key="db_calc_chain")

        # ── 12. Key Formulas ──
        st.markdown("### 12. Key Formulas")
        be_formula = f"Day {result.break_even_day}" if result.break_even_day >= 0 else "Never"
        st.code(f"""Value Created      = FCF(after, ramped) - FCF(before)
                   = {_fd(result.total_value_created)}

Operator Earned    = Upfront + Retainer + Rev Share + Pay/Close + Bonuses
                   = {_fd(comp_result.total_upfront)} + {_fd(comp_result.total_retainer)} + {_fd(comp_result.total_rev_share)} + {_fd(comp_result.total_per_deal)}
                   = {_fd(result.operator_total_earned)}

Client Net Gain    = Value Created - Operator Earned
                   = {_fd(result.total_value_created)} - {_fd(result.operator_total_earned)}
                   = {_fd(result.client_net_gain)}

Client ROI         = Client Net Gain / Operator Earned
                   = {_fd(result.client_net_gain)} / {_fd(result.operator_total_earned)}
                   = {result.client_roi:.1f}x

Lifetime ROI       = Cumulative Net / Cumulative Op Cost at sim end
                   = {result.lifetime_roi:.1f}x

Break-Even Day     = First day client cumulative net >= 0
                   = {be_formula}""", language=None)

    # ---------- Tab: Comp Structure ----------
    # Compute business health KPIs for both states
    _kpis_before = compute_kpis(inp_before, sim_before)
    _kpis_after = compute_kpis(inp_after, sim_after, operator_cost_daily=_op_cost_daily)

    with tab_comp:
        st.markdown("### Compensation Structure")
        st.caption("Configure all compensation parameters in the sidebar. Results update live.")

        # ── Operator compensation KPIs ──
        st.markdown("**Operator Compensation**")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total Earned", _fd(comp_result.total_earned))
        k2.metric("Avg Monthly", _fd(comp_result.avg_monthly_earnings))
        k3.metric("Eff $/Customer", _fd(comp_result.effective_rate_per_customer))
        k4.metric("Eff RS Rate", f"{comp_result.effective_rev_share_rate:.1f}%")
        k5.metric("Client Cum. Profit", _fd(comp_result.client_cumulative_profit_after_comp[-1]))

        k6, k7, k8, k9, k10 = st.columns(5)
        k6.metric("Upfront", _fd(comp_result.total_upfront))
        k7.metric("Retainer", _fd(comp_result.total_retainer))
        k8.metric("Rev Share", _fd(comp_result.total_rev_share))
        k9.metric("Per-Deal", _fd(comp_result.total_per_deal))
        k10.metric("Total Customers", f"{float(np.sum(comp_result.monthly_new_customers)):,.0f}")

        # ── Business health KPIs (Before -> After with deltas) ──
        st.markdown("---")
        st.markdown("**Client Business Health -- Before vs After Operator**")

        h1, h2, h3, h4, h5 = st.columns(5)
        _ttp_b = f"{_kpis_before.time_to_profitability_months}mo" if _kpis_before.time_to_profitability_months > 0 else "Never"
        _ttp_a = f"{_kpis_after.time_to_profitability_months}mo" if _kpis_after.time_to_profitability_months > 0 else "Never"
        _ttp_delta = _kpis_before.time_to_profitability_days - _kpis_after.time_to_profitability_days
        h1.metric("Time to Profit", _ttp_a,
                   delta=f"{_ttp_delta:+d} days faster" if _ttp_delta > 0 else None)
        h2.metric("Cash Needed", _fd(_kpis_after.cash_needed),
                   delta=_fd(_kpis_before.cash_needed - _kpis_after.cash_needed))
        h3.metric("LTV/CAC", f"{_kpis_after.ltv_cac_ratio:.1f}x",
                   delta=f"{_kpis_after.ltv_cac_ratio - _kpis_before.ltv_cac_ratio:+.1f}x")
        h4.metric("CAC (Blended)", _fd(_kpis_after.cac_blended),
                   delta=_fd(_kpis_before.cac_blended - _kpis_after.cac_blended))
        h5.metric("LTV", _fd(_kpis_after.ltv),
                   delta=_fd(_kpis_after.ltv - _kpis_before.ltv))

        h6, h7, h8, h9, h10 = st.columns(5)
        h6.metric("Payback Period", f"{_kpis_after.payback_period_days:.0f}d",
                   delta=f"{_kpis_before.payback_period_days - _kpis_after.payback_period_days:+.0f}d")
        h7.metric("Gross Margin", f"{_kpis_after.gross_margin:.1f}%",
                   delta=f"{_kpis_after.gross_margin - _kpis_before.gross_margin:+.1f}%")
        h8.metric("Monthly FCF", _fd(_kpis_after.monthly_fcf),
                   delta=_fd(_kpis_after.monthly_fcf - _kpis_before.monthly_fcf))
        h9.metric("Profit/Cust/Mo", _fd(_kpis_after.profit_per_customer_per_month),
                   delta=_fd(_kpis_after.profit_per_customer_per_month - _kpis_before.profit_per_customer_per_month))
        h10.metric("Cash Conv. Cycle", f"{_kpis_after.cash_conversion_cycle}d",
                    delta=f"{_kpis_before.cash_conversion_cycle - _kpis_after.cash_conversion_cycle:+d}d")

        st.markdown("---")

        # ── Cumulative earnings chart ──
        x_mo = np.arange(1, comp_result.n_months + 1)

        fig_cum = go.Figure()
        fig_cum.add_trace(go.Scatter(x=x_mo, y=np.cumsum(comp_result.retainer), name="Retainer", stackgroup="e", line=dict(color=COLORS["gray"], width=0)))
        if comp_result.total_rev_share > 0:
            fig_cum.add_trace(go.Scatter(x=x_mo, y=np.cumsum(comp_result.rev_share), name="Rev Share", stackgroup="e", line=dict(color=COLORS["green"], width=0)))
        if comp_result.total_per_deal > 0:
            fig_cum.add_trace(go.Scatter(x=x_mo, y=np.cumsum(comp_result.per_deal_bonus), name="Per-Deal", stackgroup="e", line=dict(color=COLORS["sky"], width=0)))
        if comp_result.total_upfront > 0:
            fig_cum.add_trace(go.Scatter(x=x_mo, y=np.cumsum(comp_result.upfront), name="Upfront", stackgroup="e", line=dict(color=COLORS["amber"], width=0)))
        fig_cum.update_layout(title="Cumulative Operator Earnings (Stacked)", xaxis_title="Month", yaxis_title="$",
                              **{k: v for k, v in DAILY_LAYOUT.items() if k not in ("xaxis",)})
        st.plotly_chart(fig_cum, use_container_width=True, key="db_cum_comp")

        # ── Client profit vs operator earnings ──
        fig_split = go.Figure()
        fig_split.add_trace(go.Scatter(x=x_mo, y=comp_result.cumulative_compensation, name="Operator Earnings", fill="tozeroy",
                                       line=dict(color=COLORS["amber"], width=2), fillcolor="rgba(251,191,36,0.15)"))
        fig_split.add_trace(go.Scatter(x=x_mo, y=comp_result.client_cumulative_profit_after_comp, name="Client Profit (after comp)", fill="tozeroy",
                                       line=dict(color=COLORS["green"], width=2), fillcolor="rgba(74,222,128,0.1)"))
        fig_split.add_hline(y=0, line_dash="dash", line_color="#333")
        fig_split.update_layout(title="Operator vs Client -- Cumulative", xaxis_title="Month", yaxis_title="$",
                                **{k: v for k, v in DAILY_LAYOUT.items() if k not in ("xaxis",)})
        st.plotly_chart(fig_split, use_container_width=True, key="db_split_comp")

        # ── Monthly breakdown table ──
        st.markdown("### Month-by-Month Breakdown")
        comp_rows = []
        for m in range(comp_result.n_months):
            comp_rows.append({
                "Month": m + 1, "Upfront": _fd(comp_result.upfront[m]), "Retainer": _fd(comp_result.retainer[m]),
                "Rev Share": _fd(comp_result.rev_share[m]), "Per-Deal": _fd(comp_result.per_deal_bonus[m]),
                "Total Comp": _fd(comp_result.total_compensation[m]), "Cumulative": _fd(comp_result.cumulative_compensation[m]),
                "Client FCF": _fd(comp_result.client_monthly_fcf[m]), "Client Net": _fd(comp_result.client_profit_after_comp[m]),
                "New Custs": f"{comp_result.monthly_new_customers[m]:.1f}", "Active": f"{comp_result.monthly_active_customers[m]:.0f}",
            })
        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True, key="db_comp_monthly")

        # ── Per-cohort heatmap (Mode B only) ──
        if comp.rev_share_mode == "per_client":
            st.markdown("### Per-Client Rev Share Heatmap")
            st.caption("Each cell = rev share from cohort (column) in month (row). Watch the decay.")
            max_d = min(36, comp_result.n_months)
            fig_heat = go.Figure(go.Heatmap(
                z=comp_result.rev_share_by_cohort[:max_d, :max_d],
                x=[f"C{c+1}" for c in range(max_d)], y=[f"M{m+1}" for m in range(max_d)],
                colorscale="YlOrRd", hovertemplate="Cohort %{x}, Month %{y}: $%{z:,.0f}<extra></extra>",
            ))
            fig_heat.update_layout(title="Rev Share by Cohort x Month", xaxis_title="Cohort", yaxis_title="Month", height=500,
                                   font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
                                   paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,10,10,1)")
            st.plotly_chart(fig_heat, use_container_width=True, key="db_cohort_heatmap")

    # ---------- Tab: Compare Structures (simplified) ----------
    with tab_comp_cmp:
        st.markdown("### Current Compensation Structure")
        st.caption(
            "Summary of the active compensation structure. "
            "Full structure comparison will be available in the deal comparison view."
        )

        # Show current structure details
        struct_summary = pd.DataFrame({
            "Component": ["Upfront Fee", "Monthly Retainer", "Rev Share Mode", "Rev Share Rate",
                          "Rev Share Basis", "Per-Deal Bonus", "Contract Term"],
            "Value": [
                _fd(comp.upfront_fee_amount) if comp.upfront_fee_amount > 0 else "None",
                _fd(comp.retainer_amount),
                {"none": "None", "baseline": "Mode A: Baseline", "per_client": "Mode B: Per-Client"}.get(comp.rev_share_mode, comp.rev_share_mode),
                f"{comp.rev_share_percentage:.1f}%" if comp.rev_share_mode != "none" else "N/A",
                comp.rev_share_basis if comp.rev_share_mode != "none" else "N/A",
                _fd(comp.per_deal_amount) if comp.per_deal_amount > 0 else "None",
                f"{comp.contract_term_months} months" if comp.contract_term_months > 0 else "Permanent",
            ],
        })
        st.dataframe(struct_summary, use_container_width=True, hide_index=True, key="db_struct_summary")

        # Earnings summary
        st.markdown("---")
        st.markdown("**Earnings Summary**")
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Total Earned", _fd(comp_result.total_earned))
        d2.metric("Retainer", _fd(comp_result.total_retainer))
        d3.metric("Rev Share", _fd(comp_result.total_rev_share))
        d4.metric("Per-Deal", _fd(comp_result.total_per_deal))
        d5.metric("Client Profit", _fd(comp_result.client_cumulative_profit_after_comp[-1]))

        # Overlay chart: operator vs client
        x_cmp = np.arange(1, comp_result.n_months + 1)
        fig_cmp_earn = go.Figure()
        fig_cmp_earn.add_trace(go.Scatter(
            x=x_cmp, y=comp_result.cumulative_compensation,
            name="Operator Cumulative", line=dict(color=COLORS["amber"], width=2),
        ))
        fig_cmp_earn.add_trace(go.Scatter(
            x=x_cmp, y=comp_result.client_cumulative_profit_after_comp,
            name="Client Cumulative Profit", line=dict(color=COLORS["green"], width=2),
        ))
        fig_cmp_earn.add_hline(y=0, line_dash="dash", line_color="#333")
        fig_cmp_earn.update_layout(
            title="Operator Earnings vs Client Profit -- Cumulative",
            xaxis_title="Month", yaxis_title="$",
            **{k: v for k, v in DAILY_LAYOUT.items() if k not in ("xaxis",)},
        )
        st.plotly_chart(fig_cmp_earn, use_container_width=True, key="db_cmp_earn")

        # Decay / escalation details
        if comp.retainer_escalation_enabled and comp.retainer_escalation_schedule:
            st.markdown("**Retainer Escalation Schedule**")
            esc_rows = [{"Month": s.month, "Amount": _fd(s.amount)} for s in comp.retainer_escalation_schedule]
            st.dataframe(pd.DataFrame(esc_rows), use_container_width=True, hide_index=True, key="db_esc_schedule")

        if comp.rev_share_decay_enabled and comp.rev_share_decay_schedule:
            st.markdown("**Rev Share Decay Schedule**")
            decay_rows = []
            for ds in comp.rev_share_decay_schedule:
                to_label = f"Month {ds.to_month}" if ds.to_month else "Open-ended"
                decay_rows.append({
                    "From Month": ds.from_month,
                    "To": to_label,
                    "Rate": f"{ds.rate * 100:.1f}%",
                })
            st.dataframe(pd.DataFrame(decay_rows), use_container_width=True, hide_index=True, key="db_decay_schedule")

    # ---------- Tab: Comp Sensitivity ----------
    with tab_comp_sens:
        st.markdown("### Compensation Sensitivity")
        st.caption("Sweep a single parameter and see how it shifts operator earnings and client profit.")

        _SWEEP_PARAMS = {
            "Retainer ($/mo)": ("retainer_amount", [2000, 3500, 5000, 7500, 10000, 12500, 15000]),
            "Rev Share Rate (%)": ("rev_share_percentage", [2, 5, 8, 10, 12, 15, 18, 20, 25]),
            "Per-Deal Bonus ($)": ("per_deal_amount", [0, 500, 1000, 1500, 2000, 3000, 4000, 5000]),
            "Upfront Fee ($)": ("upfront_fee_amount", [0, 2500, 5000, 7500, 10000, 15000, 20000, 25000]),
            "Baseline ($/mo, Mode A)": ("rev_share_baseline", [0, 10000, 25000, 50000, 75000, 100000]),
            "Client Window (mo, Mode B)": ("rev_share_client_window_months", [6, 9, 12, 15, 18, 24, 30, 36]),
        }

        sens_metric = st.selectbox("Parameter to Sweep", list(_SWEEP_PARAMS.keys()), key="db_sens_param")
        param_name, test_values = _SWEEP_PARAMS[sens_metric]
        current_val = getattr(comp, param_name)

        sens_results = []
        for v in test_values:
            test_comp = CompensationStructure(**{**comp.__dict__, param_name: v})
            test_comp.name = f"{param_name}={v}"
            tr = compute_compensation(test_comp, sim_after, inp_after)
            sens_results.append({
                "value": v, "total_earned": tr.total_earned, "retainer": tr.total_retainer,
                "rev_share": tr.total_rev_share, "per_deal": tr.total_per_deal,
                "client_profit": tr.client_cumulative_profit_after_comp[-1],
                "avg_monthly": tr.avg_monthly_earnings,
            })

        base_res = [r for r in sens_results if abs(r["value"] - current_val) < 0.01]
        base_earned = base_res[0]["total_earned"] if base_res else sens_results[0]["total_earned"]

        # ── Bar chart ──
        labels = [f"${v:,.0f}" if "($" in sens_metric else f"{v:g}" for v in test_values]
        earnings = [r["total_earned"] for r in sens_results]
        bar_colors = ["#e0e0e0" if abs(r["value"] - current_val) < 0.01 else "#404040" for r in sens_results]

        fig_sens = go.Figure(go.Bar(
            x=labels, y=earnings, marker_color=bar_colors,
            text=[f"${v / 1_000_000:,.1f}M" if abs(v) >= 1_000_000 else f"${v / 1_000:,.1f}K" for v in earnings],
            textposition="outside", textfont=dict(size=10, color="#888"),
        ))
        fig_sens.update_layout(title=f"Total Operator Earnings by {sens_metric}", yaxis_title="$",
                               **{k: v for k, v in DAILY_LAYOUT.items() if k not in ("xaxis",)})
        st.plotly_chart(fig_sens, use_container_width=True, key="db_sens_chart")

        # ── Delta table ──
        sens_rows = []
        for r in sens_results:
            delta = r["total_earned"] - base_earned
            pct = (delta / abs(base_earned) * 100) if base_earned != 0 else 0
            is_current = abs(r["value"] - current_val) < 0.01
            sens_rows.append({
                "": "->" if is_current else "",
                sens_metric: f"${r['value']:,.0f}" if "($" in sens_metric else f"{r['value']:g}",
                "Total Earned": _fd(r["total_earned"]),
                "Retainer": _fd(r["retainer"]),
                "Rev Share": _fd(r["rev_share"]),
                "Per-Deal": _fd(r["per_deal"]),
                "Avg Monthly": _fd(r["avg_monthly"]),
                "Client Profit": _fd(r["client_profit"]),
                "Delta": f"${delta:+,.0f}",
                "Change": f"{pct:+.0f}%",
            })
        st.dataframe(pd.DataFrame(sens_rows), use_container_width=True, hide_index=True, key="db_sens_table")
