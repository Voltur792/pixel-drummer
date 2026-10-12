"""Atomic local JSON exchange, tolerating Windows' brief reader locks."""
import json
from pathlib import Path
import time
import uuid


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(20):
            try:
                temp.replace(path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.005)
    finally:
        temp.unlink(missing_ok=True)
