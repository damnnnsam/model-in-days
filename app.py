import streamlit as st

st.set_page_config(
    page_title="Model In Days",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from engine.simulation import run_simulation, to_monthly, to_daily_df
from engine.valuation import compute_valuation
from engine.metrics import compute_kpis
from ui.sidebar import render_sidebar
from ui.dashboard import (
    render_kpi_cards, render_valuation_panel, render_sensitivity,
    render_scenario_comparison, render_export,
)
from ui.charts import (
    customers_chart,
    new_customers_by_channel,
    revenue_chart,
    cash_collected_chart,
    cost_breakdown_chart,
    pnl_chart,
    cash_balance_chart,
    fcf_chart,
    valuation_waterfall,
    add_cursor,
    hero_chart,
)

st.title("Model In Days")
st.caption("Use this model to find the most profitable direction for your business and to understand what metrics really matter.")

inp = render_sidebar()

import json, os
with open(os.path.join(os.path.dirname(__file__), "current_model.json"), "w") as _f:
    json.dump(inp.__dict__, _f, indent=2, default=str)

from engine.url_state import encode_model
encoded = encode_model(inp)
share_url = f"?m={encoded}"
st.sidebar.markdown("---")
st.sidebar.code(share_url, language=None)
if st.sidebar.button("Copy Share Link", key="share_btn"):
    st.sidebar.success("Link ready — copy the URL above and share it.")

sim = run_simulation(inp)
daily = to_daily_df(sim)
monthly = to_monthly(sim)
val = compute_valuation(inp, sim)

# ── Time cursor ─────────────────────────────────────────────────────
total_days = inp.time_max
col_slider, col_label = st.columns([5, 1])
with col_slider:
    cursor_day = st.slider(
        "View metrics at day",
        min_value=1, max_value=total_days, value=total_days,
        key="time_cursor",
    )
with col_label:
    years = cursor_day / 365
    st.markdown(f"**≈ {years:.1f} years**")

kpis = compute_kpis(inp, sim, at_day=cursor_day)

# ── Hero chart ──────────────────────────────────────────────────────
st.plotly_chart(hero_chart(daily, cursor_day=cursor_day), use_container_width=True)

# ── KPI strip ───────────────────────────────────────────────────────
def _fd(v):
    if abs(v) >= 1_000_000: return f"${v/1_000_000:,.1f}M"
    if abs(v) >= 1_000: return f"${v/1_000:,.1f}K"
    return f"${v:,.0f}"

ttp = f"{kpis.time_to_profitability_months} mo" if kpis.time_to_profitability_months > 0 else "Never"
k1, k2, k3, k4, k5, k6, k7, k8 = st.columns(8)
k1.metric("Active Cust.", f"{kpis.active_customers:,.0f}")
k2.metric("Monthly Rev.", _fd(kpis.monthly_revenue))
k3.metric("Monthly FCF", _fd(kpis.monthly_fcf))
k4.metric("TTP", ttp)
k5.metric("CAC", _fd(kpis.cac_blended))
k6.metric("LTV / CAC", f"{kpis.ltv_cac_ratio:.1f}x")
k7.metric("Profit/Cust/Mo", _fd(kpis.profit_per_customer_per_month))
k8.metric("Cash Needed", _fd(kpis.cash_needed))

with st.expander("All Metrics"):
    render_kpi_cards(kpis)

st.divider()

# ── Tabs for different views ────────────────────────────────────────
tab_val, tab_alpha, tab_cust, tab_rev, tab_costs, tab_pnl, tab_sens, tab_compare, tab_export = st.tabs([
    "Valuation", "GTM Alpha", "Customers", "Revenue & Cash", "Costs", "P&L & FCF",
    "Sensitivity", "Compare Scenarios", "Export",
])

with tab_val:
    render_valuation_panel(val, inp)
    st.divider()
    st.plotly_chart(
        valuation_waterfall(
            pv_fcf=val.pv_fcf,
            pv_terminal=val.pv_terminal_value,
            debt=inp.debt,
            cash=val.cash_at_valuation,
            equity=val.equity_value_dcf,
        ),
        use_container_width=True,
    )

with tab_alpha:
    from engine.inputs import ModelInputs as _MI

    st.subheader("GTM Alpha — How Small Improvements Create Outsized Value")
    st.caption("See how improving a single cold email metric shifts the entire business trajectory and equity value.")

    ac1, ac2 = st.columns(2)
    with ac1:
        alpha_metric = st.selectbox("Metric to stress-test", [
            "Reply rate (contact → lead %)",
            "Lead → customer rate (%)",
            "Sends per month",
            "Price of offer ($)",
            "Churn rate (%)",
            "Cost to fulfill (%)",
        ], key="alpha_metric")
    with ac2:
        alpha_years = st.selectbox("Evaluate equity at", [
            "3 years", "5 years", "7 years",
        ], index=1, key="alpha_years")

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

    # Which channel must be enabled for each metric
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
        test_inp = _MI(**p)
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

    import plotly.graph_objects as go
    from ui.charts import COLORS

    eq_values = [r["equity"] for r in results]
    labels = [f"{unit}{v:,.0f}" if unit == "$" else f"{v:g}{unit}" for v in test_values]
    bar_colors = [COLORS["green"] if r["value"] == current_val or (not base_eq and i == 0)
                  else COLORS["primary"] for i, r in enumerate(results)]
    # Highlight current value
    for i, r in enumerate(results):
        if abs(r["value"] - current_val) < 0.01:
            bar_colors[i] = COLORS["amber"]

    fig_eq = go.Figure(go.Bar(
        x=labels, y=eq_values, marker_color=bar_colors,
        text=[f"${v/1_000_000:,.1f}M" for v in eq_values],
        textposition="outside",
        hovertemplate="%{x}: $%{y:,.0f}<extra></extra>",
    ))
    fig_eq.update_layout(
        title=f"Equity Value (DCF) by {alpha_metric}",
        yaxis_title="Equity Value ($)",
        template="plotly_white", height=400,
        margin=dict(l=40, r=20, t=40, b=40),
    )
    st.plotly_chart(fig_eq, use_container_width=True)

    # Delta table
    st.markdown("### Impact Breakdown")
    import pandas as pd
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

    # The punchline — find lowest and highest, compute the full range delta
    if len(results) >= 2:
        low = results[0]
        high = results[-1]
        delta = high["equity"] - low["equity"]
        low_label = f"{unit}{low['value']:,.0f}" if unit == "$" else f"{low['value']:g}{unit}"
        high_label = f"{unit}{high['value']:,.0f}" if unit == "$" else f"{high['value']:g}{unit}"
        direction = "increasing" if delta > 0 else "decreasing"
        st.markdown(f"""
---
**The takeaway:** Moving **{alpha_metric.lower()}** from **{low_label}** to **{high_label}** 
{"creates" if delta > 0 else "destroys"} **${abs(delta)/1_000_000:,.1f}M** in equity value over {alpha_years} — 
a **{abs(delta / low['equity'] * 100) if low['equity'] != 0 else 0:,.0f}%** change from the low end.
""")

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

# ── Raw Data ────────────────────────────────────────────────────────
with st.expander("Monthly Data Table"):
    st.dataframe(monthly, use_container_width=True, height=400)
