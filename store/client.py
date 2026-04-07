"""
Client folder management.

Each client is a folder under data/clients/ with:
  meta.json     — name, industry, notes, created date
  models/       — model JSON files
  deals/        — deal JSON files
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date

from store.backend import read_json, write_json, list_dir


@dataclass
class ClientMeta:
    name: str
    industry: str = ""
    notes: str = ""
    created: str = ""


def list_clients() -> list[tuple[str, ClientMeta]]:
    """Return list of (slug, ClientMeta) for all clients."""
    clients = []
    for slug in list_dir(""):
        meta = load_client_meta(slug)
        if meta is not None:
            clients.append((slug, meta))
    return clients


def load_client_meta(slug: str) -> ClientMeta | None:
    """Load meta.json for a client. Returns None if not found."""
    data = read_json(f"{slug}/meta.json")
    if data is None:
        return None
    return ClientMeta(
        name=data.get("name", slug),
        industry=data.get("industry", ""),
        notes=data.get("notes", ""),
        created=data.get("created", ""),
    )


def save_client_meta(slug: str, meta: ClientMeta) -> None:
    """Write meta.json for a client."""
    write_json(f"{slug}/meta.json", asdict(meta),
               message=f"Update client metadata: {meta.name}")


def create_client(slug: str, name: str, industry: str = "", notes: str = "") -> ClientMeta:
    """Create a new client with meta.json and empty models/deals folders."""
    meta = ClientMeta(name=name, industry=industry, notes=notes, created=str(date.today()))
    write_json(f"{slug}/meta.json", asdict(meta),
               message=f"Create client: {name}")
    # Create placeholder files so the directories exist in git
    write_json(f"{slug}/models/.gitkeep", {},
               message=f"Create models directory for {name}")
    write_json(f"{slug}/deals/.gitkeep", {},
               message=f"Create deals directory for {name}")
    return meta


def delete_client(slug: str) -> None:
    """Delete a client and all its data."""
    from store.backend import delete_file
    # Delete all models
    for name in list_dir(f"{slug}/models"):
        delete_file(f"{slug}/models/{name}", message=f"Delete model {name}")
    # Delete all deals
    for name in list_dir(f"{slug}/deals"):
        delete_file(f"{slug}/deals/{name}", message=f"Delete deal {name}")
    # Delete meta
    delete_file(f"{slug}/meta.json", message=f"Delete client {slug}")
