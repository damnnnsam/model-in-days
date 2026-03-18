from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd
import numpy as np

from engine.simulation import SimulationResult
from engine.inputs import ModelInputs

COLORS = {
    "primary": "#4F46E5",
    "green": "#10B981",
    "red": "#EF4444",
    "amber": "#F59E0B",
    "sky": "#0EA5E9",
    "purple": "#8B5CF6",
    "pink": "#EC4899",
    "gray": "#6B7280",
}

LAYOUT_DEFAULTS = dict(
    template="plotly_white",
    height=380,
    margin=dict(l=40, r=20, t=40, b=40),
    font=dict(size=12),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def _month_axis(df: pd.DataFrame) -> list[str]:
    return [f"M{m}" for m in df["month"]]


def add_cursor(fig: go.Figure, month: int | None) -> go.Figure:
    """Add a vertical line at the given month to show the KPI cursor position."""
    if month is not None:
        fig.add_vline(
            x=f"M{month}", line_dash="dash", line_color="#9CA3AF",
            annotation_text=f"M{month}", annotation_position="top",
        )
    return fig


def customers_chart(df: pd.DataFrame) -> go.Figure:
    x = _month_axis(df)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["active_customers"], name="Active Customers",
        fill="tozeroy", line=dict(color=COLORS["primary"]),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["cumulative_customers"], name="Cumulative Customers",
        line=dict(color=COLORS["gray"], dash="dot"),
    ))
    fig.update_layout(title="Customers", yaxis_title="Customers", **LAYOUT_DEFAULTS)
    return fig


def new_customers_by_channel(df: pd.DataFrame) -> go.Figure:
    x = _month_axis(df)
    fig = go.Figure()
    channels = [
        ("new_customers_inbound", "Inbound", COLORS["sky"]),
        ("new_customers_outbound", "Outbound", COLORS["purple"]),
        ("new_customers_organic", "Organic", COLORS["green"]),
        ("new_customers_viral", "Viral", COLORS["pink"]),
    ]
    for col, name, color in channels:
        if df[col].sum() > 0:
            fig.add_trace(go.Bar(x=x, y=df[col], name=name, marker_color=color))
    fig.update_layout(
        title="New Customers by Channel (Monthly)",
        barmode="stack", yaxis_title="New Customers", **LAYOUT_DEFAULTS,
    )
    return fig


def revenue_chart(df: pd.DataFrame) -> go.Figure:
    x = _month_axis(df)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=df["revenue_new"], name="New Revenue", marker_color=COLORS["primary"],
    ))
    fig.add_trace(go.Bar(
        x=x, y=df["revenue_renewal"], name="Renewal Revenue", marker_color=COLORS["green"],
    ))
    fig.update_layout(
        title="Revenue (Monthly)", barmode="stack",
        yaxis_title="$", **LAYOUT_DEFAULTS,
    )
    return fig


def cash_collected_chart(df: pd.DataFrame) -> go.Figure:
    x = _month_axis(df)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["cash_collected_total"], name="Cash Collected",
        fill="tozeroy", line=dict(color=COLORS["green"]),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["cost_total"], name="Total Costs",
        line=dict(color=COLORS["red"]),
    ))
    fig.update_layout(title="Cash Collected vs Costs (Monthly)", yaxis_title="$", **LAYOUT_DEFAULTS)
    return fig


def cost_breakdown_chart(df: pd.DataFrame) -> go.Figure:
    x = _month_axis(df)
    fig = go.Figure()
    costs = [
        ("cost_marketing", "Marketing", COLORS["sky"]),
        ("cost_sales", "Sales", COLORS["amber"]),
        ("cost_fulfillment", "Fulfillment", COLORS["purple"]),
        ("cost_fixed", "Fixed", COLORS["gray"]),
        ("cost_transaction_fees", "Transaction Fees", COLORS["pink"]),
        ("cost_refunds", "Refunds", COLORS["red"]),
    ]
    for col, name, color in costs:
        fig.add_trace(go.Bar(x=x, y=df[col], name=name, marker_color=color))
    fig.update_layout(
        title="Cost Breakdown (Monthly)", barmode="stack",
        yaxis_title="$", **LAYOUT_DEFAULTS,
    )
    return fig


def pnl_chart(df: pd.DataFrame) -> go.Figure:
    x = _month_axis(df)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["gross_profit"], name="Gross Profit",
        line=dict(color=COLORS["green"]),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["ebitda"], name="EBITDA",
        line=dict(color=COLORS["primary"]),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["net_income"], name="Net Income",
        line=dict(color=COLORS["amber"]),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title="P&L (Monthly)", yaxis_title="$", **LAYOUT_DEFAULTS)
    return fig


def cash_balance_chart(df: pd.DataFrame) -> go.Figure:
    x = _month_axis(df)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["cash_balance"], name="Cash Balance",
        fill="tozeroy",
        line=dict(color=COLORS["green"]),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title="Cash Balance", yaxis_title="$", **LAYOUT_DEFAULTS)
    return fig


def fcf_chart(df: pd.DataFrame) -> go.Figure:
    x = _month_axis(df)
    colors = [COLORS["green"] if v >= 0 else COLORS["red"] for v in df["free_cash_flow"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=df["free_cash_flow"], name="Free Cash Flow",
        marker_color=colors,
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["cumulative_fcf"], name="Cumulative FCF",
        line=dict(color=COLORS["primary"], dash="dot"),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title="Free Cash Flow (Monthly)", yaxis_title="$", **LAYOUT_DEFAULTS)
    return fig


def valuation_waterfall(
    pv_fcf: float,
    pv_terminal: float,
    debt: float,
    cash: float,
    equity: float,
) -> go.Figure:
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["relative", "relative", "relative", "relative", "total"],
        x=["PV of FCF", "PV Terminal Value", "- Debt", "+ Cash", "Equity Value"],
        y=[pv_fcf, pv_terminal, -debt, max(cash, 0), equity],
        connector=dict(line=dict(color="rgb(63, 63, 63)")),
        increasing=dict(marker=dict(color=COLORS["green"])),
        decreasing=dict(marker=dict(color=COLORS["red"])),
        totals=dict(marker=dict(color=COLORS["primary"])),
    ))
    fig.update_layout(
        title="DCF Equity Value Waterfall",
        yaxis_title="$",
        **LAYOUT_DEFAULTS,
    )
    return fig


def scenario_comparison_chart(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    column: str,
    title: str,
    label_a: str = "Scenario A",
    label_b: str = "Scenario B",
    y_title: str = "$",
) -> go.Figure:
    months = min(len(df_a), len(df_b))
    x = [f"M{m}" for m in range(1, months + 1)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df_a[column].iloc[:months], name=label_a,
        line=dict(color=COLORS["primary"], width=2),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df_b[column].iloc[:months], name=label_b,
        line=dict(color=COLORS["amber"], width=2, dash="dash"),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title=title, yaxis_title=y_title, **LAYOUT_DEFAULTS)
    return fig


def sensitivity_heatmap(
    row_values: list[float],
    col_values: list[float],
    z_matrix: list[list[float]],
    row_label: str,
    col_label: str,
    title: str = "Sensitivity Analysis — Equity Value (DCF)",
) -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=z_matrix,
        x=[f"{v:.1f}" for v in col_values],
        y=[f"{v:.1f}" for v in row_values],
        colorscale="RdYlGn",
        text=[[f"${v:,.0f}" for v in row] for row in z_matrix],
        texttemplate="%{text}",
        hovertemplate=f"{row_label}: %{{y}}<br>{col_label}: %{{x}}<br>Equity: %{{text}}<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title=col_label,
        yaxis_title=row_label,
        **{**LAYOUT_DEFAULTS, "height": 420},
    )
    return fig
