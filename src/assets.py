"""Install our own character assets without rewriting the user's pack manifest."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import tomllib
from .platform_support import config_directory

ROOT = Path(__file__).resolve().parents[1]
CHARACTER = "pixel-drummer-nayu"
ANIMSET = "pixel-drummer-beats"
# Astra 0.2.7 reads only schema 5: animpacks/<id>/animpack.toml with a uid.
SCHEMA = 5
UID = re.compile(r'^uid = "[^"\n]*"$', re.MULTILINE)


def pack_directory() -> Path:
    override = os.environ.get("PIXEL_DRUMMER_PACK")
    if override:
        return Path(override)
    return config_directory() / "companion" / "pack"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _legacy(relative: str) -> list[str]:
    """Where the engine's schema 4 -> 5 conversion took this file from."""
    parts = relative.split("/")
    if parts[0] == "animpacks" and parts[-1] == "animpack.toml":
        return [f"animsets/{parts[1]}/animset.toml"]
    if parts[0] == "animpacks" and parts[2] == "clips":
        return [f"characters/{name}/sprites/{parts[-1]}" for name in (CHARACTER, "pixel-band-proxy")]
    return [relative]


def _migrated_from_ours(pack: Path, relative: str, previous: dict) -> bool:
    # The converter backs the old tree up untouched; if that copy is the one we
    # installed, the converted file is ours too and not a user edit.
    for backup in pack.glob(".pre-migration-*"):
        for old in _legacy(relative):
            source = backup / old
            if source.is_file() and previous.get(old) == _sha(source.read_bytes()):
                return True
    return False


def install(pack: Path | None = None) -> dict:
    pack = pack or pack_directory()
    manifest = pack / "companion.toml"
    if manifest.exists():
        version = tomllib.loads(manifest.read_text(encoding="utf-8")).get("meta", {}).get("schema_version")
        if isinstance(version, int) and version < SCHEMA:
            raise ValueError(f"Пак Astra схемы {version}; Pixel Drummer нужна Astra 0.2.7 или новее (схема {SCHEMA}).")
    source = ROOT / "src" / "resources" / "assets" / "pack"
    # A receipt makes repeat installation idempotent and protects edited files.
    receipt = pack / "pixel-drummer-receipt.json"
    previous = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
    items = []
    for src in sorted(source.rglob("*")):
        if not src.is_file():
            continue
        relative = src.relative_to(source).as_posix()
        dest = pack / relative
        data = src.read_bytes()
        if dest.exists():
            current = dest.read_bytes()
            existing = _sha(current)
            if existing != _sha(data) and existing != previous.get(relative) and not _migrated_from_ours(pack, relative, previous):
                raise ValueError(f"Файл изменён пользователем; установка остановлена: {relative}")
            if src.name == "animpack.toml":
                # The uid is the pack's identity in the engine's library; keep the one it holds.
                kept = UID.search(current.decode("utf-8"))
                if kept:
                    data = UID.sub(lambda _: kept.group(0), data.decode("utf-8"), count=1).encode("utf-8")
        items.append((data, dest, relative, _sha(data)))
    for data, dest, _, _ in items:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
            temp = Path(tmp.name)
        try:
            temp.write_bytes(data)
            temp.replace(dest)
        finally:
            temp.unlink(missing_ok=True)
    receipt.write_text(json.dumps({r: h for _, _, r, h in items}, indent=2), encoding="utf-8")
    return {"installed": True, "character": CHARACTER, "animset": ANIMSET, "files": len(items)}
