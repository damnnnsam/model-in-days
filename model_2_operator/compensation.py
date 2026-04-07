"""
Compensation Structure Engine for Growth Operator Deals.

Implements the full parameter spec:
  1. Upfront fees (single or split)
  2. Monthly retainer with escalation schedule
  3. Rev share — Mode A (baseline-based, global) and Mode B (per-client, individual streams)
  4. Per-client windows and decay schedules
  5. Per-deal bonuses
  6. Deal size tiers (tiered rev share + bonus rates)
  7. Client type rate modifiers (weighted distribution)

The engine converts daily simulation output into monthly compensation
calculations and produces a full breakdown of operator earnings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np

from engine.simulation import SimulationResult
from engine.inputs import ModelInputs


# ── Data Structures ──────────────────────────────────────────────────


@dataclass
class DecayStep:
    """One segment of a rev share decay schedule."""
    from_month: int          # 1-indexed start
    to_month: int | None     # 1-indexed end; None = open-ended
    rate: float              # decimal, e.g. 0.15 = 15%


@dataclass
class DealTier:
    """Rev share and bonus rates for a given deal size range."""
    min_value: float          # monthly deal value lower bound
    max_value: float | None   # upper bound; None = no limit
    rev_share: float          # decimal rate override for this tier
    per_deal_bonus: float     # $ per deal for this tier


@dataclass
class ClientType:
    """Rate modifier for a client acquisition channel / category."""
    name: str
    rev_share_modifier: float = 1.0   # multiplier on base rev share
    per_deal_modifier: float = 1.0    # multiplier on base per-deal bonus


@dataclass
class RetainerStep:
    """A retainer escalation step — new amount starting at a given month."""
    month: int      # 1-indexed month when step-up takes effect
    amount: float   # new retainer $/month


@dataclass
class CompensationStructure:
    """
    Complete operator compensation configuration.

    All 7 parameter groups from the spec are represented here.
    Use the preset_*() factories for the 5 pre-built configurations.
    """
    name: str = "Custom"

    # ── 1. Upfront Fee ───────────────────────────────────────────────
    upfront_fee_amount: float = 0.0
    upfront_fee_split: bool = False
    upfront_fee_split_pct_signing: float = 100.0   # % paid at signing
    upfront_fee_split_day_2: int = 30              # day for 2nd payment

    # ── 2. Monthly Retainer ──────────────────────────────────────────
    retainer_amount: float = 7500.0
    retainer_start_month: int = 1                  # 1-indexed
    retainer_escalation_enabled: bool = False
    retainer_escalation_schedule: List[RetainerStep] = field(default_factory=list)
    contract_term_months: int = 12

    # ── 3. Rev Share ─────────────────────────────────────────────────
    rev_share_mode: str = "none"                   # "none" | "baseline" | "per_client"
    rev_share_percentage: float = 12.0             # base % (used when decay disabled)
    rev_share_basis: str = "gross_revenue"         # "gross_revenue" | "gross_profit"

    # Mode A (baseline) parameters
    rev_share_baseline: float = 50_000.0           # monthly $ threshold
    rev_share_baseline_churn_adjust: bool = False
    rev_share_baseline_reset_annual: bool = False

    # Mode B (per-client) parameters
    rev_share_client_window_months: int = 18       # months of rev share per client
    rev_share_client_window_pause_on_churn: bool = False

    # Decay schedule (applies to both modes)
    rev_share_decay_enabled: bool = False
    rev_share_decay_schedule: List[DecayStep] = field(default_factory=list)

    # Caps
    rev_share_cap_monthly: float = 0.0             # 0 = no cap
    rev_share_cap_total: float = 0.0               # 0 = no cap

    # ── 7. Per-Deal Bonus ────────────────────────────────────────────
    per_deal_amount: float = 0.0
    per_deal_trigger: str = "first_payment"        # "contract_signed" | "first_payment"

    # ── 8. Deal Size Tiers ───────────────────────────────────────────
    deal_tiers_enabled: bool = False
    deal_tiers: List[DealTier] = field(default_factory=list)
    deal_tier_lock: str = "initial"                # "initial" | "current"

    # ── 9. Client Type Modifiers ─────────────────────────────────────
    client_types_enabled: bool = False
    client_types: List[ClientType] = field(default_factory=list)
    client_type_distribution: Dict[str, float] = field(default_factory=dict)


@dataclass
class CompensationResult:
    """Full month-by-month compensation computation output."""
    n_months: int
    structure_name: str

    # Monthly arrays (length = n_months)
    upfront: np.ndarray
    retainer: np.ndarray
    rev_share: np.ndarray
    per_deal_bonus: np.ndarray
    total_compensation: np.ndarray
    cumulative_compensation: np.ndarray

    # Per-cohort detail (Mode B only) — shape (n_months, n_months)
    # rev_share_by_cohort[m][c] = rev share in month m from cohort c
    rev_share_by_cohort: np.ndarray

    # Client-side monthly arrays
    client_monthly_revenue: np.ndarray
    client_monthly_gross_profit: np.ndarray
    client_monthly_fcf: np.ndarray
    client_profit_after_comp: np.ndarray
    client_cumulative_profit_after_comp: np.ndarray

    # Context arrays
    monthly_new_customers: np.ndarray
    monthly_active_customers: np.ndarray
    cohort_sizes: np.ndarray
    cohort_monthly_revenue: np.ndarray   # shape (n_months, n_months)

    # Summary totals
    total_earned: float
    total_upfront: float
    total_retainer: float
    total_rev_share: float
    total_per_deal: float
    avg_monthly_earnings: float
    effective_rate_per_customer: float
    effective_rev_share_rate: float       # actual % of total revenue taken


# ── Helpers ──────────────────────────────────────────────────────────


def _get_decay_rate(schedule: List[DecayStep], month_1idx: int) -> float:
    """Look up the rev share rate for a 1-indexed month in a decay schedule."""
    for step in schedule:
        if step.to_month is None:
            if month_1idx >= step.from_month:
                return step.rate
        elif step.from_month <= month_1idx <= step.to_month:
            return step.rate
    return 0.0


def _get_retainer_amount(comp: CompensationStructure, month_1idx: int) -> float:
    """Retainer for a given month (1-indexed), with escalation."""
    if month_1idx < comp.retainer_start_month:
        return 0.0
    amount = comp.retainer_amount
    if comp.retainer_escalation_enabled:
        for step in sorted(comp.retainer_escalation_schedule, key=lambda s: s.month):
            if month_1idx >= step.month:
                amount = step.amount
    return amount


def _get_deal_tier(comp: CompensationStructure, monthly_deal_value: float) -> DealTier | None:
    """Find the matching deal tier for a monthly deal value."""
    if not comp.deal_tiers_enabled or not comp.deal_tiers:
        return None
    for tier in comp.deal_tiers:
        upper = tier.max_value if tier.max_value is not None else float("inf")
        if tier.min_value <= monthly_deal_value <= upper:
            return tier
    return None


def _weighted_type_modifier(comp: CompensationStructure, kind: str) -> float:
    """
    Weighted-average modifier across the client type distribution.
    kind = "rev_share" or "per_deal".
    Returns 1.0 if client types are disabled.
    """
    if not comp.client_types_enabled or not comp.client_types:
        return 1.0
    if not comp.client_type_distribution:
        return 1.0
    total_w = 0.0
    weighted = 0.0
    for ct in comp.client_types:
        w = comp.client_type_distribution.get(ct.name, 0.0)
        mod = ct.rev_share_modifier if kind == "rev_share" else ct.per_deal_modifier
        weighted += w * mod
        total_w += w
    return weighted / total_w if total_w > 0 else 1.0


# ── Main Engine ──────────────────────────────────────────────────────


def compute_compensation(
    comp: CompensationStructure,
    sim: SimulationResult,
    inp: ModelInputs,
) -> CompensationResult:
    """
    Compute month-by-month operator compensation from a daily simulation.

    Converts the daily simulation into 30-day monthly periods and applies
    the full compensation structure: upfront, retainer (with escalation),
    rev share (baseline or per-client with decay), per-deal bonuses,
    deal size tiers, and client type modifiers.
    """
    T = len(sim.days)
    n_months = T // 30

    # ── Extract monthly aggregates from simulation ──────────────────
    monthly_revenue = np.zeros(n_months)
    monthly_gp = np.zeros(n_months)
    monthly_fcf = np.zeros(n_months)
    monthly_new_custs = np.zeros(n_months)
    monthly_active = np.zeros(n_months)

    for m in range(n_months):
        s, e = m * 30, min((m + 1) * 30, T)
        monthly_revenue[m] = float(np.sum(sim.cash_collected_total[s:e]))
        monthly_gp[m] = float(np.sum(sim.gross_profit[s:e]))
        monthly_fcf[m] = float(np.sum(sim.free_cash_flow[s:e]))
        monthly_new_custs[m] = float(np.sum(sim.new_customers_total[s:e]))
        monthly_active[m] = float(sim.active_customers[min(e - 1, T - 1)])

    # ── Per-customer economics (for Mode B per-client rev share) ────
    contract_months = max(inp.contract_length / 30.0, 1.0)
    RR = inp.realization_rate / 100.0
    monthly_rev_per_cust = (inp.price_of_offer * RR) / contract_months
    monthly_gp_per_cust = monthly_rev_per_cust - (
        inp.price_of_offer * (inp.cost_to_fulfill / 100.0) / contract_months
    )

    # ── Deal-tier lookup (based on effective monthly deal value) ─────
    tier = _get_deal_tier(comp, monthly_rev_per_cust)

    # Base rates (potentially overridden by tier)
    base_rs_rate = comp.rev_share_percentage / 100.0
    base_per_deal = comp.per_deal_amount

    if tier is not None:
        if tier.rev_share > 0 or comp.rev_share_mode != "none":
            base_rs_rate = tier.rev_share
        base_per_deal = tier.per_deal_bonus

    # Client-type weighted modifiers
    type_mod_rs = _weighted_type_modifier(comp, "rev_share")
    type_mod_pd = _weighted_type_modifier(comp, "per_deal")

    # ── Allocate result arrays ──────────────────────────────────────
    upfront_arr = np.zeros(n_months)
    retainer_arr = np.zeros(n_months)
    rev_share_arr = np.zeros(n_months)
    per_deal_arr = np.zeros(n_months)
    rs_by_cohort = np.zeros((n_months, n_months))
    cohort_rev = np.zeros((n_months, n_months))

    # ── 1. Upfront fee ──────────────────────────────────────────────
    if comp.upfront_fee_amount > 0:
        if comp.upfront_fee_split:
            pct1 = comp.upfront_fee_split_pct_signing / 100.0
            upfront_arr[0] = comp.upfront_fee_amount * pct1
            m2 = max(0, comp.upfront_fee_split_day_2 // 30)
            if m2 < n_months:
                upfront_arr[m2] += comp.upfront_fee_amount * (1.0 - pct1)
        else:
            upfront_arr[0] = comp.upfront_fee_amount

    # ── Track lifetime rev-share cap ────────────────────────────────
    rs_remaining = comp.rev_share_cap_total if comp.rev_share_cap_total > 0 else float("inf")

    # ── Contract term cap (retainer + per-deal stop at contract end) ──
    contract_end_month = comp.contract_term_months if comp.contract_term_months > 0 else n_months

    # ── Monthly loop ────────────────────────────────────────────────
    for m in range(n_months):
        mo = m + 1  # 1-indexed month

        # 2. Retainer (with escalation) — capped at contract term
        if mo <= contract_end_month:
            retainer_arr[m] = _get_retainer_amount(comp, mo)

        # 3. Rev share (uses its own duration controls, NOT contract term)
        if comp.rev_share_mode == "baseline":
            # ── Mode A: single global stream ────────────────────────
            if comp.rev_share_basis == "gross_profit":
                shareable = max(0.0, monthly_gp[m] - comp.rev_share_baseline)
            else:
                shareable = max(0.0, monthly_revenue[m] - comp.rev_share_baseline)

            # Rate: from decay schedule or base
            if comp.rev_share_decay_enabled and comp.rev_share_decay_schedule:
                rate = _get_decay_rate(comp.rev_share_decay_schedule, mo)
            else:
                rate = base_rs_rate

            share_amt = shareable * rate * type_mod_rs

            # Monthly cap
            if comp.rev_share_cap_monthly > 0:
                share_amt = min(share_amt, comp.rev_share_cap_monthly)
            # Lifetime cap
            share_amt = min(share_amt, max(rs_remaining, 0.0))
            rs_remaining -= share_amt

            rev_share_arr[m] = share_amt

        elif comp.rev_share_mode == "per_client":
            # ── Mode B: individual per-cohort streams ───────────────
            month_total_rs = 0.0

            for c in range(m + 1):
                # Months since this cohort was acquired (0 = same month)
                months_since = m - c
                months_1idx = months_since + 1  # 1-indexed for schedule lookup

                # Window check
                if months_since >= comp.rev_share_client_window_months:
                    continue

                csize = monthly_new_custs[c]
                if csize <= 0:
                    continue

                # Cohort revenue this month
                if comp.rev_share_basis == "gross_profit":
                    c_rev = csize * monthly_gp_per_cust
                else:
                    c_rev = csize * monthly_rev_per_cust

                cohort_rev[m][c] = c_rev

                # Rate from decay schedule or base
                if comp.rev_share_decay_enabled and comp.rev_share_decay_schedule:
                    rate = _get_decay_rate(comp.rev_share_decay_schedule, months_1idx)
                else:
                    rate = base_rs_rate

                c_share = c_rev * rate * type_mod_rs
                rs_by_cohort[m][c] = c_share
                month_total_rs += c_share

            # Apply caps
            if comp.rev_share_cap_monthly > 0:
                month_total_rs = min(month_total_rs, comp.rev_share_cap_monthly)
            month_total_rs = min(month_total_rs, max(rs_remaining, 0.0))
            rs_remaining -= month_total_rs

            rev_share_arr[m] = month_total_rs

        # 7. Per-deal bonus — capped at contract term
        if mo <= contract_end_month and monthly_new_custs[m] > 0 and base_per_deal > 0:
            per_deal_arr[m] = monthly_new_custs[m] * base_per_deal * type_mod_pd

    # ── Totals and derived arrays ───────────────────────────────────
    total_comp = upfront_arr + retainer_arr + rev_share_arr + per_deal_arr
    cum_comp = np.cumsum(total_comp)

    client_profit_after = monthly_fcf - total_comp
    client_cum_profit = np.cumsum(client_profit_after)

    total_earned = float(np.sum(total_comp))
    total_new = float(np.sum(monthly_new_custs))
    total_rev = float(np.sum(monthly_revenue))
    total_rs = float(np.sum(rev_share_arr))

    return CompensationResult(
        n_months=n_months,
        structure_name=comp.name,
        upfront=upfront_arr,
        retainer=retainer_arr,
        rev_share=rev_share_arr,
        per_deal_bonus=per_deal_arr,
        total_compensation=total_comp,
        cumulative_compensation=cum_comp,
        rev_share_by_cohort=rs_by_cohort,
        client_monthly_revenue=monthly_revenue,
        client_monthly_gross_profit=monthly_gp,
        client_monthly_fcf=monthly_fcf,
        client_profit_after_comp=client_profit_after,
        client_cumulative_profit_after_comp=client_cum_profit,
        monthly_new_customers=monthly_new_custs,
        monthly_active_customers=monthly_active,
        cohort_sizes=monthly_new_custs,
        cohort_monthly_revenue=cohort_rev,
        total_earned=total_earned,
        total_upfront=float(np.sum(upfront_arr)),
        total_retainer=float(np.sum(retainer_arr)),
        total_rev_share=total_rs,
        total_per_deal=float(np.sum(per_deal_arr)),
        avg_monthly_earnings=total_earned / max(int(np.count_nonzero(total_comp)), 1),
        effective_rate_per_customer=total_earned / max(total_new, 1),
        effective_rev_share_rate=(total_rs / max(total_rev, 1)) * 100,
    )


# ── Pre-Built Structures ────────────────────────────────────────────


def preset_alpha() -> CompensationStructure:
    """High Base + Decaying Per-Client Rev Share."""
    return CompensationStructure(
        name="Alpha — High Base + Decaying Rev Share",
        upfront_fee_amount=0.0,
        retainer_amount=10_000.0,
        rev_share_mode="per_client",
        rev_share_basis="gross_revenue",
        rev_share_percentage=15.0,
        rev_share_client_window_months=18,
        rev_share_decay_enabled=True,
        rev_share_decay_schedule=[
            DecayStep(1, 6, 0.15),
            DecayStep(7, 12, 0.10),
            DecayStep(13, 18, 0.05),
            DecayStep(19, None, 0.00),
        ],
    )


def preset_beta() -> CompensationStructure:
    """Upfront + Mid Retainer + Baseline Rev Share."""
    return CompensationStructure(
        name="Beta — Upfront + Mid Retainer + Baseline Rev Share",
        upfront_fee_amount=15_000.0,
        retainer_amount=6_000.0,
        rev_share_mode="baseline",
        rev_share_basis="gross_revenue",
        rev_share_percentage=10.0,
        rev_share_baseline=50_000.0,
        rev_share_decay_enabled=True,
        rev_share_decay_schedule=[
            DecayStep(1, 12, 0.10),
            DecayStep(13, 24, 0.07),
            DecayStep(25, None, 0.00),
        ],
    )


def preset_gamma() -> CompensationStructure:
    """Mid Base + Per-Deal Tiered Bonuses (no rev share)."""
    return CompensationStructure(
        name="Gamma — Mid Base + Per-Deal Tiers",
        upfront_fee_amount=0.0,
        retainer_amount=7_500.0,
        rev_share_mode="none",
        per_deal_amount=1_000.0,
        deal_tiers_enabled=True,
        deal_tiers=[
            DealTier(0, 7_500, 0.0, 1_000.0),
            DealTier(7_501, 15_000, 0.0, 1_500.0),
            DealTier(15_001, 30_000, 0.0, 2_500.0),
            DealTier(30_001, None, 0.0, 4_000.0),
        ],
    )


def preset_delta() -> CompensationStructure:
    """Performance-Weighted: low base + per-deal + per-client rev share + type modifiers."""
    return CompensationStructure(
        name="Delta — Performance-Weighted",
        upfront_fee_amount=0.0,
        retainer_amount=5_000.0,
        rev_share_mode="per_client",
        rev_share_basis="gross_revenue",
        rev_share_percentage=12.0,
        rev_share_client_window_months=12,
        rev_share_decay_enabled=True,
        rev_share_decay_schedule=[
            DecayStep(1, 12, 0.12),
            DecayStep(13, None, 0.00),
        ],
        per_deal_amount=1_500.0,
        client_types_enabled=True,
        client_types=[
            ClientType("outbound", 1.0, 1.0),
            ClientType("inbound", 0.75, 0.75),
            ClientType("referral", 0.5, 0.5),
            ClientType("channel_partner", 0.5, 0.5),
        ],
        client_type_distribution={
            "outbound": 0.60,
            "inbound": 0.20,
            "referral": 0.10,
            "channel_partner": 0.10,
        },
    )


def preset_epsilon() -> CompensationStructure:
    """Diagnostic Entry: minimal commitment, no performance comp."""
    return CompensationStructure(
        name="Epsilon — Diagnostic Entry",
        upfront_fee_amount=3_500.0,
        retainer_amount=3_500.0,
        rev_share_mode="none",
        per_deal_amount=0.0,
    )


ALL_PRESETS = {
    "Alpha": preset_alpha,
    "Beta": preset_beta,
    "Gamma": preset_gamma,
    "Delta": preset_delta,
    "Epsilon": preset_epsilon,
}
