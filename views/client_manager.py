"""
Client and model management UI.

Renders in the sidebar: client picker, model tree, create/edit buttons.
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

    Returns a dict describing the current selection:
      {"view": "home"}
      {"view": "model", "client": slug, "model": slug}
      {"view": "deal", "client": slug, "deal": slug}
      {"view": "compare", "client": slug, "deals": [slug, ...]}
      {"view": "new_model", "client": slug, "base": slug|None}
      {"view": "new_deal", "client": slug}
    """
    st.sidebar.title("Financial Modeling")

    # ── Client selector ────────────────────────────────────────────
    clients = list_clients()
    client_names = ["— Select Client —"] + [f"{meta.name}" for _, meta in clients]
    client_slugs = [None] + [slug for slug, _ in clients]

    selected_idx = st.sidebar.selectbox(
        "Client", range(len(client_names)),
        format_func=lambda i: client_names[i],
        key="nav_client",
    )

    # New client button
    if st.sidebar.button("+ New Client", key="nav_new_client"):
        st.session_state["show_new_client"] = True

    if st.session_state.get("show_new_client"):
        with st.sidebar.form("new_client_form"):
            nc_name = st.text_input("Client Name")
            nc_industry = st.text_input("Industry", value="")
            nc_notes = st.text_area("Notes", value="")
            if st.form_submit_button("Create Client"):
                if nc_name:
                    slug = _slugify(nc_name)
                    create_client(slug, nc_name, nc_industry, nc_notes)
                    st.session_state["show_new_client"] = False
                    st.session_state["nav_client"] = len(client_slugs)  # will be stale, rerun
                    st.rerun()

    if selected_idx == 0 or selected_idx is None:
        return {"view": "home"}

    client_slug = client_slugs[selected_idx]
    st.sidebar.markdown("---")

    # ── Model tree ─────────────────────────────────────────────────
    st.sidebar.markdown("**Models**")
    tree = get_model_tree(client_slug)
    selection = _render_model_tree(tree, client_slug, depth=0)

    # New model button
    if st.sidebar.button("+ New Model", key="nav_new_model"):
        return {"view": "new_model", "client": client_slug, "base": None}

    # ── Deals ──────────────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Deals**")
    deals = list_deals(client_slug)

    deal_selection = None
    for deal_slug, deal_file in deals:
        if st.sidebar.button(f"  {deal_file.name}", key=f"nav_deal_{deal_slug}"):
            deal_selection = deal_slug

    if st.sidebar.button("+ New Deal", key="nav_new_deal"):
        return {"view": "new_deal", "client": client_slug}

    # ── Compare Deals ──────────────────────────────────────────────
    if len(deals) >= 2:
        st.sidebar.markdown("---")
        if st.sidebar.button("Compare Deals", key="nav_compare"):
            return {"view": "compare", "client": client_slug, "deals": [s for s, _ in deals]}

    # ── Determine what to show ─────────────────────────────────────
    if deal_selection:
        return {"view": "deal", "client": client_slug, "deal": deal_selection}

    if selection:
        return {"view": "model", "client": client_slug, "model": selection}

    return {"view": "client_overview", "client": client_slug}


def _render_model_tree(nodes: list[dict], client_slug: str, depth: int) -> str | None:
    """Render model tree in sidebar. Returns slug of selected model or None."""
    selected = None
    for node in nodes:
        indent = "  " * depth
        prefix = "▸ " if node["children"] else "  "
        label = f"{indent}{prefix}{node['name']}"
        if st.sidebar.button(label, key=f"nav_model_{node['slug']}"):
            selected = node["slug"]
        # Recurse into children
        child_sel = _render_model_tree(node["children"], client_slug, depth + 1)
        if child_sel:
            selected = child_sel
    return selected


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


def _do_import(client_slug: str, url_or_param: str, name: str) -> None:
    """Import a model from an old URL-encoded string."""
    import base64
    import json
    import zlib
    from urllib.parse import urlparse, parse_qs

    # Extract the encoded parameter from a full URL or bare string
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

    # Try to decode as Model 1 format (?m= → ModelInputs)
    try:
        compressed = base64.urlsafe_b64decode(encoded)
        data = json.loads(zlib.decompress(compressed).decode())
    except Exception as e:
        st.error(f"Could not decode: {e}")
        return

    # Check if it's a Model 1 format (dict with ModelInputs fields)
    from engine.inputs import ModelInputs
    from dataclasses import fields as dc_fields
    model_fields = {f.name for f in dc_fields(ModelInputs)}

    if any(k in model_fields for k in data.keys()):
        # Model 1 format — direct ModelInputs dict
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
        # Model 2 format — session state dict with prefixed keys
        # Extract "before" state as a base model
        before_fields = {k[2:]: v for k, v in data.items() if k.startswith("b_")}
        if before_fields:
            # Map widget keys back to ModelInputs fields where possible
            from store.serialization import dict_to_model_inputs
            try:
                inp = dict_to_model_inputs(before_fields)
            except Exception:
                inp = ModelInputs()  # fallback to defaults
            slug = _slugify(name)
            create_base_model(client_slug, slug, name, inp, description="Imported from deal URL (before state)")
            st.success(f"Imported before-state as base model: **{name}**")
            st.rerun()
        else:
            st.error("Could not extract model data from deal URL.")
    else:
        st.error("Unrecognized data format.")
