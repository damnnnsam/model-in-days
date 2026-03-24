from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from engine.simulation import SimulationResult
from engine.inputs import ModelInputs


@dataclass
class Bonus:
    trigger_type: str  # "day" | "customers" | "revenue" | "profitability"
    trigger_value: float
    amount: float


@dataclass
class DealTerms:
    # Revenue share
    revenue_share_pct: float = 10.0
    revenue_share_basis: str = "delta"  # delta | new_revenue | total_revenue | gross_profit
    revenue_share_cap: float = 0.0  # total cap on rev share earned; 0 = no cap

    # Retainer
    monthly_retainer: float = 0.0

    # Pay per close
    pay_per_close: float = 0.0

    # Performance bonuses
    bonuses: List[Bonus] = field(default_factory=list)

    # Engagement timing
    engagement_start: int = 0
    ramp_days: int = 60
    ramp_curve: str = "linear"  # linear | step
    engagement_duration: int = 365  # 0 = full simulation

    # Post-engagement metric retention
    post_engagement_retention: str = "metrics_persist"
    decay_rate_days: int = 180


@dataclass
class DealResult:
    days: np.ndarray
    ramp_factor: np.ndarray

    # Effective (ramped) simulation arrays
    eff_fcf: np.ndarray
    eff_revenue: np.ndarray
    eff_revenue_new: np.ndarray
    eff_new_customers: np.ndarray
    eff_active_customers: np.ndarray
    eff_gross_profit: np.ndarray

    # Client
    client_revenue_before: np.ndarray
    client_fcf_before: np.ndarray
    client_fcf_after: np.ndarray
    client_fcf_after_fees: np.ndarray
    client_cumulative_gain: np.ndarray

    # Operator earnings breakdown
    operator_retainer: np.ndarray
    operator_rev_share: np.ndarray
    operator_pay_per_close: np.ndarray
    operator_bonus: np.ndarray
    operator_total_earnings: np.ndarray
    operator_cumulative_earnings: np.ndarray

    # ROI
    cumulative_value_created: np.ndarray
    cumulative_operator_cost: np.ndarray
    roi_curve: np.ndarray

    # Totals (over engagement period)
    total_value_created: float
    client_net_gain: float
    operator_total_earned: float
    client_roi: float
    lifetime_roi: float
    break_even_day: int  # -1 if never

    # Equity
    client_equity_before: float
    client_equity_after: float
    equity_delta: float

    # Operator summary
    effective_rate_per_customer: float
    monthly_earnings_avg: float


def _build_ramp_factor(T: int, deal: DealTerms) -> np.ndarray:
    ramp = np.zeros(T)
    eng_end = T
    if deal.engagement_duration > 0:
        eng_end = min(deal.engagement_start + deal.engagement_duration, T)

    for d in range(T):
        if d < deal.engagement_start:
            ramp[d] = 0.0
        elif d < deal.engagement_start + deal.ramp_days:
            if deal.ramp_curve == "step":
                ramp[d] = 0.0
            else:
                elapsed = d - deal.engagement_start
                ramp[d] = elapsed / max(deal.ramp_days, 1)
        elif d < eng_end:
            ramp[d] = 1.0
        else:
            if deal.post_engagement_retention == "metrics_persist":
                ramp[d] = 1.0
            elif deal.post_engagement_retention == "metrics_decay":
                elapsed = d - eng_end
                ramp[d] = max(0.0, 1.0 - elapsed / max(deal.decay_rate_days, 1))
            else:  # metrics_partial
                ramp[d] = 0.5

    return ramp


def compute_deal(
    inp_before: ModelInputs,
    inp_after: ModelInputs,
    deal: DealTerms,
    sim_before: SimulationResult,
    sim_after: SimulationResult,
    val_before,
    val_after,
) -> DealResult:
    T = len(sim_before.days)
    days = np.arange(T)

    eng_end = T
    if deal.engagement_duration > 0:
        eng_end = min(deal.engagement_start + deal.engagement_duration, T)

    ramp = _build_ramp_factor(T, deal)

    def _blend(before_arr, after_arr):
        return before_arr + ramp * (after_arr - before_arr)

    eff_fcf = _blend(sim_before.free_cash_flow, sim_after.free_cash_flow)
    eff_rev = _blend(sim_before.cash_collected_total, sim_after.cash_collected_total)
    eff_rev_new = _blend(sim_before.cash_collected_new, sim_after.cash_collected_new)
    eff_gp = _blend(sim_before.gross_profit, sim_after.gross_profit)
    eff_new_custs = _blend(sim_before.new_customers_total, sim_after.new_customers_total)
    eff_active = _blend(sim_before.active_customers, sim_after.active_customers)

    # --- Precompute metrics for bonus triggers ---

    # Cumulative new customers since engagement start
    cum_new_from_eng = np.zeros(T)
    running = 0.0
    for d in range(T):
        if d >= deal.engagement_start:
            running += eff_new_custs[d]
        cum_new_from_eng[d] = running

    # Trailing 30-day revenue
    cum_rev = np.cumsum(eff_rev)
    lagged = np.zeros(T)
    if T > 30:
        lagged[30:] = cum_rev[:-30]
    trailing_30d_rev = cum_rev - lagged

    cum_eff_fcf = np.cumsum(eff_fcf)

    # --- Operator earnings computation ---

    op_retainer = np.zeros(T)
    op_rev_share = np.zeros(T)
    op_ppc = np.zeros(T)
    op_bonus = np.zeros(T)

    rev_share_remaining = deal.revenue_share_cap if deal.revenue_share_cap > 0 else float("inf")
    bonus_triggered = [False] * len(deal.bonuses)

    for d in range(T):
        if d < deal.engagement_start or d >= eng_end:
            continue

        # Retainer
        op_retainer[d] = deal.monthly_retainer / 30.0

        # Revenue share
        basis = deal.revenue_share_basis
        if basis == "new_revenue":
            shareable = eff_rev_new[d]
        elif basis == "total_revenue":
            shareable = eff_rev[d]
        elif basis == "gross_profit":
            shareable = max(eff_gp[d] - sim_before.gross_profit[d], 0.0)
        else:  # "delta"
            shareable = max(eff_rev[d] - sim_before.cash_collected_total[d], 0.0)

        share_amt = shareable * (deal.revenue_share_pct / 100.0)

        if deal.revenue_share_cap > 0:
            share_amt = min(share_amt, max(rev_share_remaining, 0.0))
            rev_share_remaining -= share_amt

        op_rev_share[d] = share_amt

        # Pay per close
        op_ppc[d] = eff_new_custs[d] * deal.pay_per_close

        # Performance bonuses
        for i, b in enumerate(deal.bonuses):
            if bonus_triggered[i]:
                continue
            hit = False
            if b.trigger_type == "day":
                hit = (d - deal.engagement_start) >= int(b.trigger_value)
            elif b.trigger_type == "customers":
                hit = cum_new_from_eng[d] >= b.trigger_value
            elif b.trigger_type == "revenue":
                hit = trailing_30d_rev[d] >= b.trigger_value
            elif b.trigger_type == "profitability":
                hit = cum_eff_fcf[d] > 0 and d > deal.engagement_start
            if hit:
                op_bonus[d] += b.amount
                bonus_triggered[i] = True

    op_total = op_retainer + op_rev_share + op_ppc + op_bonus
    op_cumulative = np.cumsum(op_total)

    # --- Client-side arrays ---

    client_fcf_after_fees = eff_fcf - op_total
    daily_gain = client_fcf_after_fees - sim_before.free_cash_flow
    client_cumulative_gain = np.cumsum(daily_gain)

    # --- ROI curve ---

    daily_value = eff_fcf - sim_before.free_cash_flow
    cum_value = np.cumsum(daily_value)
    cum_op_cost = np.cumsum(op_total)
    cum_client_net = cum_value - cum_op_cost

    with np.errstate(divide="ignore", invalid="ignore"):
        roi = np.where(cum_op_cost > 0, cum_client_net / cum_op_cost, 0.0)

    # Break-even: first day (after engagement start) where cumulative client
    # net gain crosses from negative to positive.  If the net never dips
    # negative the client is immediately ahead, so report day 0.
    be_day = -1
    went_negative = False
    for d in range(deal.engagement_start, T):
        if cum_client_net[d] < 0:
            went_negative = True
        elif went_negative and cum_client_net[d] >= 0:
            be_day = d
            break
    if not went_negative and T > deal.engagement_start:
        be_day = deal.engagement_start

    # --- Summary totals ---

    total_val = float(cum_value[eng_end - 1]) if eng_end > 0 else 0.0
    op_earned_eng = float(np.sum(op_total[:eng_end]))
    cl_net = total_val - op_earned_eng
    cl_roi = cl_net / max(op_earned_eng, 1.0)
    lt_roi = float(roi[-1])

    total_new = float(np.sum(eff_new_custs[:eng_end]))
    eff_rate = op_earned_eng / max(total_new, 1.0)
    eng_days = max(eng_end - deal.engagement_start, 1)
    monthly_avg = op_earned_eng / max(eng_days / 30.0, 1.0)

    return DealResult(
        days=days,
        ramp_factor=ramp,
        eff_fcf=eff_fcf,
        eff_revenue=eff_rev,
        eff_revenue_new=eff_rev_new,
        eff_new_customers=eff_new_custs,
        eff_active_customers=eff_active,
        eff_gross_profit=eff_gp,
        client_revenue_before=sim_before.cash_collected_total,
        client_fcf_before=sim_before.free_cash_flow,
        client_fcf_after=eff_fcf,
        client_fcf_after_fees=client_fcf_after_fees,
        client_cumulative_gain=client_cumulative_gain,
        operator_retainer=op_retainer,
        operator_rev_share=op_rev_share,
        operator_pay_per_close=op_ppc,
        operator_bonus=op_bonus,
        operator_total_earnings=op_total,
        operator_cumulative_earnings=op_cumulative,
        cumulative_value_created=cum_value,
        cumulative_operator_cost=cum_op_cost,
        roi_curve=roi,
        total_value_created=total_val,
        client_net_gain=cl_net,
        operator_total_earned=op_earned_eng,
        client_roi=cl_roi,
        lifetime_roi=lt_roi,
        break_even_day=be_day,
        client_equity_before=val_before.equity_value_dcf,
        client_equity_after=val_after.equity_value_dcf,
        equity_delta=val_after.equity_value_dcf - val_before.equity_value_dcf,
        effective_rate_per_customer=eff_rate,
        monthly_earnings_avg=monthly_avg,
    )
