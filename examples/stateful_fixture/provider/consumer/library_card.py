"""One library card per passing span check.

The card is the consume residue an agent can load. It quotes a span, names
rivals when two spans compete, and stays reported. It is not a constraint
and not a second copy of the vault.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CHECK_SPAN = "Quote the span or return empty."
CHECK_RIVALS = "Quote the span or return empty. Name every rival. Do not pick a winner."


def library_path(root: Path) -> Path:
    return Path(root) / "consumer" / "claims" / "library.jsonl"


def make_card(claim: dict[str, Any], use: str, rivals: list[str]) -> dict[str, Any] | None:
    """Project a KEEP row into a teaching card. Returns None when the check is incomplete."""
    use_name = (use or "").strip()
    item_id = (claim.get("item_id") or "").strip()
    span = (claim.get("evidence_span") or "").strip()
    falsifier = (claim.get("falsifier") or "").strip()
    source_path = (claim.get("source_path") or "").strip()
    source_hash = (claim.get("source_hash") or "").strip()
    if not (use_name and item_id and span and falsifier and source_path and source_hash):
        return None
    named = []
    seen: set[str] = set()
    for rival in rivals:
        other = (rival or "").strip()
        if not other or other == item_id or other in seen:
            continue
        seen.add(other)
        named.append(other)
    return {
        "item_id": item_id,
        "use": use_name,
        "epistemic_class": "reported",
        "usable_as_constraint": False,
        "declares_truth": False,
        "check": CHECK_RIVALS if named else CHECK_SPAN,
        "span": span,
        "source_path": source_path,
        "source_hash": source_hash,
        "falsifier": falsifier,
        "rivals": named,
    }


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def admit(path: Path, card: dict[str, Any]) -> dict[str, Any]:
    """Append the card once. A repeat of the same item and use returns the existing line."""
    if card.get("usable_as_constraint") or card.get("declares_truth"):
        return {"card": None, "appended": False, "reason": "card would teach a constraint"}
    if card.get("epistemic_class") != "reported":
        return {"card": None, "appended": False, "reason": "card class is not reported"}
    key = (card.get("item_id"), card.get("use"))
    if not key[0] or not key[1]:
        return {"card": None, "appended": False, "reason": "card missing item_id or use"}
    existing = _read(path)
    for row in existing:
        if row.get("item_id") == key[0] and row.get("use") == key[1]:
            return {"card": row, "appended": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(card, ensure_ascii=False, separators=(",", ":")) + "\n")
    return {"card": card, "appended": True}


def cards_for_use(root: Path, use: str) -> list[dict[str, Any]]:
    """Cards an agent may load for this use. Constraint-marked lines are skipped."""
    wanted = (use or "").strip()
    if not wanted:
        return []
    kept: list[dict[str, Any]] = []
    for row in _read(library_path(root)):
        if row.get("use") != wanted:
            continue
        if row.get("usable_as_constraint") or row.get("declares_truth"):
            continue
        if row.get("epistemic_class") != "reported":
            continue
        if not (row.get("span") or "").strip():
            continue
        kept.append(row)
    return kept
