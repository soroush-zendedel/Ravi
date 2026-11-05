"""Multi-mirror download + catalog loaded from config/local-models.yaml."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import httpx
import yaml

LogFn = Callable[[str], None]
ProgressFn = Callable[[float, float | None, str], None]

DEFAULT_MODEL_ID = "qwen3-8b-q4km"

CAPABILITY_STYLE = {
    "chat": "cyan",
    "vision": "magenta",
    "image_gen": "yellow",
    "audio_asr": "green",
    "audio_tts": "green",
    "code": "blue",
    "reasoning": "white",
    "multilingual": "bright_cyan",
}


@dataclass
class CatalogModel:
    id: str
    name: str
    quant: str
    size_gb: float
    ram_gb: int
    capabilities: list[str] = field(default_factory=list)
    ollama_tags: list[str] = field(default_factory=list)
    hf_repo: str | None = None
    hf_file: str | None = None
    blurb: str = ""
    family: str = ""
    context: str = ""
    default: bool = False
    note: str = ""
    languages: list[str] = field(default_factory=lambda: ["en"])
    role: str = "chat"
    engine: str = "llama.cpp"

    @property
    def size_label(self) -> str:
        return f"~{self.size_gb:.1f} GB"

    @property
    def ram_label(self) -> str:
        return f"{self.ram_gb} GB RAM+"


_catalog_cache: list[CatalogModel] | None = None
_meta_cache: dict[str, Any] | None = None


def _catalog_path(root: Path | None = None) -> Path:
    if root is None:
        # walk from package
        here = Path(__file__).resolve()
        for c in [here.parents[2], here.parents[3], Path.cwd()]:
            p = c / "config" / "local-models.yaml"
            if p.is_file():
                return p
        return Path.cwd() / "config" / "local-models.yaml"
    return root / "config" / "local-models.yaml"


def load_catalog(root: Path | None = None, *, force: bool = False) -> list[CatalogModel]:
    global _catalog_cache, _meta_cache
    if _catalog_cache is not None and not force:
        return _catalog_cache

    path = _catalog_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"Catalog not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _meta_cache = {
        "version": data.get("version"),
        "default_id": data.get("default_id") or DEFAULT_MODEL_ID,
        "capability_labels": data.get("capability_labels") or {},
        "capability_notes": (data.get("capability_notes") or "").strip(),
    }
    models: list[CatalogModel] = []
    for raw in data.get("models") or []:
        if not isinstance(raw, dict) or raw.get("skip"):
            continue
        mid = raw.get("id")
        if not mid or raw.get("name") in (None, "skip"):
            continue
        models.append(
            CatalogModel(
                id=str(mid),
                name=str(raw.get("name") or mid),
                quant=str(raw.get("quant") or ""),
                size_gb=float(raw.get("size_gb") or 0),
                ram_gb=int(raw.get("ram_gb") or 8),
                capabilities=list(raw.get("capabilities") or []),
                ollama_tags=list(raw.get("ollama_tags") or []),
                hf_repo=raw.get("hf_repo"),
                hf_file=raw.get("hf_file"),
                blurb=str(raw.get("blurb") or ""),
                family=str(raw.get("family") or ""),
                context=str(raw.get("context") or ""),
                default=bool(raw.get("default"))
                or str(mid) == str(_meta_cache["default_id"]),
                note=str(raw.get("note") or ""),
                languages=list(raw.get("languages") or ["en"]),
                role=str(raw.get("role") or "chat"),
                engine=str(raw.get("engine") or "llama.cpp"),
            )
        )
    _catalog_cache = models
    return models


def catalog_meta(root: Path | None = None) -> dict[str, Any]:
    load_catalog(root)
    assert _meta_cache is not None
    return _meta_cache


# Back-compat name used elsewhere
def _ensure_loaded(root: Path | None = None) -> list[CatalogModel]:
    return load_catalog(root)


@property  # placeholder removed
def _noop():
    return None


# Expose LOCAL_CATALOG as a dynamic list proxy via function
def get_local_catalog(root: Path | None = None) -> list[CatalogModel]:
    return load_catalog(root)


# Module-level for older imports — refreshed on load
LOCAL_CATALOG: list[CatalogModel] = []


def refresh_catalog(root: Path | None = None) -> list[CatalogModel]:
    global LOCAL_CATALOG
    LOCAL_CATALOG = load_catalog(root, force=True)
    return LOCAL_CATALOG


def get_catalog_model(model_id: str | None, root: Path | None = None) -> CatalogModel:
    models = load_catalog(root)
    meta = catalog_meta(root)
    if not model_id:
        for m in models:
            if m.default or m.id == meta.get("default_id"):
                return m
        return models[0]

    key = model_id.strip().lower()
    for m in models:
        if m.id.lower() == key:
            return m
        if m.hf_file and m.hf_file.lower() == key:
            return m
        if m.hf_repo and key in (
            m.hf_repo.lower(),
            m.hf_repo.lower().split("/")[-1],
        ):
            return m
        if key in [t.lower() for t in m.ollama_tags]:
            return m
    for m in models:
        if key.replace(":", "-") in m.id or m.id in key.replace(":", "-"):
            return m
    for m in models:
        if m.default:
            return m
    return models[0]


def detect_system_ram_gb() -> int | None:
    """Best-effort total RAM detection (Linux / macOS / Windows)."""
    # Linux
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.is_file():
            for line in meminfo.read_text().splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return max(1, kb // (1024 * 1024))
    except Exception:
        pass
    # macOS
    try:
        p = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if p.returncode == 0 and p.stdout.strip().isdigit():
            return max(1, int(p.stdout.strip()) // (1024**3))
    except Exception:
        pass
    # Windows (wmic / PowerShell)
    try:
        p = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if p.returncode == 0 and p.stdout.strip().isdigit():
            return max(1, int(p.stdout.strip()) // (1024**3))
    except Exception:
        pass
    return None


def filter_by_ram(
    models: list[CatalogModel],
    ram_gb: int | None,
    *,
    headroom: float = 0.85,
) -> list[CatalogModel]:
    """Keep models whose recommended RAM fits in ~headroom of system RAM."""
    if ram_gb is None:
        return list(models)
    budget = max(2, int(ram_gb * headroom))
    return [m for m in models if m.ram_gb <= budget]


def models_dir(root: Path) -> Path:
    env = os.environ.get("RAVI_MODELS_DIR")
    d = Path(env).expanduser() if env else root / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_local_gguf(root: Path, filename: str | None = None) -> Path | None:
    d = models_dir(root)
    if filename:
        direct = d / filename
        if direct.is_file() and direct.stat().st_size > 1_000_000:
            return direct
        lower = filename.lower()
        for p in d.rglob("*"):
            if p.is_file() and p.name.lower() == lower and p.stat().st_size > 1_000_000:
                return p
    default = get_catalog_model(None, root)
    if default.hf_file and filename != default.hf_file:
        return find_local_gguf(root, default.hf_file)
    return None


def list_local_ggufs(root: Path) -> list[Path]:
    d = models_dir(root)
    return sorted(
        [p for p in d.rglob("*.gguf") if p.is_file() and p.stat().st_size > 1_000_000],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def hf_urls(repo: str, filename: str) -> list[tuple[str, str]]:
    repo_q = quote(repo, safe="/")
    file_q = quote(filename, safe="/")
    return [
        ("huggingface", f"https://huggingface.co/{repo_q}/resolve/main/{file_q}"),
        ("hf-mirror", f"https://hf-mirror.com/{repo_q}/resolve/main/{file_q}"),
        (
            "hf-cdn",
            f"https://cdn-lfs.huggingface.co/repos/{repo_q}/resolve/main/{file_q}",
        ),
    ]


def download_http(
    url: str,
    dest: Path,
    *,
    log: LogFn | None = None,
    progress: ProgressFn | None = None,
    timeout: float = 60.0,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    headers = {"User-Agent": "Ravi/0.1 (local-model-fetch)"}
    start = partial.stat().st_size if partial.is_file() else 0
    if start:
        headers["Range"] = f"bytes={start}-"
        if log:
            log(f"Resuming from byte {start}")

    with httpx.stream(
        "GET", url, headers=headers, follow_redirects=True, timeout=timeout
    ) as r:
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} from {url}")
        total = None
        cr = r.headers.get("Content-Range")
        cl = r.headers.get("Content-Length")
        if cr and "/" in cr:
            try:
                total = float(cr.split("/")[-1])
            except ValueError:
                total = None
        elif cl:
            try:
                total = float(cl) + start
            except ValueError:
                total = None

        mode = "ab" if start else "wb"
        done = float(start)
        with partial.open(mode) as f:
            for chunk in r.iter_bytes(1024 * 256):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total, dest.name)

    partial.replace(dest)
    if log:
        log(f"Saved {dest}")


def try_ollama_pull(
    tag: str, *, log: LogFn | None = None, use_docker: bool = True
) -> bool:
    def _run(cmd: list[str]) -> bool:
        if log:
            log(" ".join(cmd))
        p = subprocess.run(cmd, capture_output=True, text=True)
        if log:
            for line in ((p.stdout or "") + (p.stderr or "")).splitlines()[-5:]:
                log(line)
        return p.returncode == 0

    bin_path = shutil.which("ollama")
    if bin_path and _run([bin_path, "pull", tag]):
        return True
    if use_docker and _run(["docker", "exec", "ravi-ollama", "ollama", "pull", tag]):
        return True
    return False


def import_gguf_to_ollama(
    gguf: Path, model_name: str, *, log: LogFn | None = None
) -> bool:
    modelfile = gguf.parent / f"Modelfile.{model_name.replace(':', '_')}"
    modelfile.write_text(f"FROM {gguf.resolve()}\n", encoding="utf-8")
    bin_path = shutil.which("ollama")
    if not bin_path:
        if log:
            log("Ollama CLI missing — GGUF kept on disk.")
        return False
    p = subprocess.run(
        [bin_path, "create", model_name, "-f", str(modelfile)],
        capture_output=True,
        text=True,
    )
    if log:
        log((p.stdout or p.stderr or "")[-300:])
    return p.returncode == 0


def download_model(
    root: Path,
    model: CatalogModel,
    *,
    log: LogFn | None = None,
    progress: ProgressFn | None = None,
) -> tuple[str, Path | None]:
    def _log(msg: str) -> None:
        if log:
            log(msg)

    if model.hf_file:
        existing = find_local_gguf(root, model.hf_file)
        if existing:
            _log(f"Found existing file: {existing}")
            return "local-disk", existing

    for tag in model.ollama_tags:
        _log(f"Mirror [ollama] trying {tag}")
        try:
            if try_ollama_pull(tag, log=log):
                _log(f"Ollama pull OK: {tag}")
                return "ollama", None
        except Exception as e:
            _log(f"Ollama error: {e}")

    if model.hf_repo and model.hf_file:
        dest = models_dir(root) / model.hf_file
        for mid, url in hf_urls(model.hf_repo, model.hf_file):
            _log(f"Mirror [{mid}] {url}")
            try:
                download_http(url, dest, log=log, progress=progress)
                if dest.is_file() and dest.stat().st_size > 1_000_000:
                    tag = model.ollama_tags[0] if model.ollama_tags else model.id
                    import_gguf_to_ollama(dest, tag, log=log)
                    return mid, dest
            except Exception as e:
                _log(f"Mirror [{mid}] failed: {e}")
                continue

    raise RuntimeError(
        f"All mirrors failed for {model.name} ({model.id}). "
        "Check network, disk space, and Ollama / Hugging Face reachability."
    )


def remove_gguf(root: Path, filename: str) -> list[Path]:
    removed: list[Path] = []
    for p in list_local_ggufs(root):
        if p.name == filename or p.stem == filename or filename in str(p):
            p.unlink(missing_ok=True)
            removed.append(p)
    return removed


def remove_all_ggufs(root: Path) -> list[Path]:
    removed: list[Path] = []
    for p in list_local_ggufs(root):
        p.unlink(missing_ok=True)
        removed.append(p)
    return removed


# Eager load if path exists (best effort)
try:
    refresh_catalog()
except Exception:
    pass
