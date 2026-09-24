"""Explicit, bounded command line for the shared consumption process."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def emit(value):
    print(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False))


def parse_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    if len(raw) > 1_048_576:
        raise ValueError("JSON artifact exceeds 1 MiB")
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def read_json(path):
    return parse_json(Path(path).read_bytes())


def lookup(args):
    """Delegate to inspected providers; preserve their native status and limits."""
    root = args.root.resolve(strict=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    if args.provider == "historylab":
        if not args.query or any((args.fixture, args.object_id, args.revision, args.view, args.manifest_sha256)):
            raise ValueError("historylab lookup requires query and does not support fixture/read flags")
        for relative in ("consumer/consumer.py", "consumer/claims/claims.jsonl",
                         "consumer/manifests", "consumer/wake_cards", "consumer/receipts"):
            if not (root / relative).exists():
                raise ValueError(f"existing HistoryLab dependency missing: {relative}")
        worker = (
            "import importlib.util,json,pathlib,sys; "
            "root=pathlib.Path(sys.argv[1]); "
            "sys.path.insert(0,str(root/'consumer')); "
            "spec=importlib.util.spec_from_file_location('historylab_provider',root/'consumer/consumer.py'); "
            "mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
            "result=mod.UltimateConsumer(root=root).evidence_envelope(sys.argv[2],expected_snapshot=sys.argv[3] or None); "
            "print(json.dumps(result,ensure_ascii=True,allow_nan=False))"
        )
        command = [sys.executable, "-B", "-c", worker, str(root), args.query, args.snapshot or ""]
        scope = "checked HistoryLab snapshot; no logging, learning or admission"
    else:
        if not args.fixture or not args.manifest_sha256:
            raise ValueError("thelibrary-fixture requires --fixture and independently pinned --manifest-sha256")
        fixture = args.fixture.resolve(strict=True)
        manifest = fixture / "THELIBRARY_FIXTURE_MANIFEST.json"
        expected = args.manifest_sha256.lower()
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("manifest SHA-256 must be 64 hexadecimal characters")
        before = hashlib.sha256(manifest.read_bytes()).hexdigest()
        if before != expected:
            raise ValueError("fixture manifest differs from pinned SHA-256")
        command = [sys.executable, "-B", str(root / "tools/library_engine.py"), "--fixture", str(fixture)]
        if args.object_id:
            if args.query or not all((args.revision, args.snapshot, args.view)):
                raise ValueError("fixture read requires id/revision/snapshot/view and no query")
            command += ["get", "--id", args.object_id, "--revision", args.revision,
                        "--snapshot", args.snapshot, "--view", args.view, "--budget", str(args.budget)]
        else:
            if not args.query or any((args.revision, args.snapshot, args.view)):
                raise ValueError("fixture discovery requires query, with no exact-read flags")
            command += ["search", "-q", args.query, "--budget", str(args.budget)]
        scope = "one exported TheLibrary chain; inspection only; current admission unavailable"
    run = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=60)
    if run.returncode:
        # Do not expose arbitrary provider stderr (which can contain host-local data).
        raise ValueError(f"provider process failed with exit {run.returncode}; inspect it locally")
    if len(run.stdout) > 1_048_576:
        raise ValueError("provider response exceeds 1 MiB")
    native = parse_json(run.stdout)
    if not isinstance(native, dict):
        raise ValueError("provider did not return an object")
    if args.provider == "historylab":
        if native.get("schema_version") != "historylab-evidence-v1":
            raise ValueError("unsupported HistoryLab response schema")
        status = native.get("status")
        if not isinstance(status, str) or status not in {"answered", "ambiguous", "empty", "unavailable"}:
            raise ValueError("unsupported HistoryLab status")
    else:
        if hashlib.sha256(manifest.read_bytes()).hexdigest() != expected:
            raise ValueError("fixture changed during provider read")
        if native.get("contract") != "ssr-consume-read-v1":
            raise ValueError("unsupported TheLibrary response contract")
        status = native.get("outcome")
        if not isinstance(status, str) or status not in {"OK", "UNKNOWN", "INVALID_REQUEST", "CONFLICT", "STALE_SNAPSHOT", "WITHHELD", "INSUFFICIENT_BUDGET"}:
            raise ValueError("unsupported TheLibrary outcome")
    result = {"schema_version": "consumption-lookup-v1", "stage": "retrieved",
              "provider": args.provider, "native_status": status, "scope": scope,
              "accepted_use": False, "native": native}
    if args.provider == "thelibrary-fixture":
        result["manifest_sha256"] = expected
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode()
    if args.output:
        # Explicit caller-selected artifact, not a new database or mirror.
        with args.output.open("xb") as output:
            output.write(raw)
    emit(result)
    return 0  # A structured refusal is a successful lookup, never accepted evidence.


def main(argv=None):
    parser = argparse.ArgumentParser(description="Retrieve, apply, check and record bounded evidence use")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    p = sub.add_parser("packet-check", help="Read-only V0 envelope/direct-file integrity, not acceptance")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--packet", required=True, help="root-relative POSIX path")
    p.add_argument("--sha256", required=True, help="independently pinned whole-file SHA-256")
    p = sub.add_parser("lookup")
    p.add_argument("--provider", required=True, choices=["historylab", "thelibrary-fixture"])
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--query")
    p.add_argument("--fixture", type=Path)
    p.add_argument("--manifest-sha256")
    p.add_argument("--object-id")
    p.add_argument("--revision")
    p.add_argument("--snapshot")
    p.add_argument("--view", choices=["inventory", "evidence", "source", "artifact"])
    p.add_argument("--budget", type=int, default=1500)
    p.add_argument("--output", type=Path)
    for name in ("check", "gate"):
        p = sub.add_parser(name)
        p.add_argument("--receipt", type=Path)
        p.add_argument("--artifact-root", type=Path)
        p.add_argument("--task", default=os.environ.get("CONSUMPTION_TASK_ID"))
        p.add_argument("--actor", default=os.environ.get("CONSUMPTION_ACTOR_ID"))
        p.add_argument("--session", default=os.environ.get("CONSUMPTION_SESSION_ID"))
        if name == "gate":
            p.add_argument("--repo", type=Path, required=True)
    p = sub.add_parser("binding")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--exclude-receipt", default=None)
    args = parser.parse_args(argv)
    try:
        if args.command == "describe":
            emit({"version": "0.1.0", "process": ["retrieve", "apply", "check", "accept"],
                  "providers": {"historylab": "checked current-request snapshot",
                                "thelibrary-fixture": "pinned exported chain, inspection only"},
                  "receipt_schema": "consumption-use-v1", "storage": "caller-owned existing artifacts",
                  "limits": ["No agent rollout/identity authentication claimed", "No scientific truth or learning certification",
                             "No unified live TheLibrary admission adapter", "No source mutation, model call or automatic mirroring"]})
            return 0
        if args.command == "lookup":
            return lookup(args)
        if args.command == "packet-check":
            from .shared_packet import check_packet
            result = check_packet(args.root, args.packet, args.sha256)
            emit(result)
            return 0 if result["integrity"] == "direct_files_match" else 1
        if args.command == "binding":
            from .git_gate import staged_binding
            emit(staged_binding(args.repo, exclude_paths=[args.exclude_receipt] if args.exclude_receipt else []))
            return 0
        if args.command == "gate":
            from .git_gate import gate
            result = gate(args.repo, args.receipt, args.artifact_root, task_id=args.task,
                          actor_id=args.actor, session_id=args.session)
            emit(result)
            return 0 if result["allowed"] else 1
        from .receipt import validate_receipt
        if not args.receipt or not args.artifact_root or not all((args.task, args.actor, args.session)):
            raise ValueError("check requires receipt, artifact-root, task, actor and session")
        errors = validate_receipt(read_json(args.receipt), args.artifact_root, task_id=args.task,
                                  actor_id=args.actor, session_id=args.session)
        emit({"valid": not errors, "errors": errors, "scope": "local process and artifact identity; not authenticated acceptance or truth"})
        return 1 if errors else 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        emit({"status": "error", "error": str(exc), "accepted_use": False})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
