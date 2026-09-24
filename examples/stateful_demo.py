"""Extend the existing private demo with persisted task use, correction and recovery."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


LIMIT_SENTENCES = (
    "This does not prove semantic truth, automatic claim extraction, clean-machine recovery, or public release readiness.",
    "Synthetic claims are manually annotated.",
    "Recovery is a same-host Python guard.",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def immutable_output_refusal(output, task):
    """Refuse a launch that would write the accepted packet or a verifier decision."""
    output = Path(os.path.abspath(output))
    if output.parent.exists():
        output = output.parent.resolve() / output.name
    task = task.resolve()
    packet = task.parent
    if packet.name == "CE-STATEFUL-001-v1" and (output == task or output == packet or packet in output.parents):
        return "refusing to write inside the immutable CE-STATEFUL-001 task packet"
    if output.name.startswith("CE-STATEFUL-001-v1-verifier-decision"):
        return "refusing to overwrite a CE-STATEFUL-001 verifier decision"
    return ""


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8") as stream:
        json.dump(obj, stream, indent=2, sort_keys=True)
        stream.write("\n")


def query(root, label, snapshot=None):
    from replay import invoke
    args = ["lookup", "--provider", "historylab", "--root", str(root / "cases" / "initial"),
            "--query", "batch imports retry limit"]
    if snapshot:
        args += ["--snapshot", snapshot]
    response, execution = invoke(root, args)
    relative = "task-results/" + label + "-lookup.json"
    write(root / relative, response)
    write(root / "task-results" / (label + "-execution.json"), execution)
    return relative, response


def apply(root, label, expected, lookup, response, actor, session):
    from replay import apply_policy, configuration_checks
    from consumption_engine.task_history import record_checked
    config = apply_policy(response["native"], "batch imports retry limit")
    if config is None:
        raise ValueError("refused unusable context")
    output = "task-results/" + label + "-configuration.json"
    check = "task-results/" + label + "-check.json"
    write(root / output, config)
    checks = configuration_checks(config, response["native"]["claims"], expected)
    write(root / check, {"passed": all(checks.values()), "checks": checks,
        "output_sha256": sha(root / output), "method": "fixture configuration_checks; expected value from frozen rubric",
        "independent_acceptance": False})
    return record_checked(root, task="synthetic-importer", actor=actor, session=session,
                          lookup=lookup, output=output, check=check)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def render_report(output, result, checks, archive_sha, restored_count):
    """Buyer-facing report from the files this launch just wrote."""
    state = output / "source-state-unavailable"
    history = [_load(state / "task-history" / f"{index:06d}.json") for index in range(1, 7)]
    initial, stale, successor, current = history[0], history[3], history[4], history[5]
    initial_lookup = _load(state / initial["lookup"]["path"])
    successor_lookup = _load(state / successor["lookup"]["path"])
    initial_output = _load(state / initial["output"]["path"])
    successor_output = _load(state / successor["output"]["path"])
    correction = _load(state / "task-results" / "correction.json")
    old_lookup = _load(state / "task-results" / "old-snapshot-lookup.json")
    restore_check = _load(output / "restored" / "restore-check.json")["checks"]
    record = correction["record"]
    original = record["original_claim"]
    question = initial_lookup["native"]["query"]

    def evidence(title, record_row, lookup, config):
        claim = lookup["native"]["claims"][0]
        return [
            f"## {title}",
            "",
            f"- Claim: `{claim['item_id']}`.",
            f"- Statement: {claim['claim_text']}",
            f"- Source path: `{config['source']}`.",
            f"- Source SHA-256: `{config['source_sha256']}`.",
            f"- Scope: {config['scope']}.",
            f"- Lookup SHA-256: `{record_row['lookup']['sha256']}`.",
            f"- Output SHA-256: `{record_row['output']['sha256']}`.",
            f"- Check SHA-256: `{record_row['check']['sha256']}`.",
            "",
        ]

    lines = [
        f"# Checked use: {question}",
        "",
        f"Question: {question}",
        "",
        *evidence("Initial evidence", initial, initial_lookup, initial_output),
        "## Correction",
        "",
        "- Path: provider withdrawal (`retract_claim`) on the same fixture.",
        f"- Status: `{correction['status']}`.",
        f"- Retracted claim: `{record['retracted_item_id']}`.",
        f"- Original statement retained: {original['claim_text']}",
        f"- Original source retained: `{original['source_path']}`.",
        f"- Original source SHA-256: `{original['source_hash']}`.",
        f"- Superseded by: `{record['superseded_by']}`.",
        f"- Old task state: `{stale['state']}`.",
        f"- Stale reasons: {', '.join(stale['reasons'])}.",
        f"- Old snapshot reuse: `{old_lookup['native']['status']}`.",
        "",
        *evidence("Successor evidence", successor, successor_lookup, successor_output),
        "## Restore",
        "",
        f"- Archive SHA-256: `{archive_sha}`.",
        f"- Manifest files restored: `{restored_count}`.",
        f"- History records: `{len(history)}`.",
        f"- Successor state: `{current['state']}`.",
        f"- Original-source read denied: `{restore_check['original_folder_read_denied']}`.",
        f"- Cache read denied: `{restore_check['workstation_cache_read_denied']}`.",
        f"- Network denied: `{restore_check['network_denied']}`.",
        f"- Author checks passed: `{result['passed']}`.",
        f"- Initial task stale after correction: `{checks['old_work_stale_after_real_correction']}`.",
        f"- Corrected task current: `{checks['corrected_work_current']}`.",
        "",
        "## Limits",
        "",
        *LIMIT_SENTENCES,
        "",
    ]
    return "\n".join(lines)


def verify_restored(root, forbidden, cache):
    import sitecustomize
    if not sitecustomize.ACTIVE:
        raise ValueError("restore verification requires active guard")
    from consumption_engine.task_history import assess, read_history
    manifest = json.loads((root / "bundle-manifest.json").read_bytes())
    checks = {"preserved:" + row["path"]: sha(root / row["path"]) == row["sha256"] for row in manifest}
    history = read_history(root)
    checked = [r for r in history if r["event"] == "checked"]
    checks["two_completed_task_versions_restored"] = len(checked) == 2
    checks["stale_event_restored"] = any(r.get("state") == "stale" for r in history)
    lookup, response = query(root, "restored")
    checks["old_task_still_stale"] = assess(root, checked[0], lookup)["state"] == "stale"
    checks["corrected_task_still_current"] = assess(root, checked[-1], lookup)["state"] == "checked_current"
    checks["updated_context"] = response["native"]["claims"][0]["item_id"] == "retry-policy-v2"
    if cache is None or not cache.is_file():
        raise ValueError("restore verification requires the written workstation cache")
    for label, target in (("original_folder_read_denied", forbidden),
                          ("workstation_cache_read_denied", cache)):
        try:
            target.read_bytes()
            checks[label] = False
        except PermissionError:
            checks[label] = True
    import socket
    try:
        socket.socket()
        checks["network_denied"] = False
    except PermissionError:
        checks["network_denied"] = True
    write(root / "restore-check.json", {"passed": all(checks.values()), "checks": checks,
        "scope": "guarded fresh Python process on same host/interpreter, not OS isolation or cross-machine qualification"})
    print(json.dumps({"passed": all(checks.values()), "checks": len(checks)}))
    return 0 if all(checks.values()) else 1


def run(args):
    from run_demo import prepare, make_claim, seal_archive, restore_archive
    from consumption_engine.task_history import append, record_assessment, assess, read_history
    start = time.perf_counter()
    task = json.loads(args.task.read_text(encoding="utf-8-sig"))
    for pin in task["inputs"]:
        pin_path = Path(pin["path"])
        if not pin_path.is_absolute():
            pin_path = (args.task.parent / pin_path).resolve()
        if sha(pin_path) != pin["sha256"]:
            raise ValueError("frozen input changed: " + str(pin_path))
    output = Path(os.path.abspath(args.output))
    refusal = immutable_output_refusal(output, args.task)
    if refusal:
        print(json.dumps({"refused": True, "reason": refusal}))
        return 2
    output.mkdir(parents=True, exist_ok=False)
    root = output / "state"
    prepare(root, args.engine_root.resolve(), args.provider_root.resolve())
    for folder in ("guard-logs", "temp"):
        (root / folder).mkdir()
    shutil.copy2(args.engine_root / "consumption_engine/task_history.py", root / "runtime/engine/consumption_engine/task_history.py")
    shutil.copy2(Path(__file__), root / "client/stateful_demo.py")
    write(root / "task-input-manifest.json", task)
    write(output / "workstation-cache.json", {"forbidden": "not an input to restored work"})
    lookup1, response1 = query(root, "initial")
    old = apply(root, "initial", 3, lookup1, response1, task["writer"], "01a0d09b-36bd-7f62-a0bb-76ec85255c29")
    initial_ready = record_assessment(root, old, lookup1)
    fixture = root / "cases/initial"
    claims_path = fixture / "consumer/claims/claims.jsonl"
    original_claims = claims_path.read_bytes()
    fixtures = json.loads((root / "fixtures.json").read_bytes())
    docs, annotations = fixtures["documents"], fixtures["annotations"]
    (fixture / "sources/policy-v2.md").write_bytes(docs["policy-v2.md"].encode())
    v2 = make_claim("retry-policy-v2", "policy-v2.md", annotations["v2_span"], docs,
                    supersedes=["retry-policy-v1"], correction_links=[{"item_id": "retry-policy-v1", "relation": "supersedes"}])
    with claims_path.open("ab") as stream:
        stream.write((json.dumps(v2, sort_keys=True) + "\n").encode())
    # Mutate only this caller-owned fixture, through the accepted provider API.
    sys.path.insert(0, str(fixture / "consumer"))
    spec = importlib.util.spec_from_file_location("stateful_provider", fixture / "consumer/consumer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    correction = module.UltimateConsumer(root=fixture).retract_claim(
        "retry-policy-v1", "Synthetic version2 supersedes version1 for batch imports", "retry-policy-v2", author=task["writer"])
    write(root / "task-results/correction.json", correction)
    append(root, {"event": "correction", "artifact": "task-results/correction.json",
                  "sha256": sha(root / "task-results/correction.json"), "method": "provider retract_claim on same fixture"})
    lookup2, response2 = query(root, "corrected")
    stale = record_assessment(root, old, lookup2)
    stale_lookup, stale_response = query(root, "old-snapshot", response1["native"]["snapshot_version"])
    new = apply(root, "corrected", 2, lookup2, response2, task["writer"], "01a0d09b-36bd-7f62-a0bb-76ec85255c29")
    ready = record_assessment(root, new, lookup2)
    checks = {"initial_current": initial_ready["state"] == "checked_current",
        "old_work_stale_after_real_correction": stale["state"] == "stale",
        "old_snapshot_refused": stale_response["native"]["status"] == "unavailable",
        "corrected_work_current": ready["state"] == "checked_current",
        "original_claim_bytes_preserved": claims_path.read_bytes().startswith(original_claims),
        "original_task_output_preserved": sha(root / old["output"]["path"]) == old["output"]["sha256"],
        "original_source_preserved": (fixture / "sources/policy-v1.md").read_bytes() == docs["policy-v1.md"].encode(),
        "history_contains_actual_correction": len(read_history(root)) == 6}
    write(root / "task-results/lifecycle-check.json", {"passed": all(checks.values()), "checks": checks})
    if not all(checks.values()):
        raise ValueError("lifecycle check failed; retained outputs show failures")
    # Archive completed work, not just prepared fixtures. No replay regenerates history.
    archive = output / "completed-work.zip"
    archive_sha = seal_archive(root, archive)
    unavailable = output / "source-state-unavailable"
    if root.resolve().parent != output:
        raise ValueError("generated state is outside output")
    root.rename(unavailable)
    restored = output / "restored"
    restored_count = restore_archive(archive, restored, archive_sha)
    from replay import child_env
    cache = output / "workstation-cache.json"
    command = [sys.executable, "-B", str(restored / "client/stateful_demo.py"),
               "--verify-restored", str(restored), "--forbidden", str(unavailable / old["output"]["path"]),
               "--forbidden-cache", str(cache)]
    executed = subprocess.run(command, cwd=restored, env=child_env(restored), capture_output=True, text=True, timeout=120)
    write(output / "restore-execution.json", {"command": command, "exit_code": executed.returncode,
                                             "stdout": executed.stdout, "stderr": executed.stderr})
    result = {"passed": executed.returncode == 0, "archive_sha256": archive_sha, "restored_files": restored_count,
        "lifecycle_checks": checks, "execution_seconds": time.perf_counter() - start,
        "manual_preparation_and_review_cost": "not measured by runner; session work separately recorded",
        "review_status": "awaiting independent review", "source_root_unavailable": not root.exists(),
        "code": {"runner": sha(Path(__file__)), "task_history": sha(args.engine_root / "consumption_engine/task_history.py")},
        "limitations": ["manually annotated synthetic policy", "same host/interpreter Python guard, not clean-machine proof",
                       "private runtime; no public distribution approval", "task history uses single writer; no authenticated acceptance"]}
    write(output / "RESULT.json", result)
    report = render_report(output, result, checks, archive_sha, restored_count)
    (output / "REPORT.md").write_text(report, encoding="utf8")
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-root", type=Path)
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--provider-root", type=Path)
    parser.add_argument("--task", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-restored", type=Path)
    parser.add_argument("--forbidden", type=Path)
    parser.add_argument("--forbidden-cache", type=Path)
    options = parser.parse_args()
    if options.verify_restored:
        if options.forbidden is None or options.forbidden_cache is None:
            parser.error("verify-restored requires --forbidden and --forbidden-cache")
        sys.path.insert(0, str(options.verify_restored / "runtime/engine"))
        raise SystemExit(verify_restored(options.verify_restored, options.forbidden, options.forbidden_cache))
    if not all((options.client_root, options.engine_root, options.provider_root, options.task, options.output)):
        parser.error("client-root, engine-root, provider-root, task and new output required")
    sys.path.insert(0, str(options.client_root.resolve()))
    sys.path.insert(0, str(options.engine_root.resolve()))
    raise SystemExit(run(options))
