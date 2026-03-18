from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.inputs import ModelInputs
from engine.simulation import SimulationResult


@dataclass
class ValuationResult:
    # DCF
    pv_fcf: float
    terminal_value: float
    pv_terminal_value: float
    enterprise_value_dcf: float
    equity_value_dcf: float
    share_price_dcf: float

    # EBITDA multiple
    trailing_ebitda: float
    enterprise_value_ebitda: float
    equity_value_ebitda: float
    share_price_ebitda: float

    # Bridging
    net_debt: float
    cash_at_valuation: float


def compute_valuation(inp: ModelInputs, sim: SimulationResult) -> ValuationResult:
    T = len(sim.days)
    r_disc = inp.discount_rate / 100.0  # annual
    r_growth = inp.perpetual_growth_rate / 100.0
    daily_discount = (1 + r_disc) ** (1 / 365.0)

    # ── DCF ──────────────────────────────────────────────────────────
    proj_days = min(inp.projection_period_dcf, T)

    # Discount each day's FCF back to day 0
    discount_factors = daily_discount ** (-sim.days[:proj_days])
    pv_fcf = float(np.sum(sim.free_cash_flow[:proj_days] * discount_factors))

    # Terminal value using Gordon Growth Model
    # Use the last year's average daily FCF as the terminal FCF
    terminal_window = min(365, proj_days)
    terminal_start = proj_days - terminal_window
    avg_daily_fcf = float(np.mean(sim.free_cash_flow[terminal_start:proj_days]))
    annual_terminal_fcf = avg_daily_fcf * 365.0

    if r_disc > r_growth:
        terminal_value = annual_terminal_fcf * (1 + r_growth) / (r_disc - r_growth)
    else:
        terminal_value = 0.0

    # Discount terminal value back to day 0
    pv_terminal = terminal_value / ((1 + r_disc) ** (proj_days / 365.0))

    enterprise_value_dcf = pv_fcf + pv_terminal

    # Cash and debt at the valuation point
    val_day = min(proj_days - 1, T - 1)
    cash_at_val = float(sim.cash_balance[val_day])
    net_debt = inp.debt - cash_at_val

    equity_value_dcf = enterprise_value_dcf - inp.debt + max(cash_at_val, 0)
    share_price_dcf = equity_value_dcf / max(inp.number_of_shares, 1)

    # ── EBITDA Multiple ──────────────────────────────────────────────
    ebitda_proj = min(inp.projection_period_ebitda, T)

    # Trailing 12-month EBITDA at the projection point
    trail_start = max(ebitda_proj - 365, 0)
    trailing_ebitda = float(np.sum(sim.ebitda[trail_start:ebitda_proj]))

    enterprise_value_ebitda = trailing_ebitda * inp.enterprise_multiple_ebitda

    cash_at_ebitda = float(sim.cash_balance[min(ebitda_proj - 1, T - 1)])
    equity_value_ebitda = enterprise_value_ebitda - inp.debt + max(cash_at_ebitda, 0)
    share_price_ebitda = equity_value_ebitda / max(inp.number_of_shares, 1)

    return ValuationResult(
        pv_fcf=pv_fcf,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal,
        enterprise_value_dcf=enterprise_value_dcf,
        equity_value_dcf=equity_value_dcf,
        share_price_dcf=share_price_dcf,
        trailing_ebitda=trailing_ebitda,
        enterprise_value_ebitda=enterprise_value_ebitda,
        equity_value_ebitda=equity_value_ebitda,
        share_price_ebitda=share_price_ebitda,
        net_debt=net_debt,
        cash_at_valuation=cash_at_val,
    )


def sensitivity_table(
    inp: ModelInputs,
    sim_func,
    param_name: str,
    values: list[float],
    output: str = "equity_value_dcf",
) -> list[tuple[float, float]]:
    """Run the model across a range of values for one parameter and return results."""
    results = []
    for v in values:
        inp_copy = ModelInputs(**{**inp.__dict__, param_name: v})
        sim = sim_func(inp_copy)
        val = compute_valuation(inp_copy, sim)
        results.append((v, getattr(val, output)))
    return results
