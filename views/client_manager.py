"""
Client and model management UI.

Renders in the sidebar: client picker, model tree, create/edit buttons.
Renders in the main area: client overview when no model/deal is selected.
"""
from __future__ import annotations

import re
import streamlit as st

from store.client import list_clients, create_client, load_client_meta, save_client_meta, ClientMeta
from store.model import list_models, get_model_tree, load_model_file, delete_model
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
