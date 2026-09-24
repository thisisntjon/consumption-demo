"""Structural acceptance checks for portable, locally pinned consumption receipts.

All paths use relative forward-slash notation under artifact_root. Every input
pins existing bytes, including a response describing an unavailable source.
application.scope='inspection_only' records non-admission inspection; only
eligible inputs may support a completed 'evidence_use'. The gate checks these
declared boundaries, not their semantic truth. It neither authenticates reviewers
nor proves that a reported check was independently executed. Validation is pure
and repeatable: receipt IDs are not registered and replay is not prevented here.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
import re
import stat


_HASH = re.compile(r"[0-9a-f]{64}\Z")
_STATUSES = {"eligible", "inspection_only", "ambiguous", "empty", "unavailable", "withdrawn"}
_NONPOSITIVE = _STATUSES - {"eligible", "inspection_only"}


def validate_receipt(
    receipt: dict,
    artifact_root: Path,
    *,
    task_id: str,
    actor_id: str,
    session_id: str,
    now: datetime | None = None,
    max_age_hours: float = 4.0,
) -> list[str]:
    """Return errors, or [] for a structurally valid accepted-use receipt.

    Unknown fields are permitted as extensions. Required fields are checked
    without coercion. Caller-supplied identity is compared exactly. Files must
    be regular files with matching SHA-256; symlinks and reparse points are
    rejected. This is a local check, not a defense against concurrent privileged
    filesystem mutation or a substitute for an authenticated acceptance ledger.
    """
    errors: list[str] = []

    def text_field(obj: dict, key: str, label: str) -> str | None:
        value = obj.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label} must be a nonblank string")
            return None
        return value

    def object_field(obj: dict, key: str, label: str) -> dict:
        value = obj.get(key)
        if not isinstance(value, dict):
            errors.append(f"{label} must be an object")
            return {}
        return value

    def one_of(value: object, choices: set[str], label: str) -> bool:
        if not isinstance(value, str) or value not in choices:
            errors.append(f"{label} must be one of {', '.join(sorted(choices))}")
            return False
        return True

    def reparse(path: Path) -> bool:
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )

    root: Path | None = None
    try:
        requested_root = Path(artifact_root)
        if reparse(requested_root):
            raise ValueError("artifact_root must not be a symlink or reparse point")
        root = requested_root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("artifact_root must be a directory")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        errors.append(f"artifact_root is invalid: {exc}")

    def artifact(obj: dict, label: str) -> str | None:
        name = text_field(obj, "path", f"{label}.path")
        digest = obj.get("sha256")
        valid_digest = isinstance(digest, str) and _HASH.fullmatch(digest) is not None
        if not valid_digest:
            errors.append(f"{label}.sha256 must be a lowercase SHA-256 hex digest")
        if name is None:
            return None
        parts = name.split("/")
        unsafe = (
            any(char in name for char in '\\<>:"|?*')
            or any(ord(char) < 32 for char in name)
            or PureWindowsPath(name).is_absolute()
            or bool(PureWindowsPath(name).drive)
            or any(part in {"", ".", ".."} or part.endswith((".", " ")) for part in parts)
            or any(PureWindowsPath(part).is_reserved() for part in parts)
        )
        if unsafe:
            errors.append(f"{label}.path must be a safe relative forward-slash path")
            return name
        if root is None:
            return name
        try:
            target = root
            for part in parts:
                target /= part
                if reparse(target):
                    raise ValueError("symlink or reparse point is not allowed")
            resolved = target.resolve(strict=True)
            resolved.relative_to(root)
            if not resolved.is_file():
                raise ValueError("artifact must be a regular file")
            computed = hashlib.sha256()
            with resolved.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    computed.update(chunk)
            if valid_digest and computed.hexdigest() != digest:
                errors.append(f"{label}.sha256 does not match artifact bytes")
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"{label}.path cannot be verified: {exc}")
        return name

    if not isinstance(receipt, dict):
        return errors + ["receipt must be an object"]
    if receipt.get("schema_version") != "consumption-use-v1":
        errors.append("schema_version must equal consumption-use-v1")
    text_field(receipt, "receipt_id", "receipt_id")
    for field, expected in (("task_id", task_id), ("actor_id", actor_id), ("session_id", session_id)):
        actual = text_field(receipt, field, field)
        if not isinstance(expected, str) or not expected.strip():
            errors.append(f"expected {field} must be a nonblank string")
        elif actual != expected:
            errors.append(f"{field} does not match expected {field}")
    if receipt.get("stage") != "accepted":
        errors.append("stage must equal accepted")
    result = receipt.get("result")
    one_of(result, {"completed", "abstained", "negative"}, "result")

    timestamp = text_field(receipt, "timestamp", "timestamp")
    checked_now = datetime.now(timezone.utc) if now is None else now
    age_valid = isinstance(max_age_hours, (int, float)) and not isinstance(max_age_hours, bool)
    age_valid = age_valid and math.isfinite(max_age_hours) and max_age_hours > 0
    if not age_valid:
        errors.append("max_age_hours must be a positive finite number")
    if not isinstance(checked_now, datetime) or checked_now.utcoffset() is None:
        errors.append("now must be a timezone-aware datetime")
    elif timestamp is not None:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.utcoffset() is None:
                raise ValueError("timezone offset is required")
            seconds = (checked_now - parsed).total_seconds()
            if seconds < 0:
                errors.append("timestamp is in the future")
            elif age_valid and seconds > max_age_hours * 3600:
                errors.append("timestamp has expired")
        except ValueError:
            errors.append("timestamp must be an ISO-8601 timezone-aware datetime")

    request = object_field(receipt, "request", "request")
    text_field(request, "purpose", "request.purpose")
    criterion = text_field(request, "acceptance_criterion", "request.acceptance_criterion")
    requirement = request.get("evidence_requirement")
    one_of(requirement, {"required", "not_applicable"}, "request.evidence_requirement")
    if requirement == "not_applicable":
        text_field(request, "exemption_reason", "request.exemption_reason")

    inputs = receipt.get("inputs")
    if not isinstance(inputs, list):
        errors.append("inputs must be an array")
        inputs = []
    input_status: dict[str, str | None] = {}
    input_names: set[str] = set()
    for index, entry in enumerate(inputs):
        label = f"inputs[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        name = artifact(entry, label)
        status = entry.get("status")
        status_valid = one_of(status, _STATUSES, f"{label}.status")
        if name is not None:
            if name.casefold() in input_names:
                errors.append(f"{label}.path duplicates an input path")
            input_names.add(name.casefold())
            input_status[name] = status if status_valid else None
    if requirement == "not_applicable" and inputs:
        errors.append("not_applicable requires no inputs")

    output = object_field(receipt, "output", "output")
    artifact(output, "output")
    application = object_field(receipt, "application", "application")
    text_field(application, "location", "application.location")
    text_field(application, "explanation", "application.explanation")
    scope = application.get("scope")
    one_of(scope, {"evidence_use", "inspection_only"}, "application.scope")
    used = application.get("input_paths")
    if not isinstance(used, list):
        errors.append("application.input_paths must be an array")
        used = []
    if requirement == "required" and not used:
        errors.append("required evidence must have at least one applied input")
    if requirement == "not_applicable" and used:
        errors.append("not_applicable requires no applied inputs")
    seen_used: set[str] = set()
    for index, name in enumerate(used):
        if not isinstance(name, str) or not name.strip():
            errors.append(f"application.input_paths[{index}] must be a nonblank string")
            continue
        if name.casefold() in seen_used:
            errors.append("application.input_paths contains a duplicate")
        seen_used.add(name.casefold())
        if name not in input_status:
            errors.append(f"application.input_paths[{index}] is not a declared input")
            continue
        status = input_status[name]
        if status == "inspection_only" and scope != "inspection_only":
            errors.append("inspection_only input requires application.scope inspection_only")
        if status in _NONPOSITIVE and result == "completed":
            errors.append(f"{status} input cannot support a completed result")

    check = object_field(receipt, "check", "check")
    text_field(check, "command", "check.command")
    if check.get("status") != "passed":
        errors.append("check.status must equal passed")
    check_criterion = text_field(check, "criterion", "check.criterion")
    if criterion is not None and check_criterion != criterion:
        errors.append("check.criterion must equal request.acceptance_criterion")
    check_report = object_field(check, "report", "check.report")
    artifact(check_report, "check.report")

    acceptance = object_field(receipt, "acceptance", "acceptance")
    for field in ("actor_id", "session_id"):
        reviewer = text_field(acceptance, field, f"acceptance.{field}")
        if reviewer is not None and reviewer == receipt.get(field):
            errors.append(f"acceptance.{field} must differ from author {field}")
    if acceptance.get("decision") != "accepted":
        errors.append("acceptance.decision must equal accepted")
    accepted_criterion = text_field(acceptance, "criterion", "acceptance.criterion")
    if criterion is not None and accepted_criterion != criterion:
        errors.append("acceptance.criterion must equal request.acceptance_criterion")
    if acceptance.get("output_sha256") != output.get("sha256") or not isinstance(
        acceptance.get("output_sha256"), str
    ):
        errors.append("acceptance.output_sha256 must match output.sha256")
    if not isinstance(acceptance.get("check_sha256"), str) or (
        acceptance.get("check_sha256") != check_report.get("sha256")
    ):
        errors.append("acceptance.check_sha256 must match check.report.sha256")
    return errors
