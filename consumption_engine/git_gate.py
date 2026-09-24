"""Read-only, fail-closed checks tying a use receipt to the staged Git diff.

The gate validates evidence and an index snapshot; it does not authenticate a
reviewer's identity or lock the index after it returns. No commit message,
legacy success log, or environment override can qualify a change.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Iterable

from .receipt import validate_receipt


STATE_PATHS = frozenset(
    {"consumer/claims/reuse.jsonl", "runs.jsonl"}
)


class GitInspectionError(RuntimeError):
    """Git could not establish a reliable repository/index snapshot."""


def _receipt_namespace(name: str) -> bool:
    """Only dedicated receipt artifacts may be excluded, never source/config."""
    return (
        isinstance(name, str)
        and "\\" not in name
        and all(part not in {"", ".", ".."} for part in name.split("/"))
        and name.endswith(".json")
        and name.startswith(("workflow/receipts/", "consumer/receipts/"))
    )


def _git(repo: Path, args: list[str], *, allowed_codes: tuple[int, ...] = (0,)):
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            [
                "git", "--no-pager", "--literal-pathspecs",
                "-c", "color.ui=false", "-c", "diff.ignoreSubmodules=none",
                "-C", str(repo), *args,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitInspectionError(f"Cannot execute Git: {exc}") from exc
    if result.returncode not in allowed_codes:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise GitInspectionError(
            f"Git inspection failed (exit {result.returncode}): {detail[:1000]}"
        )
    return result


def _repository_root(repo: Path) -> Path:
    raw = _git(Path(repo), ["rev-parse", "--show-toplevel"]).stdout
    return Path(os.fsdecode(raw.rstrip(b"\r\n"))).resolve()


def _head(repo: Path) -> str:
    result = _git(repo, ["rev-parse", "--verify", "HEAD"], allowed_codes=(0, 128))
    if result.returncode == 0:
        return result.stdout.decode("ascii").strip()
    # Failure to resolve HEAD is not, by itself, evidence of an empty repo.
    symbolic = _git(repo, ["symbolic-ref", "--quiet", "HEAD"])
    reference = os.fsdecode(symbolic.stdout.rstrip(b"\r\n"))
    exists = _git(repo, ["show-ref", "--verify", "--quiet", reference], allowed_codes=(0, 1))
    if exists.returncode == 1:
        return "UNBORN"
    raise GitInspectionError("HEAD exists but cannot be resolved; repository is not unborn")


def staged_binding(repo: Path, exclude_paths: Iterable[str] = ()) -> dict:
    """Return the complete staged-diff binding, excluding explicit state paths.

    Paths are exact Git-relative names, never patterns. Only the two known
    runtime ledgers are automatically exempt. A caller may additionally exempt
    its explicit .json receipt path under workflow/receipts/ or consumer/receipts/
    to avoid a self-referential receipt hash. Git
    failures raise GitInspectionError; they are never treated as no changes.
    """
    exclusions = tuple(exclude_paths)
    if any(not _receipt_namespace(name) for name in exclusions):
        raise GitInspectionError(
            "Receipt exclusion must be a relative .json path under workflow/receipts/ or consumer/receipts/"
        )
    root = _repository_root(Path(repo))
    head = _head(root)
    raw_names = _git(
        root,
        ["diff", "--cached", "--name-only", "-z", "--no-renames",
         "--no-ext-diff", "--no-textconv"],
    ).stdout
    names = [os.fsdecode(name) for name in raw_names.split(b"\0") if name]
    excluded = STATE_PATHS | set(exclusions)
    files = [name for name in names if name not in excluded]
    # A bare '--' would mean every path, so never invoke diff with an empty
    # inclusion list. Hash the exact raw binary diff, including path metadata.
    diff = _git(
        root,
        ["diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv", "--", *files],
    ).stdout if files else b""
    if _head(root) != head:
        raise GitInspectionError("Repository HEAD changed during Git inspection")
    return {
        "repository_head": head,
        "staged_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "files": files,
        "excluded_files": [name for name in names if name in excluded],
    }


def _result(status: str, allowed: bool, errors: list[str], binding: dict | None = None) -> dict:
    return {
        "status": status,
        "allowed": allowed,
        "consumption_qualified": allowed and status == "accepted",
        "errors": errors,
        "repository_head": binding["repository_head"] if binding else None,
        "staged_diff_sha256": binding["staged_diff_sha256"] if binding else None,
        "files": binding["files"] if binding else [],
        "excluded_files": binding["excluded_files"] if binding else [],
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def gate(
    repo: Path,
    receipt_path: Path | None,
    artifact_root: Path | None,
    *,
    task_id: str | None,
    actor_id: str | None,
    session_id: str | None,
) -> dict:
    """Check the current index against an accepted, artifact-pinned receipt.

    Relative receipt paths are relative to the repository root. An artifact
    root must be explicit for substantive changes. No-staged/state-only results
    can proceed operationally but are explicitly not consumption-qualified.
    In-repo receipt paths must be .json artifacts under workflow/receipts/ or
    consumer/receipts/. A staged receipt is fully checked even when it is the
    only staged file; naming source code as a receipt cannot exempt that code.
    """
    try:
        root = _repository_root(Path(repo))
        receipt_file = Path(receipt_path) if receipt_path is not None else None
        if receipt_file is not None:
            if not receipt_file.is_absolute():
                receipt_file = root / receipt_file
            receipt_file = receipt_file.resolve()
        exclusions: tuple[str, ...] = ()
        if receipt_file is not None:
            try:
                exclusions = (receipt_file.relative_to(root).as_posix(),)
            except ValueError:
                pass
        binding = staged_binding(root, exclusions)
    except (GitInspectionError, OSError, ValueError) as exc:
        return _result("blocked", False, [str(exc)])

    staged_receipt = bool(exclusions and exclusions[0] in binding["excluded_files"])
    if not binding["files"] and not staged_receipt:
        try:
            if staged_binding(root, exclusions) != binding:
                return _result("blocked", False, ["Staged index changed during gate check"], binding)
        except GitInspectionError as exc:
            return _result("blocked", False, [str(exc)], binding)
        status = "no_material_changes" if binding["excluded_files"] else "no_staged_changes"
        return _result(status, True, [], binding)

    errors = []
    for name, value in (("task_id", task_id), ("actor_id", actor_id), ("session_id", session_id)):
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{name} is required for substantive staged changes")
    if artifact_root is None:
        errors.append("artifact_root is required for substantive staged changes")
    if receipt_file is None:
        errors.append("An accepted consumption receipt is required for substantive staged changes")
    if errors:
        return _result("blocked", False, errors, binding)

    try:
        with receipt_file.open("rb") as stream:
            raw = stream.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("Consumption receipt exceeds 1 MiB")
        receipt = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return _result("blocked", False, [f"Cannot read consumption receipt: {exc}"], binding)
    if not isinstance(receipt, dict):
        return _result("blocked", False, ["Consumption receipt must be a JSON object"], binding)

    change_binding = receipt.get("change_binding")
    if not isinstance(change_binding, dict):
        errors.append("Receipt change_binding is required")
    else:
        for field in ("repository_head", "staged_diff_sha256"):
            if change_binding.get(field) != binding[field]:
                errors.append(f"Receipt change_binding.{field} does not match the current staged change")
    try:
        errors.extend(validate_receipt(
            receipt, Path(artifact_root), task_id=task_id, actor_id=actor_id, session_id=session_id
        ))
    except Exception as exc:
        errors.append(f"Receipt validation could not complete: {exc}")

    # Validation can take time and reads external artifacts. Detect an index or
    # HEAD change before returning permission for the inspected snapshot.
    try:
        if staged_binding(root, exclusions) != binding:
            errors.append("Staged index or repository HEAD changed during receipt validation")
        if staged_receipt:
            staged_raw = _git(root, ["cat-file", "blob", f":{exclusions[0]}"]).stdout
            if staged_raw != raw:
                errors.append("Staged receipt bytes differ from the receipt that was validated")
    except GitInspectionError as exc:
        errors.append(str(exc))
    status = "blocked" if errors else ("accepted" if binding["files"] else "no_material_changes")
    return _result(status, not errors, errors, binding)
