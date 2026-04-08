"""
Client and model management UI.

Renders in the sidebar: client picker, model tree (or breadcrumb when inside a model/deal).
Renders in the main area: client overview when no model/deal is selected.
"""
from __future__ import annotations

import re
import streamlit as st

from store.client import list_clients, create_client, load_client_meta, save_client_meta, ClientMeta
from store.model import list_models, get_model_tree, load_model_file, delete_model, create_base_model
from store.deal import list_deals, delete_deal


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def render_sidebar_navigation() -> dict:
    """
    Render client/model/deal navigation in the sidebar.

    When a model or deal is active, navigation collapses to a breadcrumb
    so sidebar space is used for inputs.
    """
    # ── Client selector ────────────────────────────────────────────
    clients = list_clients()
    client_names = ["— Select Client —"] + [meta.name for _, meta in clients]
    client_slugs = [None] + [slug for slug, _ in clients]

    # If a new client was just created, pre-select it before the widget renders
    pending = st.session_state.pop("_pending_client", None)
    if pending and pending in client_slugs:
        st.session_state["nav_client"] = client_slugs.index(pending)

    selected_idx = st.sidebar.selectbox(
        "Client", range(len(client_names)),
        format_func=lambda i: client_names[i],
        key="nav_client",
        label_visibility="collapsed",
    )

    if selected_idx == 0 or selected_idx is None:
        # No client selected — show new client button
        if st.sidebar.button("+ New Client", key="nav_new_client_home"):
            st.session_state["show_new_client"] = True
        if st.session_state.get("show_new_client"):
            _render_new_client_form(client_slugs)
        return {"view": "home"}

    client_slug = client_slugs[selected_idx]
    client_meta = load_client_meta(client_slug)
    client_name = client_meta.name if client_meta else client_slug

    # ── Check if wizard is active ─────────────────────────────────
    if st.session_state.get("active_wizard"):
        st.sidebar.caption(f"{client_name} > New Engagement")
        if st.sidebar.button("← Back to overview", key="nav_wiz_back", use_container_width=True):
            st.session_state.pop("active_wizard", None)
            for k in list(st.session_state.keys()):
                if k.startswith("wiz_"):
                    del st.session_state[k]
            st.rerun()
        st.sidebar.markdown("---")
        return {"view": "wizard", "client": client_slug}

    # ── Check if we're inside a model or deal ──────────────────────
    active_model = st.session_state.get("active_model")
    active_deal = st.session_state.get("active_deal")

    # Verify the active model/deal actually exists for this client
    if active_model:
        mf = load_model_file(client_slug, active_model)
        if mf is None:
            st.session_state.pop("active_model", None)
            active_model = None
    if active_deal:
        from store.deal import load_deal as _load_deal
        df = _load_deal(client_slug, active_deal)
        if df is None:
            st.session_state.pop("active_deal", None)
            active_deal = None

    # If active, render breadcrumb mode (compact)
    if active_model or active_deal:
        return _render_breadcrumb_mode(client_slug, client_name, active_model, active_deal)

    # Otherwise, render full navigation tree
    return _render_full_nav(client_slug, client_name)


def _render_breadcrumb_mode(client_slug: str, client_name: str,
                            active_model: str | None, active_deal: str | None) -> dict:
    """Compact breadcrumb navigation — 2-3 lines, rest is for inputs."""

    if active_model:
        mf = load_model_file(client_slug, active_model)
        item_name = mf.name if mf else active_model
        label = f"{client_name} > {item_name}"
    else:
        from store.deal import load_deal
        df = load_deal(client_slug, active_deal)
        item_name = df.name if df else active_deal
        label = f"{client_name} > {item_name}"

    st.sidebar.caption(label)

    # Quick switch dropdown
    models = list_models(client_slug)
    deals = list_deals(client_slug)
    all_items = (
        [("model", slug, f"Model: {mf.name}") for slug, mf in models] +
        [("deal", slug, f"Deal: {df.name}") for slug, df in deals]
    )

    # Find current index
    current_key = ("model", active_model) if active_model else ("deal", active_deal)
    current_idx = 0
    for i, (typ, slug, _) in enumerate(all_items):
        if (typ, slug) == current_key:
            current_idx = i
            break

    if st.sidebar.button("← Back to overview", key="nav_back", use_container_width=True):
        st.session_state.pop("active_model", None)
        st.session_state.pop("active_deal", None)
        st.rerun()

    new_idx = st.sidebar.selectbox(
        "Switch", range(len(all_items)),
        format_func=lambda i: all_items[i][2],
        index=current_idx,
        key="nav_switch",
        label_visibility="collapsed",
    )

    # Handle switch
    typ, slug, _ = all_items[new_idx]
    if typ == "model" and slug != active_model:
        st.session_state["active_model"] = slug
        st.session_state.pop("active_deal", None)
        st.rerun()
    elif typ == "deal" and slug != active_deal:
        st.session_state["active_deal"] = slug
        st.session_state.pop("active_model", None)
        st.rerun()

    st.sidebar.markdown("---")

    if active_model:
        return {"view": "model", "client": client_slug, "model": active_model}
    else:
        return {"view": "deal", "client": client_slug, "deal": active_deal}


def _render_full_nav(client_slug: str, client_name: str) -> dict:
    """Full navigation tree — shown when not inside a model/deal."""

    # New client button
    if st.sidebar.button("+ New Client", key="nav_new_client"):
        st.session_state["show_new_client"] = True
    if st.session_state.get("show_new_client"):
        clients = list_clients()
        client_slugs = [None] + [slug for slug, _ in clients]
        _render_new_client_form(client_slugs)

    st.sidebar.markdown("---")

    # ── Primary action ─────────────────────────────────────────────
    if st.sidebar.button("New Engagement", key="nav_wizard", type="primary", use_container_width=True):
        st.session_state["active_wizard"] = True
        st.session_state.pop("active_model", None)
        st.session_state.pop("active_deal", None)
        st.rerun()

    st.sidebar.markdown("---")

    # ── Models ─────────────────────────────────────────────────────
    st.sidebar.markdown("**Models**")
    tree = get_model_tree(client_slug)
    model_selection = _render_model_tree(tree, depth=0)

    if st.sidebar.button("+ New Model", key="nav_new_model"):
        return {"view": "new_model", "client": client_slug, "base": None}

    # ── Deals ──────────────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Deals**")
    deals = list_deals(client_slug)

    deal_selection = None
    for deal_slug, deal_file in deals:
        label = f"  {deal_file.name}"
        if st.sidebar.button(label, key=f"nav_deal_{deal_slug}", help=f"{deal_file.before_model} → {deal_file.after_model}"):
            deal_selection = deal_slug

    if st.sidebar.button("+ New Deal", key="nav_new_deal"):
        return {"view": "new_deal", "client": client_slug}

    # Compare
    if len(deals) >= 2:
        st.sidebar.markdown("---")
        if st.sidebar.button("Compare Deals", key="nav_compare"):
            return {"view": "compare", "client": client_slug, "deals": [s for s, _ in deals]}

    # ── Handle clicks — set active and rerun to switch to breadcrumb ──
    if deal_selection:
        st.session_state["active_deal"] = deal_selection
        st.session_state.pop("active_model", None)
        st.rerun()

    if model_selection:
        st.session_state["active_model"] = model_selection
        st.session_state.pop("active_deal", None)
        st.rerun()

    return {"view": "client_overview", "client": client_slug}


def _render_new_client_form(client_slugs: list) -> None:
    """Inline form for creating a new client."""
    with st.sidebar.form("new_client_form"):
        nc_name = st.text_input("Client Name")
        nc_industry = st.text_input("Industry", value="")
        nc_notes = st.text_area("Notes", value="")
        if st.form_submit_button("Create Client"):
            if nc_name:
                slug = _slugify(nc_name)
                create_client(slug, nc_name, nc_industry, nc_notes)
                st.session_state["show_new_client"] = False
                st.session_state["_pending_client"] = slug
                st.rerun()


def _render_model_tree(nodes: list[dict], depth: int) -> str | None:
    """Render model tree in sidebar. Returns slug of clicked model or None."""
    selected = None
    for node in nodes:
        indent = "› " * depth
        label = f"{indent}{node['name']}"
        if st.sidebar.button(label, key=f"nav_model_{node['slug']}", use_container_width=True):
            selected = node["slug"]
        child_sel = _render_model_tree(node["children"], depth + 1)
        if child_sel:
            selected = child_sel
    return selected


# ── Client Overview (main area) ────────────────────────────────────────

def render_client_overview(client_slug: str) -> None:
    """Render client overview in the main area."""
    meta = load_client_meta(client_slug)
    if meta is None:
        st.error(f"Client not found: {client_slug}")
        return

    st.markdown(f"# {meta.name}")
    if meta.industry:
        st.markdown(f"**Industry:** {meta.industry}")
    if meta.notes:
        st.markdown(f"**Notes:** {meta.notes}")

    st.markdown("---")

    # Models
    models = list_models(client_slug)
    st.markdown("### Models")
    if models:
        for slug, mf in models:
            col1, col2 = st.columns([4, 1])
            with col1:
                base_label = f" (based on: {mf.base})" if mf.base else " (base)"
                st.markdown(f"**{mf.name}**{base_label}")
                if mf.description:
                    st.caption(mf.description)
            with col2:
                if st.button("Delete", key=f"del_model_{slug}"):
                    delete_model(client_slug, slug)
                    st.rerun()
    else:
        st.info("No models yet. Create one to get started.")

    st.markdown("---")

    # Deals
    deals = list_deals(client_slug)
    st.markdown("### Deals")
    if deals:
        for slug, df in deals:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{df.name}** ({df.before_model} → {df.after_model})")
                if df.notes:
                    st.caption(df.notes)
            with col2:
                if st.button("Delete", key=f"del_deal_{slug}"):
                    delete_deal(client_slug, slug)
                    st.rerun()
    else:
        st.info("No deals yet. Create a deal to connect two models with a compensation structure.")

    # ── Import from URL ────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Import from URL")
    st.caption("Paste a shared model URL (with `?m=...` or `?d=...` parameter) to import it as a new base model.")

    with st.form("import_url_form"):
        import_url = st.text_input("URL or encoded parameter", placeholder="https://...?m=eNpt... or just the encoded string")
        import_name = st.text_input("Save as model name", placeholder="Imported Model")
        import_submitted = st.form_submit_button("Import")

    if import_submitted and import_url and import_name:
        _do_import(client_slug, import_url, import_name)

    # ── Import from Google Sheets ─────────────────────────────────
    st.markdown("---")
    st.markdown("### Import from Google Sheets")
    st.caption("Paste a Google Sheets URL to import model inputs. The sheet must have Parameter and Value columns.")

    with st.form("import_sheets_form"):
        sheets_url = st.text_input("Google Sheets URL", placeholder="https://docs.google.com/spreadsheets/d/...")
        sheets_name = st.text_input("Save as model name", placeholder="Imported from Sheets")
        sheets_submitted = st.form_submit_button("Import from Sheets")

    if sheets_submitted and sheets_url and sheets_name:
        try:
            from sheets.google_sheets import import_model_from_sheets
            inp = import_model_from_sheets(sheets_url)
            slug = _slugify(sheets_name)
            create_base_model(client_slug, slug, sheets_name, inp, description="Imported from Google Sheets")
            st.success(f"Imported as base model: **{sheets_name}**")
            st.rerun()
        except Exception as e:
            st.error(f"Import failed: {e}")


def _do_import(client_slug: str, url_or_param: str, name: str) -> None:
    """Import a model from an old URL-encoded string."""
    import base64
    import json
    import zlib
    from urllib.parse import urlparse, parse_qs

    encoded = url_or_param.strip()
    if "?" in encoded:
        parsed = urlparse(encoded)
        params = parse_qs(parsed.query)
        if "m" in params:
            encoded = params["m"][0]
        elif "d" in params:
            encoded = params["d"][0]
        else:
            st.error("URL has no `?m=` or `?d=` parameter.")
            return

    try:
        compressed = base64.urlsafe_b64decode(encoded)
        data = json.loads(zlib.decompress(compressed).decode())
    except Exception as e:
        st.error(f"Could not decode: {e}")
        return

    from engine.inputs import ModelInputs
    from dataclasses import fields as dc_fields
    model_fields = {f.name for f in dc_fields(ModelInputs)}

    if any(k in model_fields for k in data.keys()):
        from store.serialization import dict_to_model_inputs
        try:
            inp = dict_to_model_inputs(data)
        except Exception as e:
            st.error(f"Could not parse ModelInputs: {e}")
            return
        slug = _slugify(name)
        create_base_model(client_slug, slug, name, inp, description="Imported from URL")
        st.success(f"Imported as base model: **{name}**")
        st.rerun()

    elif any(k.startswith(("b_", "a_", "sb_", "d_")) for k in data.keys()):
        before_fields = {k[2:]: v for k, v in data.items() if k.startswith("b_")}
        if before_fields:
            from store.serialization import dict_to_model_inputs
            try:
                inp = dict_to_model_inputs(before_fields)
            except Exception:
                inp = ModelInputs()
            slug = _slugify(name)
            create_base_model(client_slug, slug, name, inp, description="Imported from deal URL (before state)")
            st.success(f"Imported before-state as base model: **{name}**")
            st.rerun()
        else:
            st.error("Could not extract model data from deal URL.")
    else:
        st.error("Unrecognized data format.")
