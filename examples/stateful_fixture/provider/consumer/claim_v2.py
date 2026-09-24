"""Small dependency-free validator for the additive SSR claim-v2 boundary."""
from __future__ import annotations

import re
from typing import Any

HEX64 = re.compile(r"^[0-9a-f]{64}$")
BASES = {"reported", "observed", "derived", "replicated", "unknown"}
ROLES = {"primary", "secondary", "tertiary", "unknown"}
SUPPORT = {"supports", "partially_supports", "does_not_support", "not_assessed", "unknown"}


def validate_v2(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = ("schema_version", "item_id", "claim_text", "falsifier", "source_path", "source_hash",
                "evidence_basis", "source_role", "support_assessment", "independence_group",
                "validity_interval", "correction_links", "verification_receipt")
    for key in required:
        if key not in row:
            errors.append(f"missing {key}")
    if errors:
        return errors
    if row["schema_version"] != "ssr-claim-v2": errors.append("schema_version must be ssr-claim-v2")
    for key in ("item_id", "claim_text", "falsifier", "source_path", "independence_group"):
        if not isinstance(row[key], str) or not row[key].strip(): errors.append(f"{key} must be nonempty text")
    if not isinstance(row["source_hash"], str) or not HEX64.fullmatch(row["source_hash"]): errors.append("source_hash must be lowercase SHA-256")
    if row["evidence_basis"] not in BASES: errors.append("invalid evidence_basis")
    if row["source_role"] not in ROLES: errors.append("invalid source_role")
    if row["support_assessment"] not in SUPPORT: errors.append("invalid support_assessment")
    interval = row["validity_interval"]
    if not isinstance(interval, dict) or not isinstance(interval.get("as_of"), str): errors.append("validity_interval.as_of required")
    links = row["correction_links"]
    if not isinstance(links, list) or any(not isinstance(x, str) or not x for x in links): errors.append("correction_links must be a list of IDs")
    receipt = row["verification_receipt"]
    if receipt is not None and not isinstance(receipt, dict): errors.append("verification_receipt must be object or null")
    if row["evidence_basis"] == "replicated" and row["support_assessment"] in {"not_assessed", "unknown"}:
        errors.append("replicated requires an assessed support relationship")
    if row["support_assessment"] == "supports" and not (row.get("evidence_span") or "").strip():
        errors.append("supports requires evidence_span")
    return errors


def is_valid_v2(row: dict[str, Any]) -> bool:
    return not validate_v2(row)
