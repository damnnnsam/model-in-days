from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd
import numpy as np

from engine.simulation import SimulationResult
from engine.inputs import ModelInputs

COLORS = {
    "primary": "#a0a0a0",
    "green": "#4ade80",
    "red": "#f87171",
    "amber": "#fbbf24",
    "sky": "#60a5fa",
    "purple": "#a78bfa",
    "pink": "#f472b6",
    "gray": "#525252",
}

DAILY_LAYOUT = dict(
    template="plotly_dark",
    height=360,
    margin=dict(l=50, r=16, t=32, b=36),
    font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                font=dict(size=10)),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(10,10,10,1)",
    xaxis=dict(
        rangeslider=dict(visible=True, thickness=0.05),
        type="linear",
        gridcolor="#1a1a1a",
    ),
    yaxis=dict(gridcolor="#1a1a1a"),
)


def _apply_range(fig: go.Figure, total_days: int) -> go.Figure:
    """Show the last 365 days by default, with range slider for full history."""
    start = max(0, total_days - 365)
    fig.update_xaxes(range=[start, total_days])
    return fig


def add_cursor(fig: go.Figure, day: int | None) -> go.Figure:
    if day is not None:
        fig.add_shape(
            type="line", x0=day, x1=day, y0=0, y1=1,
            yref="paper", line=dict(dash="dash", color="#9CA3AF", width=1),
        )
    return fig


def hero_chart(df: pd.DataFrame, cursor_day: int | None = None) -> go.Figure:
    from plotly.subplots import make_subplots

    x = df["day"]
    T = len(df)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Free Cash Flow (Daily)", "Cash Balance", "Active Customers", "Revenue vs Costs"),
        vertical_spacing=0.22,
        horizontal_spacing=0.12,
    )

    # FCF line with fill
    fig.add_trace(go.Scatter(
        x=x, y=df["free_cash_flow"], fill="tozeroy",
        line=dict(color=COLORS["green"], width=1),
        showlegend=False, hovertemplate="FCF: $%{y:,.0f}<extra></extra>",
    ), row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="#333", line_width=1, row=1, col=1)

    # Cash balance
    fig.add_trace(go.Scatter(
        x=x, y=df["cash_balance"], fill="tozeroy",
        line=dict(color=COLORS["sky"], width=1),
        fillcolor="rgba(96,165,250,0.15)",
        showlegend=False, hovertemplate="Cash: $%{y:,.0f}<extra></extra>",
    ), row=1, col=2)
    fig.add_hline(y=0, line_dash="dash", line_color="#333", line_width=1, row=1, col=2)

    # Active customers
    fig.add_trace(go.Scatter(
        x=x, y=df["active_customers"], fill="tozeroy",
        line=dict(color=COLORS["sky"], width=1),
        showlegend=False, hovertemplate="Active: %{y:,.0f}<extra></extra>",
    ), row=2, col=1)

    # Revenue vs costs
    fig.add_trace(go.Scatter(
        x=x, y=df["cash_collected_total"], name="Cash Collected",
        line=dict(color=COLORS["green"], width=1),
        hovertemplate="Revenue: $%{y:,.0f}<extra></extra>",
    ), row=2, col=2)
    fig.add_trace(go.Scatter(
        x=x, y=df["cost_total"], name="Total Costs",
        line=dict(color=COLORS["red"], width=1),
        hovertemplate="Costs: $%{y:,.0f}<extra></extra>",
    ), row=2, col=2)

    # Cursor on all subplots
    if cursor_day is not None:
        xref_map = {(1, 1): "x", (1, 2): "x2", (2, 1): "x3", (2, 2): "x4"}
        for (row, col), xref in xref_map.items():
            fig.add_shape(
                type="line", x0=cursor_day, x1=cursor_day, y0=0, y1=1,
                xref=xref, yref="paper",
                line=dict(dash="dash", color="#9CA3AF", width=1),
            )

    fig.update_layout(
        template="plotly_dark",
        height=560,
        margin=dict(l=50, r=16, t=28, b=28),
        font=dict(family="JetBrains Mono, Consolas, monospace", size=10, color="#b0b0b0"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.08, xanchor="center", x=0.75,
                    font=dict(size=10)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,10,10,1)",
        showlegend=True,
    )
    fig.update_xaxes(title_text="Day", gridcolor="#1a1a1a")
    fig.update_yaxes(gridcolor="#1a1a1a")

    return fig


def customers_chart(df: pd.DataFrame) -> go.Figure:
    x = df["day"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["active_customers"], name="Active Customers",
        fill="tozeroy", line=dict(color=COLORS["primary"], width=1),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["cumulative_customers"], name="Cumulative Customers",
        line=dict(color=COLORS["gray"], dash="dot", width=1),
    ))
    fig.update_layout(title="Customers", yaxis_title="Customers", xaxis_title="Day", **DAILY_LAYOUT)
    return _apply_range(fig, len(df))


def new_customers_by_channel(df: pd.DataFrame) -> go.Figure:
    x = df["day"]
    fig = go.Figure()
    channels = [
        ("new_customers_inbound", "Inbound", COLORS["sky"]),
        ("new_customers_outbound", "Outbound", COLORS["purple"]),
        ("new_customers_organic", "Organic", COLORS["green"]),
        ("new_customers_viral", "Viral", COLORS["pink"]),
    ]
    for col, name, color in channels:
        if df[col].sum() > 0:
            fig.add_trace(go.Scatter(x=x, y=df[col], name=name, line=dict(color=color, width=1)))
    fig.update_layout(
        title="New Customers by Channel (Daily)", yaxis_title="New Customers",
        xaxis_title="Day", **DAILY_LAYOUT,
    )
    return _apply_range(fig, len(df))


def revenue_chart(df: pd.DataFrame) -> go.Figure:
    x = df["day"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["revenue_new"], name="New Revenue",
        line=dict(color=COLORS["primary"], width=1),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["revenue_renewal"], name="Renewal Revenue",
        line=dict(color=COLORS["green"], width=1),
    ))
    fig.update_layout(
        title="Revenue (Daily)", yaxis_title="$",
        xaxis_title="Day", **DAILY_LAYOUT,
    )
    return _apply_range(fig, len(df))


def cash_collected_chart(df: pd.DataFrame) -> go.Figure:
    x = df["day"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["cash_collected_total"], name="Cash Collected",
        fill="tozeroy", line=dict(color=COLORS["green"], width=1),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["cost_total"], name="Total Costs",
        line=dict(color=COLORS["red"], width=1),
    ))
    fig.update_layout(
        title="Cash Collected vs Costs (Daily)", yaxis_title="$",
        xaxis_title="Day", **DAILY_LAYOUT,
    )
    return _apply_range(fig, len(df))


def cost_breakdown_chart(df: pd.DataFrame) -> go.Figure:
    x = df["day"]
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
        fig.add_trace(go.Scatter(
            x=x, y=df[col], name=name, stackgroup="costs",
            line=dict(color=color, width=0),
        ))
    fig.update_layout(
        title="Cost Breakdown (Daily, Stacked)", yaxis_title="$",
        xaxis_title="Day", **DAILY_LAYOUT,
    )
    return _apply_range(fig, len(df))


def pnl_chart(df: pd.DataFrame) -> go.Figure:
    x = df["day"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["gross_profit"], name="Gross Profit",
        line=dict(color=COLORS["green"], width=1),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["ebitda"], name="EBITDA",
        line=dict(color=COLORS["primary"], width=1),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["net_income"], name="Net Income",
        line=dict(color=COLORS["amber"], width=1),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title="P&L (Daily)", yaxis_title="$", xaxis_title="Day", **DAILY_LAYOUT)
    return _apply_range(fig, len(df))


def cash_balance_chart(df: pd.DataFrame) -> go.Figure:
    x = df["day"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["cash_balance"], name="Cash Balance",
        fill="tozeroy", line=dict(color=COLORS["green"], width=1),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title="Cash Balance", yaxis_title="$", xaxis_title="Day", **DAILY_LAYOUT)
    return _apply_range(fig, len(df))


def fcf_chart(df: pd.DataFrame) -> go.Figure:
    x = df["day"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["free_cash_flow"], name="Free Cash Flow",
        fill="tozeroy", line=dict(color=COLORS["green"], width=1),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["cumulative_fcf"], name="Cumulative FCF",
        line=dict(color=COLORS["primary"], dash="dot", width=1),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title="Free Cash Flow (Daily)", yaxis_title="$", xaxis_title="Day", **DAILY_LAYOUT)
    return _apply_range(fig, len(df))


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
    layout = {k: v for k, v in DAILY_LAYOUT.items() if k != "xaxis"}
    fig.update_layout(title="DCF Equity Value Waterfall", yaxis_title="$", **layout)
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
    if "day" in df_a.columns:
        n = min(len(df_a), len(df_b))
        x = df_a["day"].iloc[:n]
    else:
        n = min(len(df_a), len(df_b))
        x = list(range(n))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df_a[column].iloc[:n], name=label_a,
        line=dict(color=COLORS["primary"], width=2),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df_b[column].iloc[:n], name=label_b,
        line=dict(color=COLORS["amber"], width=2, dash="dash"),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title=title, yaxis_title=y_title, xaxis_title="Day", **DAILY_LAYOUT)
    return _apply_range(fig, n)


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
    layout = {k: v for k, v in DAILY_LAYOUT.items() if k != "xaxis"}
    fig.update_layout(
        title=title, xaxis_title=col_label, yaxis_title=row_label,
        **{**layout, "height": 420},
    )
    return fig
