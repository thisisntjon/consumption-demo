"""Prepare, run, compare and restore one caller-owned synthetic demonstration."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile

from replay import digest, read_json, stable, write_json

HERE = Path(__file__).resolve().parent
PROVIDER_FILES = ["consumer.py", "epistemic.py", "claim_v2.py", "library_card.py"]
ENGINE_FILES = ["engine.py", "consumption_engine/__init__.py", "consumption_engine/__main__.py",
                "consumption_engine/receipt.py", "consumption_engine/git_gate.py", "consumption_engine/shared_packet.py"]
CLIENT_FILES = ["replay.py", "sitecustomize.py", "guarded_lookup.py"]


def copy_pinned(source, target):
    raw = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {"path": str(source), "sha256": digest(raw), "bytes": len(raw)}


def make_claim(item, path, span, documents, **extra):
    return {"item_id": item, "claim_text": span, "source_path": "sources/" + path,
            "source_hash": digest(documents[path].encode("utf-8")), "evidence_span": span,
            "falsifier": "Inspect the declared synthetic original, version, scope and correction record.",
            "epistemic_class": "reported", "lifecycle": "KEEP", "license_class": "public-domain",
            "source_role": "primary", "support_assessment": "not_assessed",
            "usable_as_constraint": False, "annotation_method": "manual synthetic fixture",
            "created_at": "2026-01-01T00:00:00Z", **extra}


def prepare(root, engine, provider):
    fixtures = read_json(HERE / "fixtures.json")
    docs, annotations = fixtures["documents"], fixtures["annotations"]
    root.mkdir()
    dependencies = []
    for name in ENGINE_FILES:
        dependencies.append(copy_pinned(engine / name, root / "runtime" / "engine" / name))
    for name in CLIENT_FILES:
        copy_pinned(HERE / name, root / "client" / name)
    for name in ("fixtures.json", "rubric.json"):
        copy_pinned(HERE / name, root / name)
    for name, text in docs.items():
        path = root / "originals" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    groups = {}
    for name, text in docs.items():
        groups.setdefault(digest(text.encode("utf-8")), []).append(name)
    write_json(root / "source-manifest.json", {
        "sources": [{"path": "originals/" + name, "sha256": digest(text.encode("utf-8")),
                     "bytes": len(text.encode("utf-8")), "acquisition": "owned synthetic fixture",
                     "rights": fixtures["rights"]} for name, text in docs.items()],
        "exact_copy_groups": list(groups.values()),
        "independence_of_different_hashes": "not assessed"})
    v1 = make_claim("retry-policy-v1", "policy-v1.md", annotations["v1_span"], docs)
    v2 = make_claim("retry-policy-v2", "policy-v2.md", annotations["v2_span"], docs,
                    supersedes=["retry-policy-v1"], correction_links=[{"item_id": "retry-policy-v1", "relation": "supersedes"}])
    conflict = make_claim("retry-policy-conflict", "conflicting-policy.md", annotations["conflict_span"], docs,
                         conflicts_with=["retry-policy-v2"])
    failure = make_claim("recovery-failure", "failed-restore.md", annotations["failure_span"], docs,
                        negative="Synthetic failed approach. No product failure-frequency claim.")
    correction = {"retracted_item_id": "retry-policy-v1", "superseded_by": "retry-policy-v2",
                  "reason": "Manually recorded policy version 2 replaces version 1 for batch imports.",
                  "retracted_at": "2026-02-01T00:00:00Z"}
    cases = {}
    for case in read_json(root / "rubric.json")["cases"]:
        case_root = root / "cases" / case
        for directory in ("consumer/claims", "consumer/manifests", "consumer/wake_cards", "consumer/receipts", "sources"):
            (case_root / directory).mkdir(parents=True, exist_ok=True)
        for directory in ("consumer/manifests", "consumer/wake_cards", "consumer/receipts"):
            (case_root / directory / ".keep").write_bytes(b"Required empty fixture directory.\n")
        for name in PROVIDER_FILES:
            pin = copy_pinned(provider / "consumer" / name, case_root / "consumer" / name)
            if case == "initial":
                dependencies.append(pin)
        available = ["policy-v1.md", "policy-v1-copy.md", "failed-restore.md"]
        claims, withdrawals, active = [v1, failure], [], list(available)
        if case != "initial":
            available += ["policy-v2.md"]
            claims, withdrawals, active = [v1, v2, failure], [correction], ["policy-v2.md", "failed-restore.md"]
        if case == "conflicting":
            available += ["conflicting-policy.md"]
            active += ["conflicting-policy.md"]
            claims = [v1, dict(v2, conflicts_with=["retry-policy-conflict"]), conflict, failure]
        if case == "withdrawn":
            withdrawals = [correction, {"retracted_item_id": "retry-policy-v2", "superseded_by": "",
                            "reason": "Synthetic withdrawal without replacement.", "retracted_at": "2026-03-01T00:00:00Z"}]
            active = ["failed-restore.md"]
        for name in available:
            if case == "missing" and name == "policy-v2.md":
                continue
            text = docs[name]
            if case == "tampered" and name == "policy-v2.md":
                text = text.replace("up to 2 times", "up to 9 times")
            (case_root / "sources" / name).write_bytes(text.encode("utf-8"))
        for name, rows in (("claims", claims), ("retractions", withdrawals)):
            (case_root / "consumer" / "claims" / (name + ".jsonl")).write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        cases[case] = {"question": case if case in {"unsupported", "failure"} else "policy",
                       "available_documents": available, "active_documents": active}
    write_json(root / "case-specs.json", cases)
    write_json(root / "private-dependency-pins.json", dependencies)
    return dependencies


def seal_archive(root, archive):
    manifest = [{"path": path.relative_to(root).as_posix(), "sha256": digest(path.read_bytes()),
                 "bytes": path.stat().st_size} for path in sorted(root.rglob("*")) if path.is_file()]
    write_json(root / "bundle-manifest.json", manifest)
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(root).as_posix())
    return digest(archive.read_bytes())


def restore_archive(archive, target, expected_hash):
    if digest(archive.read_bytes()) != expected_hash:
        raise ValueError("archive differs from independently retained SHA-256")
    if target.exists():
        raise FileExistsError(target)
    with zipfile.ZipFile(archive) as zipped:
        entries = zipped.infolist()
        seen = set()
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if (name.is_absolute() or ".." in name.parts or "\\" in entry.filename
                    or ":" in entry.filename or entry.is_dir()
                    or entry.filename.casefold() in seen
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("unsafe or duplicate archive member")
            seen.add(entry.filename.casefold())
        manifest = json.loads(zipped.read("bundle-manifest.json"))
        if {m["path"] for m in manifest} != {e.filename for e in entries} - {"bundle-manifest.json"}:
            raise ValueError("archive inventory differs from manifest")
        for item in manifest:
            raw = zipped.read(item["path"])
            if len(raw) != item["bytes"] or digest(raw) != item["sha256"]:
                raise ValueError("archive content differs from manifest")
        target.mkdir()
        for entry in entries:
            path = target / entry.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zipped.read(entry))
    return len(manifest)


def execute(root):
    command = [sys.executable, "-I", "-B", str(root / "client" / "replay.py"), str(root)]
    env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "COMSPEC") if k in os.environ}
    completed = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=180)
    if not (root / "results" / "checks.json").exists():
        raise RuntimeError(completed.stderr + completed.stdout)
    return read_json(root / "results" / "checks.json"), {
        "command": command, "exit_code": completed.returncode,
        "stdout": completed.stdout, "stderr": completed.stderr}


def report(output, initial, restored, verification):
    lines = ["# Consumption Engine synthetic demonstration", "",
             "Local integration result. Private runtime dependencies; not a public release.", "",
             "## Executed cases", "",
             "| Case | Provider result | Configuration retry limit | Checks |", "|---|---|---:|---|"]
    for name, case in restored["cases"].items():
        value = (case["configuration"] or {}).get("batch_import_retry_limit", "No configuration")
        lines.append(f"| {name} | {case['native']['status']} | {value} | {'PASS' if all(case['checks'].values()) else 'FAIL'} |")
    lines += ["", "## Retrieval comparison", "",
              "Same synthetic documents. BM25 returns passages, not answers. The metadata variant receives the same manually supplied lifecycle and copy information used to prepare the engine input.", "",
              "| Case | Raw ranked documents | Metadata-filtered documents | Raw exact-copy excess | Raw inactive documents |",
              "|---|---:|---:|---:|---:|"]
    for name in ("initial", "corrected", "conflicting", "unsupported", "withdrawn", "tampered", "missing"):
        case = restored["cases"][name]
        lines.append(f"| {name} | {len(case['baseline_raw'])} | {len(case['baseline_metadata'])} | {case['raw_duplicate_candidates']} | {case['raw_inactive_candidates']} |")
    lines += ["", "The metadata baseline can remove known copies and superseded documents too. The engine additionally returns its explicit status, source identity, passage checks and correction record. The baseline has no integrity validator. These observations do not establish superiority over vector RAG, Graphiti or another configured product.",
              "", "## Preservation and replay", "",
              f"- Archive SHA-256: `{verification['archive_sha256']}`.",
              f"- Manifest entries restored: {verification['restored_files']}.",
              f"- Fresh replay matches original statuses, claims, snapshots and evidence: {verification['equivalent_replay']}.",
              f"- Original generated data location unavailable during replay: {verification['original_location_unavailable']}.",
              f"- Original tool/provider source files unchanged: {verification['dependencies_unchanged']}.",
              f"- All checks passed: {verification['passed']}.", "",
              "Each lookup ran with Python read restrictions and socket denial. This qualifies only this text-only Python fixture on this machine and installed interpreter. It is not OS-level air-gap or different-machine recovery qualification. The top-level report coordinator is trusted; the actual lookup processes carry the read/network guards.",
              "", "## Interpretation", "",
              "Manual annotations define claims, policy scope, authority, corrections and conflicts. The client calculates exact-copy groups, but the fixture author supplies one claim for the original and its copy. This does not demonstrate automated deduplicated admission. Archive/replay is a demonstration-client addition. The provider's hash/span checks do not assess semantic entailment. The configuration parser handles only this fixture's exact sentence form. No LLM was called; token savings, answer accuracy, general contradiction detection and reduction in repeated failures were not measured.",
              "", "Failure retrieval shows a recorded failed approach is accessible. It does not prove an agent avoids repeating it. Human annotation/review time, customer value and delivery cost are unmeasured. A separate reviewer must inspect the pinned code and outputs before acceptance.",
              "", "See `source-state-unavailable/results/` for the first run and `restored/results/` for the fresh replay. Raw results retain full provider qualifications and command records. `verification.json` records the exact client, fixture and rubric identities."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--provider-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source-state"
    pins = prepare(source, args.engine_root.resolve(strict=True), args.provider_root.resolve(strict=True))
    archive = output / "recovery.zip"
    archive_hash = seal_archive(source, archive)
    initial, first_execution = execute(source)
    # Rename only the exact generated fixture directory beneath this new output.
    if source.parent != output or source.resolve().parent != output:
        raise ValueError("refusing to move a path outside the generated output")
    source.rename(output / "source-state-unavailable")
    restored_root = output / "restored"
    restored_count = restore_archive(archive, restored_root, archive_hash)
    restored, second_execution = execute(restored_root)
    equivalence = {name: stable(initial["cases"][name]["native"]) == stable(restored["cases"][name]["native"])
                   and initial["cases"][name]["configuration"] == restored["cases"][name]["configuration"]
                   for name in initial["cases"]}
    manifest = read_json(restored_root / "source-manifest.json")
    originals_match = all(digest((restored_root / m["path"]).read_bytes()) == m["sha256"] for m in manifest["sources"])
    unchanged = all(digest(Path(pin["path"]).read_bytes()) == pin["sha256"] for pin in pins)
    verification = {"archive_sha256": archive_hash, "restored_files": restored_count,
        "case_equivalence": equivalence, "equivalent_replay": all(equivalence.values()),
        "original_location_unavailable": not source.exists(), "originals_match": originals_match,
        "dependencies_unchanged": unchanged, "initial_execution": first_execution,
        "restored_execution": second_execution, "client_pins": {
            p.name: digest(p.read_bytes()) for p in HERE.iterdir() if p.is_file()},
        "passed": initial["passed"] and restored["passed"] and all(equivalence.values()) and originals_match and unchanged
                  and first_execution["exit_code"] == 0 and second_execution["exit_code"] == 0,
        "review_status": "awaiting separate review"}
    write_json(output / "verification.json", verification)
    report(output, initial, restored, verification)
    print(json.dumps({"passed": verification["passed"], "report": str(output / "REPORT.md")}))
    return 0 if verification["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
