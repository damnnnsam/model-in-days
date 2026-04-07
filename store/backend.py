"""
Storage backend abstraction.

Auto-detects environment:
- Local development: direct filesystem read/write to data/clients/
- Streamlit Cloud: read/write via GitHub API (every write = a git commit)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# ── Environment detection ──────────────────────────────────────────────

def _is_streamlit_cloud() -> bool:
    """Detect if we're running on Streamlit Cloud."""
    return os.environ.get("STREAMLIT_SHARING_MODE") is not None or \
           os.environ.get("STREAMLIT_SERVER_HEADLESS") == "true"


def _get_data_root() -> Path:
    """Root directory for client data (local mode only)."""
    return Path(__file__).resolve().parent.parent / "data" / "clients"


def _get_github_config() -> dict:
    """Load GitHub config from Streamlit secrets."""
    try:
        import streamlit as st
        return {
            "token": st.secrets["GITHUB_TOKEN"],
            "repo": st.secrets["GITHUB_REPO"],
            "branch": st.secrets.get("GITHUB_BRANCH", "main"),
        }
    except Exception:
        return {}


# ── GitHub API helpers ─────────────────────────────────────────────────

def _github_request(method: str, url: str, token: str, data: dict | None = None) -> dict:
    """Make an authenticated GitHub API request."""
    import urllib.request
    import urllib.error

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps(data).encode() if data else None
    if body:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"_status": 404}
        raise


def _github_get_file(repo: str, path: str, token: str, branch: str = "main") -> dict | None:
    """Get file content and SHA from GitHub."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    resp = _github_request("GET", url, token)
    if resp.get("_status") == 404:
        return None
    return resp


def _github_write_file(repo: str, path: str, content: str, token: str,
                       branch: str = "main", message: str = "Update model data",
                       sha: str | None = None) -> dict:
    """Create or update a file on GitHub."""
    import base64
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    data = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        data["sha"] = sha
    return _github_request("PUT", url, token, data)


def _github_delete_file(repo: str, path: str, token: str,
                        branch: str = "main", message: str = "Delete model data",
                        sha: str | None = None) -> dict:
    """Delete a file on GitHub."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    data = {"message": message, "branch": branch}
    if sha:
        data["sha"] = sha
    return _github_request("DELETE", url, token, data)


def _github_list_dir(repo: str, path: str, token: str, branch: str = "main") -> list[str]:
    """List directory contents on GitHub. Returns list of names."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    resp = _github_request("GET", url, token)
    if resp.get("_status") == 404 or not isinstance(resp, list):
        return []
    return [item["name"] for item in resp if isinstance(item, dict)]


# ── Public API ─────────────────────────────────────────────────────────

def read_json(path: str) -> dict | None:
    """Read a JSON file. Path is relative to data/clients/.
    Returns None if file doesn't exist."""
    if _is_streamlit_cloud():
        cfg = _get_github_config()
        if not cfg:
            return None
        full_path = f"data/clients/{path}"
        result = _github_get_file(cfg["repo"], full_path, cfg["token"], cfg["branch"])
        if result is None:
            return None
        import base64
        content = base64.b64decode(result["content"]).decode()
        return json.loads(content)
    else:
        fp = _get_data_root() / path
        if not fp.exists():
            return None
        return json.loads(fp.read_text())


def write_json(path: str, data: Any, message: str = "Update model data") -> None:
    """Write a JSON file. Path is relative to data/clients/.
    On Streamlit Cloud, this creates a git commit."""
    content = json.dumps(data, indent=2, default=str)

    if _is_streamlit_cloud():
        cfg = _get_github_config()
        if not cfg:
            raise RuntimeError("GitHub config not found in Streamlit secrets")
        full_path = f"data/clients/{path}"
        # Check if file exists to get SHA for update
        existing = _github_get_file(cfg["repo"], full_path, cfg["token"], cfg["branch"])
        sha = existing.get("sha") if existing and existing.get("_status") != 404 else None
        _github_write_file(cfg["repo"], full_path, content, cfg["token"],
                          cfg["branch"], message, sha)
    else:
        fp = _get_data_root() / path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)


def list_dir(path: str) -> list[str]:
    """List directory contents. Path is relative to data/clients/.
    Returns list of names (files and directories)."""
    if _is_streamlit_cloud():
        cfg = _get_github_config()
        if not cfg:
            return []
        full_path = f"data/clients/{path}" if path else "data/clients"
        return _github_list_dir(cfg["repo"], full_path, cfg["token"], cfg["branch"])
    else:
        dp = _get_data_root() / path if path else _get_data_root()
        if not dp.exists():
            return []
        return [p.name for p in sorted(dp.iterdir())]


def delete_file(path: str, message: str = "Delete model data") -> None:
    """Delete a file. Path is relative to data/clients/."""
    if _is_streamlit_cloud():
        cfg = _get_github_config()
        if not cfg:
            raise RuntimeError("GitHub config not found in Streamlit secrets")
        full_path = f"data/clients/{path}"
        existing = _github_get_file(cfg["repo"], full_path, cfg["token"], cfg["branch"])
        if existing and existing.get("_status") != 404:
            _github_delete_file(cfg["repo"], full_path, cfg["token"],
                               cfg["branch"], message, existing.get("sha"))
    else:
        fp = _get_data_root() / path
        if fp.exists():
            fp.unlink()


def file_exists(path: str) -> bool:
    """Check if a file exists. Path is relative to data/clients/."""
    if _is_streamlit_cloud():
        cfg = _get_github_config()
        if not cfg:
            return False
        full_path = f"data/clients/{path}"
        result = _github_get_file(cfg["repo"], full_path, cfg["token"], cfg["branch"])
        return result is not None and result.get("_status") != 404
    else:
        return (_get_data_root() / path).exists()
