import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_INTERESTS_FILENAME = "catch_interested_recruits.json"


def interest_key(item):
    return str(
        item.get("recruit_id")
        or item.get("link")
        or f"{item.get('company', '')}::{item.get('title', '')}"
    ).strip().casefold()


def load_interests(path):
    path = Path(path)
    if not path.exists():
        return {
            "source": "catch",
            "generated_at": "",
            "count": 0,
            "items": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def write_interests(items, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "source": "catch",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": list(items),
    }
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def merge_interests(existing_items, new_items):
    merged = {}
    for item in existing_items:
        key = interest_key(item)
        if key:
            merged[key] = item
    added = 0
    for item in new_items:
        key = interest_key(item)
        if not key or key in merged:
            continue
        merged[key] = item
        added += 1
    return list(merged.values()), added


def add_interests(path, new_items):
    current = load_interests(path)
    items, added = merge_interests(current.get("items", []), new_items)
    write_interests(items, path)
    return {
        "path": Path(path),
        "count": len(items),
        "added": added,
        "items": items,
    }
