"""
Deal Wizard — guided 3-step flow to build a complete deal.

Step 1: Model the business as it is today (base model)
Step 2: Model what it looks like after improvements (layered model)
Step 3: Configure how the operator gets paid (compensation + deal)

Produces: base model + layered model + deal, all saved to the client.
"""
from __future__ import annotations

import re
import streamlit as st
import numpy as np

from engine.inputs import ModelInputs
from engine.simulation import run_simulation, to_daily_df, to_monthly
from engine.valuation import compute_valuation
from engine.metrics import compute_kpis
from model_2_operator.deal import DealTerms, compute_deal
from model_2_operator.compensation import CompensationStructure, ALL_PRESETS, compute_compensation
from ui.charts import hero_chart, COLORS
from ui.dashboard import render_kpi_cards

from store.model import create_base_model, create_layered_model, resolve_model
from store.deal import save_deal, DealFile
from store.serialization import model_inputs_to_dict, compute_overrides, comp_structure_to_dict
from ui.sidebar import render_model_inputs


def _fd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:,.1f}K"
    return f"${v:,.0f}"


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _inject_sticky_sidebar_css() -> None:
    """Make the bottom of the sidebar sticky."""
    st.markdown("""
    <style>
    [data-testid="stSidebar"] > div:first-child {
        display: flex;
        flex-direction: column;
        height: 100vh;
    }
    .sticky-sidebar-bottom {
        position: sticky;
        bottom: 0;
        background: var(--secondary-background-color, #141414);
        padding: 1rem 0 0.5rem 0;
        border-top: 1px solid #333;
        z-index: 10;
    }
    </style>
    """, unsafe_allow_html=True)


def render_wizard(client_slug: str) -> None:
    """Render the 3-step deal wizard."""
    _inject_sticky_sidebar_css()
    st.markdown("## New Engagement")

    # Step tracker
    if "wiz_step" not in st.session_state:
        st.session_state["wiz_step"] = 1

    step = st.session_state["wiz_step"]

    steps = {1: "Current State", 2: "Target State", 3: "Compensation"}
    st.progress(step / 3, text=f"Step {step}/3 — {steps[step]}")

    if step == 1:
        _step_1_baseline(client_slug)
    elif step == 2:
        _step_2_improvements(client_slug)
    elif step == 3:
        _step_3_compensation(client_slug)


# ── Step 1: Model the business as-is ──────────────────────────────────

def _step_1_baseline(client_slug: str) -> None:
    st.markdown("### Step 1: Current State Assessment")
    st.caption("Capture the client's baseline operating metrics. The valuation updates live.")

    # Sidebar inputs
    inp = render_model_inputs(prefix="wiz_b")

    # Live dashboard
    sim = run_simulation(inp)
    daily = to_daily_df(sim)
    val = compute_valuation(inp, sim)
    kpis = compute_kpis(inp, sim)

    render_kpi_cards(kpis)
    st.plotly_chart(hero_chart(daily, cursor_day=None), use_container_width=True)

    # Valuation summary
    c1, c2, c3 = st.columns(3)
    c1.metric("Equity Value (DCF)", _fd(val.equity_value_dcf))
    c2.metric("Equity Value (EBITDA)", _fd(val.equity_value_ebitda))
    c3.metric("Cash Balance", _fd(val.cash_at_valuation))

    # Save & continue (sticky bottom)
    st.sidebar.markdown('<div class="sticky-sidebar-bottom">', unsafe_allow_html=True)
    name = st.sidebar.text_input("Baseline name", value="Current State", key="wiz_b_name")

    if st.sidebar.button("Save & Continue →", key="wiz_b_save", type="primary", use_container_width=True):
        slug = _slugify(name)
        create_base_model(client_slug, slug, name, inp,
                         description="Baseline — current state assessment")
        st.session_state["wiz_base_slug"] = slug
        st.session_state["wiz_step"] = 2
        st.rerun()
    st.sidebar.markdown('</div>', unsafe_allow_html=True)


# ── Step 2: Model the improvements ────────────────────────────────────

def _step_2_improvements(client_slug: str) -> None:
    base_slug = st.session_state.get("wiz_base_slug")
    if not base_slug:
        st.error("No baseline model found. Go back to step 1.")
        if st.button("← Back to Step 1"):
            st.session_state["wiz_step"] = 1
            st.rerun()
        return

    st.markdown("### Step 2: Target State & Value Creation")
    st.caption("Define the operational improvements. Deltas against the baseline are tracked automatically.")

    # Load baseline
    inp_before = resolve_model(client_slug, base_slug)

    # Sidebar inputs — pre-populated with baseline values
    inp_after = render_model_inputs(defaults=inp_before, prefix="wiz_a")

    # Show what changed
    overrides = compute_overrides(inp_before, inp_after)
    if overrides:
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**{len(overrides)} fields changed:**")
        for k, v in overrides.items():
            old_val = getattr(inp_before, k)
            st.sidebar.caption(f"{k}: {old_val} → {v}")

    # Live before/after comparison
    sim_before = run_simulation(inp_before)
    sim_after = run_simulation(inp_after)
    val_before = compute_valuation(inp_before, sim_before)
    val_after = compute_valuation(inp_after, sim_after)
    kpis_before = compute_kpis(inp_before, sim_before)
    kpis_after = compute_kpis(inp_after, sim_after)

    # Delta metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Equity (DCF)", _fd(val_after.equity_value_dcf),
              delta=_fd(val_after.equity_value_dcf - val_before.equity_value_dcf))
    c2.metric("Monthly FCF", _fd(kpis_after.monthly_fcf),
              delta=_fd(kpis_after.monthly_fcf - kpis_before.monthly_fcf))
    c3.metric("Active Customers", f"{kpis_after.active_customers:,.0f}",
              delta=f"{kpis_after.active_customers - kpis_before.active_customers:+,.0f}")
    c4.metric("LTV/CAC", f"{kpis_after.ltv_cac_ratio:.1f}x",
              delta=f"{kpis_after.ltv_cac_ratio - kpis_before.ltv_cac_ratio:+.1f}x")
    c5.metric("CAC", _fd(kpis_after.cac_blended),
              delta=_fd(kpis_after.cac_blended - kpis_before.cac_blended), delta_color="inverse")

    if not overrides:
        st.warning("No changes from baseline yet. Adjust the metrics the operator will improve.")

    # Navigation (sticky bottom)
    st.sidebar.markdown('<div class="sticky-sidebar-bottom">', unsafe_allow_html=True)
    name = st.sidebar.text_input("Target state name", value="Target State", key="wiz_a_name")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("← Back", key="wiz_a_back", use_container_width=True):
            st.session_state["wiz_step"] = 1
            st.rerun()
    with col2:
        if st.button("Continue →", key="wiz_a_save", type="primary", disabled=not overrides, use_container_width=True):
            slug = _slugify(name)
            create_layered_model(client_slug, slug, name, base_slug, overrides,
                               description="Target state — projected improvements")
            st.session_state["wiz_after_slug"] = slug
            st.session_state["wiz_step"] = 3
            st.rerun()
    st.sidebar.markdown('</div>', unsafe_allow_html=True)


# ── Step 3: Configure compensation ────────────────────────────────────

def _step_3_compensation(client_slug: str) -> None:
    base_slug = st.session_state.get("wiz_base_slug")
    after_slug = st.session_state.get("wiz_after_slug")
    if not base_slug or not after_slug:
        st.error("Missing models. Go back.")
        if st.button("← Back to Step 1"):
            st.session_state["wiz_step"] = 1
            st.rerun()
        return

    st.markdown("### Step 3: Compensation Structure")
    st.caption("Define the fee structure. Deal economics and client ROI update live.")

    inp_before = resolve_model(client_slug, base_slug)
    inp_after = resolve_model(client_slug, after_slug)

    # Sidebar: compensation inputs
    st.sidebar.markdown("**Preset**")
    preset_names = list(ALL_PRESETS.keys())
    preset_choice = st.sidebar.selectbox(
        "Load Preset", ["— Custom —"] + preset_names, key="wiz_c_preset")

    if preset_choice != "— Custom —":
        comp = ALL_PRESETS[preset_choice]()
    else:
        comp = CompensationStructure()

    st.sidebar.markdown("---")

    with st.sidebar.expander("Retainer", expanded=True):
        retainer = st.number_input("Retainer ($/mo)", value=comp.retainer_amount, step=500.0, key="wiz_c_ret")

    with st.sidebar.expander("Rev Share", expanded=False):
        rs_modes = ["none", "baseline", "per_client"]
        rs_mode = rs_modes[st.selectbox("Mode", range(3),
                                         format_func=lambda i: rs_modes[i],
                                         index=rs_modes.index(comp.rev_share_mode),
                                         key="wiz_c_rsm")]
        rs_pct = st.number_input("Rev Share (%)", value=comp.rev_share_percentage, step=1.0, key="wiz_c_rsp")
        rs_window = st.number_input("Client Window (months)", value=comp.rev_share_client_window_months,
                                     step=3, key="wiz_c_rsw")

    with st.sidebar.expander("Per-Deal Bonus", expanded=False):
        per_deal = st.number_input("Per Deal ($)", value=comp.per_deal_amount, step=100.0, key="wiz_c_pd")

    with st.sidebar.expander("Upfront Fee", expanded=False):
        upfront = st.number_input("Upfront ($)", value=comp.upfront_fee_amount, step=1000.0, key="wiz_c_up")

    with st.sidebar.expander("Engagement", expanded=True):
        duration = int(st.number_input("Duration (days)", value=365, step=90, key="wiz_c_dur"))
        ramp = int(st.number_input("Ramp (days)", value=60, step=15, key="wiz_c_ramp"))

    final_comp = CompensationStructure(
        name="Custom",
        retainer_amount=retainer,
        rev_share_mode=rs_mode,
        rev_share_percentage=rs_pct,
        rev_share_client_window_months=rs_window,
        per_deal_amount=per_deal,
        upfront_fee_amount=upfront,
        contract_term_months=max(duration // 30, 1) if duration > 0 else 0,
        # Preserve decay/tier settings from preset
        rev_share_decay_enabled=comp.rev_share_decay_enabled,
        rev_share_decay_schedule=comp.rev_share_decay_schedule,
        rev_share_basis=comp.rev_share_basis,
        rev_share_baseline=comp.rev_share_baseline,
    )

    # Compute deal
    sim_before = run_simulation(inp_before)
    sim_after = run_simulation(inp_after)
    val_before = compute_valuation(inp_before, sim_before)
    val_after = compute_valuation(inp_after, sim_after)

    _rs_basis_map = {"gross_revenue": "total_revenue", "gross_profit": "gross_profit"}
    deal_terms = DealTerms(
        revenue_share_pct=rs_pct if rs_mode != "none" else 0.0,
        revenue_share_basis=_rs_basis_map.get(final_comp.rev_share_basis, "delta"),
        revenue_share_cap=final_comp.rev_share_cap_total,
        monthly_retainer=retainer,
        pay_per_close=per_deal,
        upfront_fee=upfront,
        ramp_days=ramp,
        engagement_duration=duration,
        post_engagement_retention="metrics_persist",
    )

    result = compute_deal(inp_before, inp_after, deal_terms, sim_before, sim_after, val_before, val_after)
    comp_result = compute_compensation(final_comp, sim_after, inp_after)

    # Deal economics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Value Created", _fd(result.total_value_created))
    c2.metric("Operator Earned", _fd(result.operator_total_earned))
    c3.metric("Client Net Gain", _fd(result.client_net_gain))
    c4.metric("Client ROI", f"{result.client_roi:.1%}")
    c5.metric("Break-Even", f"Day {result.break_even_day}" if result.break_even_day >= 0 else "Never")

    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("Equity Before", _fd(val_before.equity_value_dcf))
    c7.metric("Equity After", _fd(val_after.equity_value_dcf))
    c8.metric("Equity Delta", _fd(result.equity_delta))
    c9.metric("Avg Monthly", _fd(comp_result.avg_monthly_earnings))
    c10.metric("Lifetime ROI", f"{result.lifetime_roi:.1f}x")

    # Earnings breakdown
    st.markdown("**Operator Earnings Breakdown**")
    bc1, bc2, bc3, bc4 = st.columns(4)
    bc1.metric("Upfront", _fd(comp_result.total_upfront))
    bc2.metric("Retainer", _fd(comp_result.total_retainer))
    bc3.metric("Rev Share", _fd(comp_result.total_rev_share))
    bc4.metric("Per-Deal", _fd(comp_result.total_per_deal))

    # ROI chart
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=result.days, y=result.roi_curve,
                              name="Client ROI", line=dict(color=COLORS["green"], width=2)))
    fig.add_hline(y=0, line_dash="dot", line_color="#555")
    if result.break_even_day >= 0:
        fig.add_vline(x=result.break_even_day, line_dash="dash", line_color=COLORS["amber"],
                      annotation_text=f"Break-even (day {result.break_even_day})")
    if duration > 0:
        fig.add_vline(x=duration, line_dash="dot", line_color=COLORS["gray"],
                      annotation_text="Engagement End")
    fig.update_layout(
        title="Client ROI Over Time",
        template="plotly_dark", height=300,
        margin=dict(l=50, r=16, t=40, b=36),
        font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,10,10,1)",
        yaxis=dict(title="ROI", tickformat=".0%", gridcolor="#1a1a1a"),
        xaxis=dict(title="Day", gridcolor="#1a1a1a"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Save (sticky bottom)
    st.sidebar.markdown('<div class="sticky-sidebar-bottom">', unsafe_allow_html=True)
    deal_name = st.sidebar.text_input("Engagement name", value="Engagement Proposal", key="wiz_c_name")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("← Back", key="wiz_c_back", use_container_width=True):
            st.session_state["wiz_step"] = 2
            st.rerun()
    with col2:
        if st.button("Finalize", key="wiz_c_save", type="primary", use_container_width=True):
            deal_slug = _slugify(deal_name)
            deal_file = DealFile(
                name=deal_name,
                before_model=base_slug,
                after_model=after_slug,
                compensation=comp_structure_to_dict(final_comp),
                engagement={
                    "duration_days": duration,
                    "ramp_days": ramp,
                    "ramp_curve": "linear",
                    "post_engagement": "metrics_persist",
                    "decay_rate_days": 180,
                },
            )
            save_deal(client_slug, deal_slug, deal_file)

            # Clean up wizard state
            for k in list(st.session_state.keys()):
                if k.startswith("wiz_"):
                    del st.session_state[k]
            st.session_state.pop("active_wizard", None)

            # Navigate to the deal
            st.session_state["active_deal"] = deal_slug
            st.success(f"Deal saved: **{deal_name}**")
            st.rerun()
    st.sidebar.markdown('</div>', unsafe_allow_html=True)
