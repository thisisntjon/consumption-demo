"""Deterministic client, baselines and rubric checks for the synthetic bundle."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def rank_documents(documents, query):
    """BM25, k1=1.5, b=0.75. Stable path tie-breaking; return all positive hits."""
    counts = {name: Counter(tokens(text)) for name, text in documents.items()}
    n = len(counts)
    average = sum(sum(c.values()) for c in counts.values()) / max(n, 1)
    rows = []
    for name, count in counts.items():
        score = 0.0
        for term in set(tokens(query)):
            frequency = count[term]
            if not frequency:
                continue
            df = sum(term in c for c in counts.values())
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            score += idf * frequency * 2.5 / (frequency + 1.5 * (
                0.25 + 0.75 * sum(count.values()) / average))
        if score:
            rows.append({"path": name, "score": round(score, 6), "text": documents[name]})
    return sorted(rows, key=lambda row: (-row["score"], row["path"]))


def apply_policy(native, query):
    """Restricted fixture application, not a general entailment or agent policy."""
    if native["status"] != "answered" or query != "batch imports retry limit":
        return None
    claims = native.get("claims", [])
    if len(claims) != 1:
        return None
    span = claims[0]["evidence_span"]
    match = re.fullmatch(r"Batch imports may retry up to ([0-9]+) times\.", span)
    if not match:
        return None
    return {"batch_import_retry_limit": int(match.group(1)),
            "claim_id": claims[0]["item_id"], "source": claims[0]["source_path"],
            "source_sha256": claims[0]["source_hash_claimed"],
            "scope": "manually annotated synthetic batch-import policy only"}


def configuration_checks(config, claims, expected_limit):
    if expected_limit is None:
        return {"configuration_absent": config is None}
    if config is None or len(claims) != 1:
        return {"configuration_present": False}
    claim = claims[0]
    return {"configuration_value": config.get("batch_import_retry_limit") == expected_limit,
            "configuration_claim": config.get("claim_id") == claim["item_id"],
            "configuration_source": config.get("source") == claim["source_path"],
            "configuration_source_hash": config.get("source_sha256") == claim["source_hash_claimed"],
            "configuration_scope": config.get("scope") == "manually annotated synthetic batch-import policy only"}


def stable(value):
    """Exclude only request timestamp and relocated absolute source paths."""
    if isinstance(value, list):
        return [stable(v) for v in value]
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items()
                if k != "checked_at" and not (k == "path" and isinstance(v, str) and Path(v).is_absolute())}
    return value


def child_env(root):
    env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "COMSPEC") if k in os.environ}
    env.update(PYTHONPATH=str(root / "client"), PYTHONNOUSERSITE="1", PYTHONUTF8="1",
               PYTHONDONTWRITEBYTECODE="1", CE_DEMO_ROOT=str(root),
               TEMP=str(root / "temp"), TMP=str(root / "temp"))
    return env


def invoke(root, argv):
    command = [sys.executable, "-B", str(root / "client" / "guarded_lookup.py"), str(root), *argv]
    start = time.perf_counter()
    completed = subprocess.run(command, cwd=root, env=child_env(root), capture_output=True,
                               text=True, encoding="utf-8", timeout=30)
    if completed.returncode:
        raise RuntimeError(f"lookup failed ({completed.returncode}): {completed.stderr} {completed.stdout}")
    return json.loads(completed.stdout), {
        "command": command, "exit_code": completed.returncode,
        "elapsed_seconds": round(time.perf_counter() - start, 6), "stderr": completed.stderr}


def check_case(case, native, config, expected, root):
    checks = {
        "status": native["status"] == expected["status"],
        "claim_ids": sorted(c["item_id"] for c in native["claims"]) == sorted(expected["ids"]),
        "no_truth_claim": native["declares_truth"] is False and native["usable_as_constraint"] is False,
    }
    checks.update(configuration_checks(config, native["claims"], expected["retry_limit"]))
    if "reason" in expected:
        checks["refusal_reason"] = native.get("reason") == expected["reason"]
    for claim in native["claims"]:
        source = root / "cases" / case / claim["source_path"]
        raw = source.read_bytes()
        checks[claim["item_id"] + ":hash"] = digest(raw) == claim["source_hash_claimed"]
        checks[claim["item_id"] + ":passage"] = claim["evidence_span"] in raw.decode("utf-8")
    if case == "corrected" and native["claims"]:
        events = native["claims"][0]["history"]["events"]
        checks["correction_history"] = any(e.get("retracted_item_id") == "retry-policy-v1" for e in events)
    if case == "conflicting":
        checks["conflict_retained"] = all(c["conflicts"]["conflicts"] for c in native["claims"])
    return checks


def run(root):
    root = root.resolve(strict=True)
    rubric = read_json(root / "rubric.json")
    specs = read_json(root / "case-specs.json")
    (root / "guard-logs").mkdir(exist_ok=True)
    (root / "temp").mkdir(exist_ok=True)
    results, all_checks = {}, {}
    for case, expected in rubric["cases"].items():
        spec = specs[case]
        query = rubric["questions"][spec["question"]]
        argv = ["lookup", "--provider", "historylab", "--root", str(root / "cases" / case), "--query", query]
        if case == "stale_snapshot":
            argv.extend(["--snapshot", results["initial"]["native"]["snapshot_version"]])
        response, execution = invoke(root, argv)
        native = response["native"]
        config = apply_policy(native, query)
        config_path = root / "results" / (case + "-importer-config.json")
        if config is not None:
            write_json(config_path, config)
        checks = check_case(case, native, config, expected, root)
        if config is not None:
            saved = read_json(config_path)
            checks["saved_configuration_matches"] = saved == config
            checks.update({"saved_" + key: value for key, value in
                           configuration_checks(saved, native["claims"], expected["retry_limit"]).items()})
        else:
            checks["no_saved_configuration"] = not config_path.exists()
        documents = {name: (root / "cases" / case / "sources" / name).read_text(encoding="utf-8")
                     for name in spec["available_documents"]
                     if (root / "cases" / case / "sources" / name).exists()}
        raw_rank = rank_documents(documents, query)
        # Both baselines receive identical originals. The second also receives the
        # same manual lifecycle metadata used to prepare the provider's claims.
        eligible, seen = {}, set()
        for name in spec["active_documents"]:
            if name not in documents:
                continue
            identity = digest(documents[name].encode("utf-8"))
            if identity not in seen:
                seen.add(identity)
                eligible[name] = documents[name]
        metadata_rank = rank_documents(eligible, query)
        hashes = [digest(row["text"].encode("utf-8")) for row in raw_rank]
        result = {"query": query, "native": native, "configuration": config, "checks": checks,
                  "configuration_file_sha256": digest(config_path.read_bytes()) if config is not None else None,
                  "execution": execution, "baseline_raw": raw_rank, "baseline_metadata": metadata_rank,
                  "raw_duplicate_candidates": len(hashes) - len(set(hashes)),
                  "raw_inactive_candidates": sum(r["path"] not in spec["active_documents"] for r in raw_rank)}
        results[case] = result
        all_checks.update({case + ":" + key: value for key, value in checks.items()})
        write_json(root / "results" / (case + ".json"), result)
    probe, _ = invoke(root, ["probe", str(root.parent / "outside-read-probe.txt")])
    all_checks.update(probe)
    logs = [read_json(p) for p in (root / "guard-logs").glob("*.json")]
    all_checks["guard_process_count"] = len(logs) == 2 * len(rubric["cases"]) + 1
    all_checks["guard_active"] = all(log["active"] for log in logs)
    unexpected_denials = [d for log in logs for d in log["denied"]
                         if not (d["event"].startswith("socket.") or d.get("path", "").endswith("outside-read-probe.txt"))]
    all_checks["no_unexpected_guard_denials"] = not unexpected_denials
    summary = {"checks": all_checks, "passed": all(all_checks.values()), "cases": results,
               "guard_processes": len(logs), "python": sys.version, "python_executable": sys.executable,
               "python_executable_sha256": digest(Path(sys.executable).read_bytes()),
               "review_status": "awaiting separate review", "model_calls": 0,
               "comparison_scope": "deterministic retrieval; no generated-answer accuracy or causal advantage measured"}
    write_json(root / "results" / "checks.json", summary)
    return summary


if __name__ == "__main__":
    result = run(Path(sys.argv[1]))
    print(json.dumps({"passed": result["passed"], "checks": len(result["checks"])}))
    raise SystemExit(0 if result["passed"] else 1)
