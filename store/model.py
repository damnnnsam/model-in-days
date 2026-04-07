"""
Model persistence with override resolution.

A model is either:
- A base model: full ModelInputs snapshot (base=None, inputs={...})
- A layered model: parent reference + override dict (base="parent-slug", overrides={...})

resolve_model() walks the parent chain to produce a complete ModelInputs.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

from engine.inputs import ModelInputs
from store.backend import read_json, write_json, list_dir, delete_file
from store.serialization import (
    model_inputs_to_dict, dict_to_model_inputs, apply_overrides, compute_overrides,
)


@dataclass
class ModelFile:
    name: str
    description: str = ""
    base: str | None = None          # slug of parent model (None = base model)
    inputs: dict | None = None       # full ModelInputs dict (base models only)
    overrides: dict | None = None    # partial overrides (layered models only)
    created: str = ""
    modified: str = ""


def _model_path(client_slug: str, model_slug: str) -> str:
    return f"{client_slug}/models/{model_slug}.json"


def list_models(client_slug: str) -> list[tuple[str, ModelFile]]:
    """List all models for a client. Returns list of (slug, ModelFile)."""
    models = []
    for name in list_dir(f"{client_slug}/models"):
        if not name.endswith(".json") or name.startswith("."):
            continue
        slug = name[:-5]  # strip .json
        mf = load_model_file(client_slug, slug)
        if mf is not None:
            models.append((slug, mf))
    return models


def load_model_file(client_slug: str, model_slug: str) -> ModelFile | None:
    """Load a raw model file (before resolution)."""
    data = read_json(_model_path(client_slug, model_slug))
    if data is None:
        return None
    return ModelFile(
        name=data.get("name", model_slug),
        description=data.get("description", ""),
        base=data.get("base"),
        inputs=data.get("inputs"),
        overrides=data.get("overrides"),
        created=data.get("created", ""),
        modified=data.get("modified", ""),
    )


def save_model(client_slug: str, model_slug: str, model: ModelFile) -> None:
    """Write a model file."""
    model.modified = datetime.now().isoformat(timespec="seconds")
    if not model.created:
        model.created = model.modified
    write_json(
        _model_path(client_slug, model_slug),
        asdict(model),
        message=f"Save model: {model.name} ({client_slug}/{model_slug})",
    )


def delete_model(client_slug: str, model_slug: str) -> None:
    """Delete a model file."""
    delete_file(_model_path(client_slug, model_slug),
                message=f"Delete model: {client_slug}/{model_slug}")


def resolve_model(client_slug: str, model_slug: str, _visited: set | None = None) -> ModelInputs:
    """
    Resolve a model to a full ModelInputs by walking the parent chain.

    For a base model: deserialize inputs directly.
    For a layered model: resolve(parent) then apply overrides.
    Detects circular references.
    """
    if _visited is None:
        _visited = set()

    if model_slug in _visited:
        raise ValueError(f"Circular model reference detected: {model_slug} in chain {_visited}")
    _visited.add(model_slug)

    mf = load_model_file(client_slug, model_slug)
    if mf is None:
        raise FileNotFoundError(f"Model not found: {client_slug}/models/{model_slug}.json")

    if mf.base is None:
        # Base model — full inputs
        if mf.inputs is None:
            raise ValueError(f"Base model {model_slug} has no inputs")
        return dict_to_model_inputs(mf.inputs)
    else:
        # Layered model — resolve parent then apply overrides
        parent_inp = resolve_model(client_slug, mf.base, _visited)
        if mf.overrides:
            return apply_overrides(parent_inp, mf.overrides)
        return parent_inp


def create_base_model(client_slug: str, slug: str, name: str,
                      inp: ModelInputs, description: str = "") -> None:
    """Create a new base model from a full ModelInputs."""
    mf = ModelFile(
        name=name,
        description=description,
        base=None,
        inputs=model_inputs_to_dict(inp),
        overrides=None,
    )
    save_model(client_slug, slug, mf)


def create_layered_model(client_slug: str, slug: str, name: str,
                         base_slug: str, overrides: dict,
                         description: str = "") -> None:
    """Create a model that layers overrides on top of a parent."""
    # Verify parent exists and resolves
    resolve_model(client_slug, base_slug)
    mf = ModelFile(
        name=name,
        description=description,
        base=base_slug,
        overrides=overrides,
        inputs=None,
    )
    save_model(client_slug, slug, mf)


def get_model_tree(client_slug: str) -> list[dict]:
    """
    Build the model tree for a client.
    Returns a list of root nodes, each with {slug, name, description, children: [...]}.
    """
    all_models = list_models(client_slug)
    by_slug = {slug: mf for slug, mf in all_models}

    # Build children map
    children_map: dict[str | None, list[str]] = {None: []}
    for slug, mf in all_models:
        parent = mf.base
        if parent not in children_map:
            children_map[parent] = []
        children_map.setdefault(parent, []).append(slug)

    def _build_node(slug: str) -> dict:
        mf = by_slug[slug]
        return {
            "slug": slug,
            "name": mf.name,
            "description": mf.description,
            "base": mf.base,
            "children": [_build_node(c) for c in children_map.get(slug, [])],
        }

    roots = children_map.get(None, [])
    return [_build_node(r) for r in roots]
