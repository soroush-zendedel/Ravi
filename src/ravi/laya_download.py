"""Local Laya weights under RAVI_MODELS_DIR/laya — same sharing model as GGUF."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ravi import envutil as eu
from ravi import share as rshare


def catalog(root: Path) -> list[dict[str, Any]]:
    path = root / "config" / "laya" / "models.yaml"
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("models") or [])


def laya_root(root: Path) -> Path:
    env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    base = rshare.resolve_models_dir(env.get("RAVI_MODELS_DIR") or "./models", root)
    path = base / "laya"
    path.mkdir(parents=True, exist_ok=True)
    return path


def variant_from_env(env: dict[str, str]) -> str:
    v = (env.get("RAVI_LAYA_VARIANT") or "english").strip().lower()
    if v in ("multilingual", "multi", "full"):
        return "laya-multilingual"
    return "laya-english"


def local_dir_for(root: Path, model_id: str) -> Path:
    for row in catalog(root):
        if row.get("id") == model_id:
            return laya_root(root) / str(row.get("local_dir") or model_id)
    # fallbacks
    if model_id in ("laya-multilingual", "multilingual"):
        return laya_root(root) / "multilingual"
    return laya_root(root) / "english"


def is_present(root: Path, model_id: str | None = None) -> bool:
    env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    mid = model_id or variant_from_env(env)
    if mid in ("english", "en"):
        mid = "laya-english"
    elif mid in ("multilingual", "multi"):
        mid = "laya-multilingual"
    d = local_dir_for(root, mid)
    if not d.is_dir():
        return False
    # weights or any non-empty tree (snapshot_download layout)
    markers = list(d.rglob("*.safetensors")) + list(d.rglob("*.bin")) + list(
        d.rglob("config.json")
    )
    return bool(markers) or any(p.is_file() for p in d.rglob("*"))


def detect(root: Path) -> dict[str, Any]:
    """Scan models dir for Laya checkpoints."""
    env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    wanted = variant_from_env(env)
    rows = []
    for row in catalog(root):
        mid = row["id"]
        present = is_present(root, mid)
        rows.append(
            {
                "id": mid,
                "hf_repo": row.get("hf_repo"),
                "path": str(local_dir_for(root, mid)),
                "present": present,
                "active_candidate": mid == wanted,
            }
        )
    return {
        "models_root": str(laya_root(root)),
        "wanted": wanted,
        "wanted_present": is_present(root, wanted),
        "items": rows,
    }


def pull(root: Path, model_id: str = "laya-english", progress=None) -> Path:
    rows = {r["id"]: r for r in catalog(root) if r.get("id")}
    if model_id in ("english", "en"):
        model_id = "laya-english"
    elif model_id in ("multilingual", "multi"):
        model_id = "laya-multilingual"
    row = rows.get(model_id)
    if not row:
        raise ValueError(f"Unknown Laya model id: {model_id}")
    dest = local_dir_for(root, model_id)
    dest.mkdir(parents=True, exist_ok=True)
    repo = row["hf_repo"]
    from huggingface_hub import snapshot_download

    if progress:
        progress(f"Downloading {repo} -> {dest}")
    snapshot_download(repo_id=repo, local_dir=str(dest), local_dir_use_symlinks=False)
    return dest
