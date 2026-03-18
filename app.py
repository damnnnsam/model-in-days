import streamlit as st

st.set_page_config(
    page_title="Financial Model — Marketing to Equity Value",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from engine.simulation import run_simulation, to_monthly
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
)

st.title("Marketing Metrics → Equity Value")
st.caption(
    "Full-stack financial model: granular marketing inputs → revenue → P&L → FCF → DCF / EBITDA valuation"
)

inp = render_sidebar()

sim = run_simulation(inp)
monthly = to_monthly(sim)
val = compute_valuation(inp, sim)

# ── Time cursor ─────────────────────────────────────────────────────
total_months = inp.time_max // 30
col_slider, col_label = st.columns([5, 1])
with col_slider:
    view_month = st.slider(
        "View metrics at month",
        min_value=1, max_value=total_months, value=total_months,
        key="time_cursor",
    )
with col_label:
    years = view_month / 12
    st.markdown(f"**≈ {years:.1f} years**")

cursor_day = view_month * 30
kpis = compute_kpis(inp, sim, at_day=cursor_day)

# ── KPI Dashboard ───────────────────────────────────────────────────
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
    st.plotly_chart(add_cursor(customers_chart(monthly), view_month), use_container_width=True)
    st.plotly_chart(add_cursor(new_customers_by_channel(monthly), view_month), use_container_width=True)

with tab_rev:
    st.plotly_chart(add_cursor(revenue_chart(monthly), view_month), use_container_width=True)
    st.plotly_chart(add_cursor(cash_collected_chart(monthly), view_month), use_container_width=True)

with tab_costs:
    st.plotly_chart(add_cursor(cost_breakdown_chart(monthly), view_month), use_container_width=True)

with tab_pnl:
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(add_cursor(pnl_chart(monthly), view_month), use_container_width=True)
    with col2:
        st.plotly_chart(add_cursor(fcf_chart(monthly), view_month), use_container_width=True)
    st.plotly_chart(add_cursor(cash_balance_chart(monthly), view_month), use_container_width=True)

with tab_sens:
    render_sensitivity(inp)

with tab_compare:
    render_scenario_comparison(inp)

with tab_export:
    render_export(inp, kpis, val, monthly)

# ── Raw Data ────────────────────────────────────────────────────────
with st.expander("Monthly Data Table"):
    st.dataframe(monthly, use_container_width=True, height=400)
