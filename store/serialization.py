"""
JSON serialization for all dataclasses used in persistence.

Handles ModelInputs, CompensationStructure (with nested DecayStep, RetainerStep,
DealTier, ClientType), and DealTerms (with nested Bonus).
"""
from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from engine.inputs import ModelInputs
from model_2_operator.compensation import (
    CompensationStructure, DecayStep, RetainerStep, DealTier, ClientType,
)
from model_2_operator.deal import DealTerms, Bonus


# ── ModelInputs ────────────────────────────────────────────────────────

def model_inputs_to_dict(inp: ModelInputs) -> dict:
    """Serialize ModelInputs to a JSON-safe dict."""
    return asdict(inp)


def dict_to_model_inputs(d: dict) -> ModelInputs:
    """Deserialize a dict to ModelInputs, coercing types to match defaults."""
    valid_fields = {f.name: f for f in fields(ModelInputs)}
    cleaned = {}
    for k, v in d.items():
        if k not in valid_fields:
            continue
        ftype = valid_fields[k].type
        if ftype == "int" or ftype is int:
            cleaned[k] = int(v)
        elif ftype == "float" or ftype is float:
            cleaned[k] = float(v)
        elif ftype == "bool" or ftype is bool:
            cleaned[k] = bool(v)
        else:
            cleaned[k] = v
    return ModelInputs(**cleaned)


# ── CompensationStructure ──────────────────────────────────────────────

def comp_structure_to_dict(comp: CompensationStructure) -> dict:
    """Serialize CompensationStructure to a JSON-safe dict."""
    d = {}
    for f in fields(CompensationStructure):
        val = getattr(comp, f.name)
        if f.name == "retainer_escalation_schedule":
            d[f.name] = [{"month": s.month, "amount": s.amount} for s in val]
        elif f.name == "rev_share_decay_schedule":
            d[f.name] = [{"from_month": s.from_month, "to_month": s.to_month, "rate": s.rate} for s in val]
        elif f.name == "deal_tiers":
            d[f.name] = [{"min_value": t.min_value, "max_value": t.max_value,
                          "rev_share": t.rev_share, "per_deal_bonus": t.per_deal_bonus} for t in val]
        elif f.name == "client_types":
            d[f.name] = [{"name": t.name, "rev_share_modifier": t.rev_share_modifier,
                          "per_deal_modifier": t.per_deal_modifier} for t in val]
        else:
            d[f.name] = val
    return d


def dict_to_comp_structure(d: dict) -> CompensationStructure:
    """Deserialize a dict to CompensationStructure."""
    kwargs = {}
    for f in fields(CompensationStructure):
        if f.name not in d:
            continue
        val = d[f.name]
        if f.name == "retainer_escalation_schedule":
            kwargs[f.name] = [RetainerStep(s["month"], s["amount"]) for s in (val or [])]
        elif f.name == "rev_share_decay_schedule":
            kwargs[f.name] = [DecayStep(s["from_month"], s["to_month"], s["rate"]) for s in (val or [])]
        elif f.name == "deal_tiers":
            kwargs[f.name] = [DealTier(t["min_value"], t["max_value"], t["rev_share"], t["per_deal_bonus"]) for t in (val or [])]
        elif f.name == "client_types":
            kwargs[f.name] = [ClientType(t["name"], t.get("rev_share_modifier", 1.0), t.get("per_deal_modifier", 1.0)) for t in (val or [])]
        else:
            kwargs[f.name] = val
    return CompensationStructure(**kwargs)


# ── DealTerms ──────────────────────────────────────────────────────────

def deal_terms_to_dict(deal: DealTerms) -> dict:
    """Serialize DealTerms to a JSON-safe dict."""
    d = {}
    for f in fields(DealTerms):
        val = getattr(deal, f.name)
        if f.name == "bonuses":
            d[f.name] = [{"trigger_type": b.trigger_type, "trigger_value": b.trigger_value,
                          "amount": b.amount} for b in val]
        else:
            d[f.name] = val
    return d


def dict_to_deal_terms(d: dict) -> DealTerms:
    """Deserialize a dict to DealTerms."""
    kwargs = {}
    for f in fields(DealTerms):
        if f.name not in d:
            continue
        val = d[f.name]
        if f.name == "bonuses":
            kwargs[f.name] = [Bonus(b["trigger_type"], b["trigger_value"], b["amount"]) for b in (val or [])]
        else:
            kwargs[f.name] = val
    return DealTerms(**kwargs)


# ── Override utilities ─────────────────────────────────────────────────

def compute_overrides(base: ModelInputs, modified: ModelInputs) -> dict:
    """Diff two ModelInputs and return only changed fields."""
    overrides = {}
    for f in fields(ModelInputs):
        base_val = getattr(base, f.name)
        mod_val = getattr(modified, f.name)
        if base_val != mod_val:
            overrides[f.name] = mod_val
    return overrides


def apply_overrides(base: ModelInputs, overrides: dict) -> ModelInputs:
    """Apply override dict on top of a base ModelInputs."""
    d = asdict(base)
    valid_fields = {f.name for f in fields(ModelInputs)}
    for k, v in overrides.items():
        if k in valid_fields:
            d[k] = v
    return dict_to_model_inputs(d)
