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
tab_val, tab_cust, tab_rev, tab_costs, tab_pnl, tab_sens, tab_compare, tab_export = st.tabs([
    "Valuation", "Customers", "Revenue & Cash", "Costs", "P&L & FCF",
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
