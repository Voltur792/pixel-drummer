"""Install our own character assets without rewriting the user's pack manifest."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHARACTER = "pixel-drummer-nayu"
ANIMSET = "pixel-drummer-beats"


def pack_directory() -> Path:
    override = os.environ.get("PIXEL_DRUMMER_PACK")
    if override:
        return Path(override)
    return Path(os.environ["APPDATA"]) / "astra" / "astra" / "config" / "companion" / "pack"


def install(pack: Path | None = None) -> dict:
    pack = pack or pack_directory()
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
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        if dest.exists():
            existing = hashlib.sha256(dest.read_bytes()).hexdigest()
            if existing != digest and existing != previous.get(relative):
                raise ValueError(f"Файл изменён пользователем; установка остановлена: {relative}")
        items.append((src, dest, relative, digest))
    for src, dest, _, _ in items:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
            temp = Path(tmp.name)
        try:
            shutil.copyfile(src, temp)
            temp.replace(dest)
        finally:
            temp.unlink(missing_ok=True)
    receipt.write_text(json.dumps({r: h for _, _, r, h in items}, indent=2), encoding="utf-8")
    return {"installed": True, "character": CHARACTER, "animset": ANIMSET, "files": len(items)}
