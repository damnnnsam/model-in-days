"""
Deal configuration persistence.

A deal connects two models (before + after) with a compensation structure
and engagement terms. This is the "finished product" presented on sales calls.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime

from store.backend import read_json, write_json, list_dir, delete_file
from store.serialization import (
    comp_structure_to_dict, dict_to_comp_structure,
)
from model_2_operator.compensation import CompensationStructure


@dataclass
class DealFile:
    name: str
    before_model: str                      # slug of the "before" model
    after_model: str                       # slug of the "after" model
    compensation: dict | None = None       # serialized CompensationStructure
    engagement: dict | None = None         # engagement timing config
    notes: str = ""
    created: str = ""
    modified: str = ""


def _deal_path(client_slug: str, deal_slug: str) -> str:
    return f"{client_slug}/deals/{deal_slug}.json"


def list_deals(client_slug: str) -> list[tuple[str, DealFile]]:
    """List all deals for a client. Returns list of (slug, DealFile)."""
    deals = []
    for name in list_dir(f"{client_slug}/deals"):
        if not name.endswith(".json") or name.startswith("."):
            continue
        slug = name[:-5]
        df = load_deal(client_slug, slug)
        if df is not None:
            deals.append((slug, df))
    return deals


def load_deal(client_slug: str, deal_slug: str) -> DealFile | None:
    """Load a deal configuration."""
    data = read_json(_deal_path(client_slug, deal_slug))
    if data is None:
        return None
    return DealFile(
        name=data.get("name", deal_slug),
        before_model=data.get("before_model", ""),
        after_model=data.get("after_model", ""),
        compensation=data.get("compensation"),
        engagement=data.get("engagement"),
        notes=data.get("notes", ""),
        created=data.get("created", ""),
        modified=data.get("modified", ""),
    )


def save_deal(client_slug: str, deal_slug: str, deal: DealFile) -> None:
    """Write a deal configuration."""
    deal.modified = datetime.now().isoformat(timespec="seconds")
    if not deal.created:
        deal.created = deal.modified
    write_json(
        _deal_path(client_slug, deal_slug),
        asdict(deal),
        message=f"Save deal: {deal.name} ({client_slug}/{deal_slug})",
    )


def delete_deal(client_slug: str, deal_slug: str) -> None:
    """Delete a deal configuration."""
    delete_file(_deal_path(client_slug, deal_slug),
                message=f"Delete deal: {client_slug}/{deal_slug}")


def get_compensation_structure(deal: DealFile) -> CompensationStructure:
    """Extract the CompensationStructure from a deal's saved compensation dict."""
    if deal.compensation:
        return dict_to_comp_structure(deal.compensation)
    return CompensationStructure()


def get_engagement_config(deal: DealFile) -> dict:
    """Extract engagement configuration with defaults."""
    defaults = {
        "duration_days": 365,
        "ramp_days": 60,
        "ramp_curve": "linear",
        "post_engagement": "metrics_persist",
        "decay_rate_days": 180,
    }
    if deal.engagement:
        defaults.update(deal.engagement)
    return defaults
