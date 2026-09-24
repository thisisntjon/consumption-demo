"""Caller-owned task history; freshness is checked at use, never inferred from age.

Single writer, immutable numbered records. This records author checks, not independent
acceptance or truth. A caller must supply a new checked-provider response at each use.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _file(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or ":" in relative:
        raise ValueError("artifact path must be relative and contained")
    target = (root / path).resolve(strict=True)
    if root not in target.parents or not target.is_file():
        raise ValueError("artifact outside task root")
    return target


def _binding(root, relative):
    return {"path": relative, "sha256": digest(_file(root, relative).read_bytes())}


def _native(response):
    if response.get("schema_version") != "consumption-lookup-v1":
        raise ValueError("checked lookup response required")
    native = response.get("native", {})
    if native.get("status") != "answered" or not native.get("snapshot_version") or not native.get("claims"):
        raise ValueError("answered evidence with snapshot and claims required")
    return native


def read_history(root):
    root = Path(root).resolve(strict=True)
    folder = root / "task-history"
    if not folder.exists():
        return []
    records, previous = [], None
    for number, path in enumerate(sorted(folder.glob("*.json")), 1):
        if path.name != f"{number:06d}.json":
            raise ValueError("missing or reordered history record")
        raw = path.read_bytes()
        record = json.loads(raw)
        if record.get("sequence") != number or record.get("previous_sha256") != previous:
            raise ValueError("history chain mismatch")
        previous = digest(raw)
        records.append(record)
    return records


def append(root, event):
    root = Path(root).resolve(strict=True)
    records = read_history(root)
    folder = root / "task-history"
    folder.mkdir(exist_ok=True)
    number = len(records) + 1
    previous = digest((folder / f"{number-1:06d}.json").read_bytes()) if records else None
    record = dict(event, sequence=number, previous_sha256=previous,
                  recorded_at=datetime.now(timezone.utc).isoformat())
    with (folder / f"{number:06d}.json").open("xb") as stream:
        stream.write(_bytes(record))
    return record


def record_checked(root, *, task, actor, session, lookup, output, check):
    root = Path(root).resolve(strict=True)
    if not all(isinstance(x, str) and x.strip() for x in (task, actor, session)):
        raise ValueError("task, actor and session required")
    response = json.loads(_file(root, lookup).read_bytes())
    native = _native(response)
    report = json.loads(_file(root, check).read_bytes())
    bound = _binding(root, output)
    if report.get("passed") is not True or report.get("output_sha256") != bound["sha256"]:
        raise ValueError("successful check bound to exact output required")
    return append(root, {"event": "checked", "task": task, "actor": actor, "session": session,
        "lookup": _binding(root, lookup), "output": bound, "check": _binding(root, check),
        "snapshot": native["snapshot_version"], "claim_ids": sorted(c["item_id"] for c in native["claims"]),
        "accepted": False, "scope": "author-checked task; separate review is distinct"})


def assess(root, record, fresh_lookup):
    """Fail closed on changed provider snapshot, output/check/input, or unusable evidence."""
    root = Path(root).resolve(strict=True)
    records = read_history(root)
    if record not in records or record.get("event") != "checked":
        raise ValueError("checked record must belong to retained history")
    reasons = []
    for key in ("lookup", "output", "check"):
        try:
            if _binding(root, record[key]["path"]) != record[key]:
                reasons.append(key + "_changed")
        except (OSError, ValueError):
            reasons.append(key + "_missing")
    response = json.loads(_file(root, fresh_lookup).read_bytes())
    try:
        native = _native(response)
        if native["snapshot_version"] != record["snapshot"]:
            reasons.append("evidence_snapshot_changed")
        if sorted(c["item_id"] for c in native["claims"]) != record["claim_ids"]:
            reasons.append("claim_selection_changed")
    except ValueError:
        reasons.append("evidence_unusable")
    return {"state": "stale" if reasons else "checked_current", "reasons": reasons,
            "task": record["task"], "checked_sequence": record["sequence"],
            "fresh_lookup": _binding(root, fresh_lookup), "accepted": False}


def record_assessment(root, record, fresh_lookup):
    result = assess(root, record, fresh_lookup)
    return append(root, dict(result, event="freshness_check"))
