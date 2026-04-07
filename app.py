"""
Unified Financial Modeling App.

Single entry point replacing model_1_linear/ and model_2_operator/.
Manages clients, models, deals, and deal comparisons.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

st.set_page_config(
    page_title="Financial Modeling",
    layout="wide",
    initial_sidebar_state="expanded",
)

from engine.inputs import ModelInputs
from store.client import list_clients, create_client, load_client_meta
from store.model import (
    list_models, resolve_model, create_base_model, create_layered_model,
    load_model_file, save_model, get_model_tree, ModelFile,
)
from store.deal import (
    list_deals, load_deal, save_deal, DealFile,
    get_compensation_structure, get_engagement_config,
)
from store.serialization import (
    model_inputs_to_dict, dict_to_model_inputs, compute_overrides,
    comp_structure_to_dict, dict_to_comp_structure,
)
from model_2_operator.compensation import (
    CompensationStructure, DecayStep, RetainerStep, ALL_PRESETS,
)
from views.client_manager import render_sidebar_navigation, render_client_overview
from views.model_viewer import render_model_view
from views.deal_builder import render_deal_view
from views.deal_comparison import render_deal_comparison
from views.wizard import render_wizard


# ── Helper: Model Inputs Editor ────────────────────────────────────────

def _render_model_inputs_editor(inp: ModelInputs, prefix: str = "edit") -> ModelInputs:
    """Render editable model inputs in the sidebar using the canonical renderer."""
    from ui.sidebar import render_model_inputs
    return render_model_inputs(defaults=inp, prefix=prefix)


# ── Helper: Compensation Editor ────────────────────────────────────────

def _render_comp_editor(comp: CompensationStructure, prefix: str = "comp") -> CompensationStructure:
    """Render compensation structure editor in sidebar."""
    preset_names = list(ALL_PRESETS.keys())
    preset_choice = st.sidebar.selectbox(
        "Load Preset", ["— Keep Current —"] + preset_names, key=f"{prefix}_preset")
    if preset_choice != "— Keep Current —":
        if st.sidebar.button("Apply Preset", key=f"{prefix}_apply"):
            comp = ALL_PRESETS[preset_choice]()

    with st.sidebar.expander("Upfront Fee", expanded=False):
        upfront = st.number_input("Upfront ($)", value=comp.upfront_fee_amount, step=1000.0, key=f"{prefix}_upfront")

    with st.sidebar.expander("Retainer", expanded=True):
        retainer = st.number_input("Retainer ($/mo)", value=comp.retainer_amount, step=500.0, key=f"{prefix}_ret")

    with st.sidebar.expander("Rev Share", expanded=False):
        rs_modes = ["none", "baseline", "per_client"]
        rs_mode_idx = rs_modes.index(comp.rev_share_mode) if comp.rev_share_mode in rs_modes else 0
        rs_mode = rs_modes[st.selectbox("Mode", range(len(rs_modes)),
                                         format_func=lambda i: rs_modes[i],
                                         index=rs_mode_idx, key=f"{prefix}_rsm")]
        rs_pct = st.number_input("Rev Share (%)", value=comp.rev_share_percentage, step=1.0, key=f"{prefix}_rsp")
        rs_basis_opts = ["gross_revenue", "gross_profit"]
        rs_basis_idx = rs_basis_opts.index(comp.rev_share_basis) if comp.rev_share_basis in rs_basis_opts else 0
        rs_basis = rs_basis_opts[st.selectbox("Basis", range(len(rs_basis_opts)),
                                               format_func=lambda i: rs_basis_opts[i],
                                               index=rs_basis_idx, key=f"{prefix}_rsb")]
        rs_window = st.number_input("Client Window (months)", value=comp.rev_share_client_window_months,
                                     step=3, key=f"{prefix}_rsw")
        rs_baseline = st.number_input("Baseline ($/mo)", value=comp.rev_share_baseline, step=5000.0,
                                       key=f"{prefix}_rsbl")

    with st.sidebar.expander("Per-Deal Bonus", expanded=False):
        per_deal = st.number_input("Per Deal ($)", value=comp.per_deal_amount, step=100.0, key=f"{prefix}_pd")

    return CompensationStructure(
        name=comp.name,
        upfront_fee_amount=upfront,
        retainer_amount=retainer,
        rev_share_mode=rs_mode,
        rev_share_percentage=rs_pct,
        rev_share_basis=rs_basis,
        rev_share_client_window_months=rs_window,
        rev_share_baseline=rs_baseline,
        per_deal_amount=per_deal,
        upfront_fee_split=comp.upfront_fee_split,
        upfront_fee_split_pct_signing=comp.upfront_fee_split_pct_signing,
        upfront_fee_split_day_2=comp.upfront_fee_split_day_2,
        retainer_start_month=comp.retainer_start_month,
        retainer_escalation_enabled=comp.retainer_escalation_enabled,
        retainer_escalation_schedule=comp.retainer_escalation_schedule,
        contract_term_months=comp.contract_term_months,
        rev_share_baseline_churn_adjust=comp.rev_share_baseline_churn_adjust,
        rev_share_baseline_reset_annual=comp.rev_share_baseline_reset_annual,
        rev_share_client_window_pause_on_churn=comp.rev_share_client_window_pause_on_churn,
        rev_share_decay_enabled=comp.rev_share_decay_enabled,
        rev_share_decay_schedule=comp.rev_share_decay_schedule,
        rev_share_cap_monthly=comp.rev_share_cap_monthly,
        rev_share_cap_total=comp.rev_share_cap_total,
        per_deal_trigger=comp.per_deal_trigger,
        deal_tiers_enabled=comp.deal_tiers_enabled,
        deal_tiers=comp.deal_tiers,
        deal_tier_lock=comp.deal_tier_lock,
        client_types_enabled=comp.client_types_enabled,
        client_types=comp.client_types,
        client_type_distribution=comp.client_type_distribution,
    )


# ── Helper: Engagement Editor ──────────────────────────────────────────

def _render_engagement_editor(eng: dict, prefix: str = "eng") -> dict:
    """Render engagement timing editor in sidebar."""
    with st.sidebar.expander("Engagement", expanded=False):
        duration = int(st.number_input("Duration (days, 0=permanent)",
                                        value=eng.get("duration_days", 365), step=90,
                                        key=f"{prefix}_dur"))
        ramp = int(st.number_input("Ramp Period (days)",
                                    value=eng.get("ramp_days", 60), step=15,
                                    key=f"{prefix}_ramp"))
        curve_opts = ["linear", "step"]
        curve_idx = curve_opts.index(eng.get("ramp_curve", "linear")) if eng.get("ramp_curve") in curve_opts else 0
        curve = curve_opts[st.selectbox("Ramp Curve", range(len(curve_opts)),
                                         format_func=lambda i: curve_opts[i],
                                         index=curve_idx, key=f"{prefix}_curve")]
        post_opts = ["metrics_persist", "metrics_decay", "metrics_partial"]
        post_idx = post_opts.index(eng.get("post_engagement", "metrics_persist")) if eng.get("post_engagement") in post_opts else 0
        post = post_opts[st.selectbox("Post-Engagement", range(len(post_opts)),
                                       format_func=lambda i: post_opts[i].replace("_", " ").title(),
                                       index=post_idx, key=f"{prefix}_post")]
        decay = int(st.number_input("Decay Rate (days)",
                                     value=eng.get("decay_rate_days", 180), step=30,
                                     key=f"{prefix}_decay"))

    return {
        "duration_days": duration,
        "ramp_days": ramp,
        "ramp_curve": curve,
        "post_engagement": post,
        "decay_rate_days": decay,
    }


# ── URL Parameter Handling ─────────────────────────────────────────────

def _read_url_nav() -> dict | None:
    """Read navigation state from URL query parameters."""
    params = st.query_params
    client = params.get("client")
    if not client:
        return None
    model = params.get("model")
    deal = params.get("deal")
    compare = params.get("compare")
    if deal:
        return {"view": "deal", "client": client, "deal": deal}
    if compare:
        return {"view": "compare", "client": client, "deals": compare.split(",")}
    if model:
        return {"view": "model", "client": client, "model": model}
    return {"view": "client_overview", "client": client}


def _sync_url(nav: dict) -> None:
    """Update URL query parameters to reflect current navigation."""
    view = nav.get("view")
    if view == "model":
        st.query_params.update({"client": nav["client"], "model": nav["model"]})
    elif view == "deal":
        st.query_params.update({"client": nav["client"], "deal": nav["deal"]})
    elif view == "compare":
        st.query_params.update({"client": nav["client"], "compare": ",".join(nav.get("deals", []))})
    elif view == "client_overview":
        st.query_params.update({"client": nav["client"]})
    else:
        st.query_params.clear()


# On first load, check URL params before rendering sidebar
_url_nav = None
if "url_loaded" not in st.session_state:
    _url_nav = _read_url_nav()
    if _url_nav:
        st.session_state["url_loaded"] = True
        # Pre-set the client selector to match URL
        clients = list_clients()
        client_slugs = [slug for slug, _ in clients]
        if _url_nav.get("client") in client_slugs:
            st.session_state["nav_client"] = client_slugs.index(_url_nav["client"]) + 1
        # Pre-set active model/deal so breadcrumb mode activates
        if _url_nav.get("view") == "model":
            st.session_state["active_model"] = _url_nav["model"]
        elif _url_nav.get("view") == "deal":
            st.session_state["active_deal"] = _url_nav["deal"]

# ── Sidebar Navigation ────────────────────────────────────────────────

nav = render_sidebar_navigation()
view = nav.get("view", "home")

# Sync URL to current nav state
_sync_url(nav)


# ── Home ───────────────────────────────────────────────────────────────

if view == "home":
    st.markdown("# Financial Modeling")
    st.markdown("Select a client from the sidebar to get started, or create a new one.")

    clients = list_clients()
    if clients:
        st.markdown("### Your Clients")
        for slug, meta in clients:
            models = list_models(slug)
            deals = list_deals(slug)
            st.markdown(f"**{meta.name}** — {len(models)} models, {len(deals)} deals")
    else:
        st.info("No clients yet. Click **+ New Client** in the sidebar.")


# ── Client Overview ────────────────────────────────────────────────────

elif view == "client_overview":
    render_client_overview(nav["client"])


# ── Model Viewer ───────────────────────────────────────────────────────

elif view == "model":
    client_slug = nav["client"]
    model_slug = nav["model"]

    mf = load_model_file(client_slug, model_slug)
    if mf is None:
        st.error(f"Model not found: {model_slug}")
    else:
        st.markdown(f"## {mf.name}")
        if mf.description:
            st.caption(mf.description)
        if mf.base:
            st.info(f"Layered on: **{mf.base}** — showing {len(mf.overrides or {})} overridden fields")

        try:
            inp = resolve_model(client_slug, model_slug)
        except (FileNotFoundError, ValueError) as e:
            st.error(str(e))
            st.stop()

        # Editable inputs in sidebar
        st.sidebar.markdown("---")
        st.sidebar.markdown("### Edit Model")

        edited_inp = _render_model_inputs_editor(inp, prefix=f"edit_{model_slug}")

        # Unsaved changes detection
        has_changes = compute_overrides(inp, edited_inp)
        if has_changes:
            st.sidebar.warning(f"Unsaved changes ({len(has_changes)} fields)")

        save_label = "Save Changes" if not has_changes else f"Save Changes ({len(has_changes)})"
        if st.sidebar.button(save_label, key=f"save_{model_slug}", disabled=not has_changes):
            if mf.base is None:
                mf.inputs = model_inputs_to_dict(edited_inp)
            else:
                parent_inp = resolve_model(client_slug, mf.base)
                mf.overrides = compute_overrides(parent_inp, edited_inp)
            save_model(client_slug, model_slug, mf)
            st.sidebar.success("Saved!")
            st.rerun()

        render_model_view(edited_inp, model_name=model_slug)


# ── New Model ──────────────────────────────────────────────────────────

elif view == "new_model":
    client_slug = nav["client"]
    st.markdown("## Create New Model")

    with st.form("new_model_form"):
        nm_name = st.text_input("Model Name", value="")
        nm_description = st.text_area("Description", value="")

        # Choose base
        models = list_models(client_slug)
        model_options = ["— Base Model (standalone) —"] + [f"{mf.name} ({slug})" for slug, mf in models]
        model_slugs = [None] + [slug for slug, _ in models]
        base_idx = st.selectbox("Build on top of", range(len(model_options)),
                                format_func=lambda i: model_options[i])

        submitted = st.form_submit_button("Create Model")

    if submitted and nm_name:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", nm_name.lower().strip()).strip("-")
        base_slug = model_slugs[base_idx]

        if base_slug is None:
            # Base model with defaults
            create_base_model(client_slug, slug, nm_name, ModelInputs(), description=nm_description)
        else:
            # Layered model with no overrides yet
            create_layered_model(client_slug, slug, nm_name, base_slug, {}, description=nm_description)

        st.success(f"Created model: {nm_name}")
        st.rerun()


# ── Deal Viewer ────────────────────────────────────────────────────────

elif view == "deal":
    client_slug = nav["client"]
    deal_slug = nav["deal"]

    deal_file = load_deal(client_slug, deal_slug)
    if deal_file is None:
        st.error(f"Deal not found: {deal_slug}")
    else:
        st.markdown(f"## {deal_file.name}")
        if deal_file.notes:
            st.caption(deal_file.notes)

        # Show which models this deal compares
        before_mf = load_model_file(client_slug, deal_file.before_model)
        after_mf = load_model_file(client_slug, deal_file.after_model)
        before_name = before_mf.name if before_mf else deal_file.before_model
        after_name = after_mf.name if after_mf else deal_file.after_model
        before_desc = before_mf.description if before_mf and before_mf.description else "—"
        after_desc = after_mf.description if after_mf and after_mf.description else "—"
        after_overrides = len(after_mf.overrides) if after_mf and after_mf.overrides else 0
        after_base = after_mf.base if after_mf else None

        try:
            inp_before = resolve_model(client_slug, deal_file.before_model)
            inp_after = resolve_model(client_slug, deal_file.after_model)
        except (FileNotFoundError, ValueError) as e:
            st.error(f"Could not resolve models: {e}")
            st.stop()

        comp = get_compensation_structure(deal_file)
        eng = get_engagement_config(deal_file)

        # Model reference panel
        with st.expander("Models being compared", expanded=True):
            mc1, mc2 = st.columns(2)
            with mc1:
                st.markdown(f"**Baseline: {before_name}**")
                st.caption(before_desc)
                st.markdown(f"""
| Parameter | Value |
|-----------|-------|
| Channels | {'Inbound ' if inp_before.use_inbound else ''}{'Outbound ' if inp_before.use_outbound else ''}{'Organic ' if inp_before.use_organic else ''}{'Viral' if inp_before.use_viral else ''} |
| Price | ${inp_before.price_of_offer:,.0f} |
| Churn | {inp_before.churn_rate}% |
| Fixed Costs | ${inp_before.fixed_costs_per_month:,.0f}/mo |
""")
            with mc2:
                st.markdown(f"**Target: {after_name}**")
                st.caption(after_desc)
                if after_base:
                    st.markdown(f"Based on: {after_base} | {after_overrides} fields modified")
                # Show the deltas
                from store.serialization import compute_overrides as _co
                deltas = _co(inp_before, inp_after)
                if deltas:
                    delta_lines = []
                    for k, v in deltas.items():
                        old = getattr(inp_before, k)
                        delta_lines.append(f"| `{k}` | {old} → **{v}** |")
                    st.markdown("| Field | Change |\n|-------|--------|\n" + "\n".join(delta_lines))
                else:
                    st.markdown("*No differences from baseline*")

        # Compensation editor in sidebar
        st.sidebar.markdown("---")
        st.sidebar.markdown("### Compensation")
        edited_comp = _render_comp_editor(comp, prefix=f"deal_{deal_slug}")
        edited_eng = _render_engagement_editor(eng, prefix=f"deal_{deal_slug}")

        # Unsaved changes detection
        saved_comp = comp_structure_to_dict(comp)
        current_comp = comp_structure_to_dict(edited_comp)
        comp_changed = saved_comp != current_comp
        eng_changed = eng != edited_eng
        has_deal_changes = comp_changed or eng_changed

        if has_deal_changes:
            st.sidebar.warning("Unsaved changes")

        if st.sidebar.button("Save Deal", key=f"save_deal_{deal_slug}", disabled=not has_deal_changes):
            deal_file.compensation = comp_structure_to_dict(edited_comp)
            deal_file.engagement = edited_eng
            save_deal(client_slug, deal_slug, deal_file)
            st.sidebar.success("Saved!")
            st.rerun()

        render_deal_view(inp_before, inp_after, edited_comp, edited_eng)


# ── New Deal ───────────────────────────────────────────────────────────

elif view == "new_deal":
    client_slug = nav["client"]
    st.markdown("## Create New Deal")

    models = list_models(client_slug)
    if len(models) < 2:
        st.warning("You need at least 2 models (a before and an after) to create a deal.")
        st.stop()

    model_options = [f"{mf.name} ({slug})" for slug, mf in models]
    model_slugs = [slug for slug, _ in models]

    with st.form("new_deal_form"):
        nd_name = st.text_input("Deal Name", value="")
        nd_notes = st.text_area("Notes", value="")

        col1, col2 = st.columns(2)
        with col1:
            before_idx = st.selectbox("Before Model (baseline)", range(len(model_options)),
                                      format_func=lambda i: model_options[i])
        with col2:
            after_idx = st.selectbox("After Model (with improvements)", range(len(model_options)),
                                     format_func=lambda i: model_options[i],
                                     index=min(1, len(model_options) - 1))

        # Preset compensation
        preset_names = list(ALL_PRESETS.keys())
        preset_choice = st.selectbox("Compensation Preset", ["Custom (defaults)"] + preset_names)

        submitted = st.form_submit_button("Create Deal")

    if submitted and nd_name:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", nd_name.lower().strip()).strip("-")

        if preset_choice != "Custom (defaults)":
            comp = ALL_PRESETS[preset_choice]()
        else:
            comp = CompensationStructure()

        deal_file = DealFile(
            name=nd_name,
            before_model=model_slugs[before_idx],
            after_model=model_slugs[after_idx],
            compensation=comp_structure_to_dict(comp),
            engagement={
                "duration_days": 365,
                "ramp_days": 60,
                "ramp_curve": "linear",
                "post_engagement": "metrics_persist",
                "decay_rate_days": 180,
            },
            notes=nd_notes,
        )
        save_deal(client_slug, slug, deal_file)
        st.success(f"Created deal: {nd_name}")
        st.rerun()


# ── Deal Comparison ────────────────────────────────────────────────────

elif view == "compare":
    client_slug = nav["client"]
    deal_slugs = nav.get("deals", [])
    render_deal_comparison(client_slug, deal_slugs)


# ── Wizard ─────────────────────────────────────────────────────────────

elif view == "wizard":
    client_slug = nav["client"]
    render_wizard(client_slug)
