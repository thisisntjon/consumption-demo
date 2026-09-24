#!/usr/bin/env python3
"""
Ultimate Consumer v0 (Fort Knox Edition)
Autonomous Knowledge Ingestion, Provenance Verification, and Retrieval Engine.
Compliant with SSR SEED v3, BigBoss dual-gate, and thebus retraction doctrines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

_CONSUMER_DIR = Path(__file__).resolve().parent
if str(_CONSUMER_DIR) not in sys.path:
    sys.path.insert(0, str(_CONSUMER_DIR))

from epistemic import (  # noqa: E402
    bundle_issues,
    calibrated_status,
    attach_nuance,
    consume_result,
    epistemic_class,
    explain_uncertainty,
    is_substantive_claim,
    pdf_plain_text,
    score_query_against_claim,
    show_conflicts,
    show_evidence,
    show_history,
    span_in_text,
)
from claim_v2 import validate_v2  # noqa: E402
from library_card import admit as admit_library_card  # noqa: E402
from library_card import library_path, make_card  # noqa: E402


def default_root() -> Path:
    env = os.environ.get("HISTORYLAB_ROOT")
    if env:
        return Path(env)
    # Keep the fixture portable: callers can point it at a checkout with
    # HISTORYLAB_ROOT, otherwise resolve relative to the current invocation.
    return Path.cwd()


ROOT = default_root()
CONSUMER_ROOT = ROOT / "consumer"
CLAIMS_DB = CONSUMER_ROOT / "claims" / "claims.jsonl"
REJECTED_DB = CONSUMER_ROOT / "claims" / "rejected.jsonl"
RETRACTIONS_DB = CONSUMER_ROOT / "claims" / "retractions.jsonl"
QUARANTINE_DB = CONSUMER_ROOT / "claims" / "quarantine.jsonl"
MANIFEST_FILE = CONSUMER_ROOT / "manifests" / "sources.jsonl"
WAKE_CARDS_DIR = CONSUMER_ROOT / "wake_cards"
RECEIPTS_DIR = CONSUMER_ROOT / "receipts"

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9\s]+")

ALLOWED_LICENSES = {
    "open-arxiv", "mit", "apache-2.0", "cc-by-4.0", "cc-by-sa-4.0", "public-domain"
}

def sha256_file(filepath: Path | str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def normalize_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()

def compute_content_hash(claim_text: str, falsifier: str, evidence_span: str, source_path: str) -> str:
    body = "\n".join([claim_text.strip(), falsifier.strip(), evidence_span.strip(), source_path.strip()])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()

def compute_normalized_hash(claim_text: str, falsifier: str) -> str:
    body = normalize_text(claim_text) + "\n" + normalize_text(falsifier)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()

def shingles(text: str, n: int = 2) -> set[str]:
    toks = normalize_text(text).split()
    if len(toks) < n:
        return set(toks)
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}

def jaccard(s1: set[str], s2: set[str]) -> float:
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)

class UltimateConsumer:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root is not None else default_root()
        self.consumer_root = self.root / "consumer"
        self.claims_db = self.consumer_root / "claims" / "claims.jsonl"
        self.rejected_db = self.consumer_root / "claims" / "rejected.jsonl"
        self.retractions_db = self.consumer_root / "claims" / "retractions.jsonl"
        self.quarantine_db = self.consumer_root / "claims" / "quarantine.jsonl"
        self.manifest_file = self.consumer_root / "manifests" / "sources.jsonl"
        self.wake_cards_dir = self.consumer_root / "wake_cards"
        self.receipts_dir = self.consumer_root / "receipts"
        self.reuse_db = self.consumer_root / "claims" / "reuse.jsonl"
        self.club_db = self.consumer_root / "claims" / "journal_club.jsonl"
        self.library_db = library_path(self.root)
        for d in [
            self.consumer_root / "claims",
            self.consumer_root / "manifests",
            self.wake_cards_dir,
            self.receipts_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def load_existing_claims(self) -> List[Dict[str, Any]]:
        claims = []
        if self.claims_db.exists():
            with open(self.claims_db, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        claims.append(json.loads(line))
        return claims

    def load_retractions(self) -> List[Dict[str, Any]]:
        rows = []
        if self.retractions_db.exists():
            with open(self.retractions_db, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rows.append(json.loads(line))
        return rows

    def register_source(self, local_path: str, url: str, license_class: str) -> Dict[str, Any]:
        """Ingest source with cryptographic manifest."""
        full_path = self.root / local_path
        if not full_path.exists():
            raise FileNotFoundError(f"Source file does not exist on disk: {full_path}")
        
        file_hash = sha256_file(full_path)
        manifest_record = {
            "path": local_path,
            "sha256": file_hash,
            "bytes": full_path.stat().st_size,
            "source_url": url,
            "license_class": license_class,
            "captured_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(self.manifest_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(manifest_record) + "\n")
        return manifest_record

    def machine_gate(self, candidate: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Strict machine gate: schema, license, local evidence fixity, falsifier presence."""
        trace = []
        passed = True

        # Required fields check
        required = ["item_id", "claim_text", "falsifier", "source_path", "status", "lifecycle"]
        for r in required:
            if not candidate.get(r):
                trace.append(f"FAIL: Missing required field '{r}'")
                passed = False

        # Status check
        if candidate.get("status") in ["UNVERIFIED", "DISPUTED", "CLOSED-UNREAD"]:
            trace.append(f"FAIL: Status is '{candidate.get('status')}' (only VERIFIED may pass machine gate)")
            passed = False
        else:
            trace.append("PASS: Status is VERIFIED")

        # License check
        lic = candidate.get("license_class", "unknown-quarantined")
        if lic not in ALLOWED_LICENSES:
            trace.append(f"FAIL: License class '{lic}' is quarantined / not open")
            passed = False
        else:
            trace.append(f"PASS: License class '{lic}' approved")

        # Falsifier check
        falsifier = candidate.get("falsifier", "").strip()
        if len(falsifier) < 10:
            trace.append("FAIL: Falsifier missing or too short to be testable")
            passed = False
        else:
            trace.append("PASS: Falsifier present and testable")

        # Primary-source shape: handbooks and Wikipedia are not KEEP evidence.
        raw_source_path = candidate.get("source_path", "").split("#")[0]
        src_l = raw_source_path.replace("\\", "/").lower()
        if "wikipedia" in src_l or src_l.endswith(".zim"):
            trace.append("FAIL: Wikipedia/ZIM is encyclopedia, not a KEEP source")
            passed = False
        suffix = Path(raw_source_path).suffix.lower()
        if suffix in {".md", ".html", ".htm", ".txt"} and "papers/" not in src_l:
            trace.append(f"FAIL: {suffix} handbook/prose is not a primary artifact")
            passed = False
        if not is_substantive_claim(candidate.get("claim_text") or ""):
            trace.append("FAIL: claim_text is empty or a placeholder template")
            passed = False
        if not is_substantive_claim(candidate.get("evidence_span") or "", min_alnum=8):
            trace.append("FAIL: evidence_span is empty or a placeholder template")
            passed = False
        klass = (candidate.get("epistemic_class") or "").strip().lower()
        if klass == "replicated" and not candidate.get("replication_receipt"):
            trace.append("FAIL: replicated requires a replication_receipt; vendor agreement is not replication")
            passed = False

        # Local file and hash check
        full_source_path = self.root / raw_source_path
        if not full_source_path.exists():
            trace.append(f"FAIL: source_path does not exist on disk: {raw_source_path}")
            passed = False
        else:
            actual_hash = sha256_file(full_source_path)
            candidate["source_hash"] = actual_hash
            trace.append(f"PASS: Local source verified on disk (SHA256: {actual_hash[:16]}...)")
            if suffix == ".pdf":
                try:
                    pdf_text = pdf_plain_text(full_source_path)
                except Exception as exc:
                    trace.append(f"FAIL: could not read PDF text ({exc})")
                    passed = False
                else:
                    if not span_in_text(candidate.get("evidence_span") or "", pdf_text):
                        trace.append("FAIL: evidence_span not found in source PDF (normalized)")
                        passed = False
                    else:
                        trace.append("PASS: evidence_span found in source PDF")

        # Deduplication check
        existing = self.load_existing_claims()
        cand_norm_hash = compute_normalized_hash(candidate.get("claim_text", ""), candidate.get("falsifier", ""))
        cand_shingles = shingles(candidate.get("claim_text", ""))
        
        for ex in existing:
            if ex.get("item_id") == candidate.get("item_id"):
                trace.append(f"FAIL: Duplicate item_id '{candidate.get('item_id')}' already in vault")
                passed = False
                break
            ex_norm_hash = compute_normalized_hash(ex.get("claim_text", ""), ex.get("falsifier", ""))
            if cand_norm_hash == ex_norm_hash:
                trace.append(f"FAIL: Normalized exact duplicate of {ex.get('item_id')}")
                passed = False
                break
            # Near duplicate
            ex_shingles = shingles(ex.get("claim_text", ""))
            jac = jaccard(cand_shingles, ex_shingles)
            if jac > 0.85:
                trace.append(f"FAIL: Near-duplicate Jaccard {jac:.2f} with {ex.get('item_id')}")
                passed = False
                break

        return passed, trace

    def admit_claim(self, candidate: Dict[str, Any], human_approver: Optional[str] = None) -> Dict[str, Any]:
        """Dual-gate admission: Machine checks first, then BigBoss human approval."""
        passed_machine, trace = self.machine_gate(candidate)
        candidate["content_hash"] = compute_content_hash(
            candidate.get("claim_text", ""),
            candidate.get("falsifier", ""),
            candidate.get("evidence_span", ""),
            candidate.get("source_path", "")
        )
        candidate["normalized_hash"] = compute_normalized_hash(
            candidate.get("claim_text", ""),
            candidate.get("falsifier", "")
        )
        candidate["created_at"] = datetime.now(timezone.utc).isoformat()

        if not passed_machine:
            # Route to rejected or quarantine
            candidate["gate"] = {
                "machine_passed": False,
                "machine_checked_at": datetime.now(timezone.utc).isoformat(),
                "machine_rule_trace": trace,
                "human_approved": False,
                "human_approved_by": None,
                "gate_notes": "Rejected by machine gate."
            }
            target_file = self.quarantine_db if "License" in " ".join(trace) else self.rejected_db
            with open(target_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(candidate) + "\n")
            return {"status": "REJECTED", "candidate": candidate, "trace": trace}

        # Machine passed: check human gate
        if not human_approver:
            candidate["gate"] = {
                "machine_passed": True,
                "machine_checked_at": datetime.now(timezone.utc).isoformat(),
                "machine_rule_trace": trace,
                "human_approved": False,
                "human_approved_by": None,
                "gate_notes": "Pending BigBoss human approval."
            }
            return {"status": "PENDING_HUMAN", "candidate": candidate, "trace": trace}

        # Both gates passed: commit KEEP claim
        candidate["lifecycle"] = "KEEP"
        candidate["gate"] = {
            "machine_passed": True,
            "machine_checked_at": datetime.now(timezone.utc).isoformat(),
            "machine_rule_trace": trace,
            "human_approved": True,
            "human_approved_by": human_approver,
            "human_approved_at": datetime.now(timezone.utc).isoformat(),
            "gate_notes": "Dual-gate passed. Committed to vault."
        }

        with open(self.claims_db, "a", encoding="utf-8") as f:
            f.write(json.dumps(candidate) + "\n")

        # Emit Wake Card
        self.emit_wake_card(candidate)
        return {"status": "KEEP_ADMITTED", "candidate": candidate, "trace": trace}

    def admit_reported_span(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Commit a span-checked paper claim as reported KEEP.

        Machine hash+span is the admit. No human name is written. Class stays
        reported. usable_as_constraint stays false. Replicated claims still
        need admit_claim and a replication receipt.
        """
        candidate = dict(candidate)
        use = str(candidate.get("use") or "").strip()
        if use not in ("wake_card", "eval_set", "ft_candidate"):
            trace = ["FAIL: reported span admit requires use wake_card, eval_set, or ft_candidate"]
            return {"status": "REJECTED", "candidate": candidate, "trace": trace}
        if str(candidate.get("epistemic_class") or "").strip().lower() == "replicated":
            trace = ["FAIL: replicated is not a span admit; it needs a replication_receipt and a human gate"]
            return {"status": "REJECTED", "candidate": candidate, "trace": trace}
        candidate["epistemic_class"] = "reported"
        candidate["status"] = "VERIFIED"
        candidate["lifecycle"] = "KEEP"
        candidate["usable_as_constraint"] = False
        candidate.setdefault("evidence_basis", "reported")
        candidate.setdefault("source_role", "primary")
        candidate.setdefault("support_assessment", "supports")
        candidate.setdefault("transfer", "TRANSFERABLE")
        candidate.setdefault("project", "HistoryLab")
        candidate.setdefault("schema_version", "ssr-claim-v2")
        candidate.setdefault("independence_group", "paper-reported")
        candidate.setdefault("validity_interval", {"as_of": datetime.now(timezone.utc).date().isoformat(), "until": None})
        candidate.setdefault("correction_links", [])
        passed_machine, trace = self.machine_gate(candidate)
        candidate["content_hash"] = compute_content_hash(
            candidate.get("claim_text", ""),
            candidate.get("falsifier", ""),
            candidate.get("evidence_span", ""),
            candidate.get("source_path", ""),
        )
        candidate["normalized_hash"] = compute_normalized_hash(
            candidate.get("claim_text", ""),
            candidate.get("falsifier", ""),
        )
        candidate["created_at"] = datetime.now(timezone.utc).isoformat()
        candidate["verification_receipt"] = {
            "verified_by": "admit_reported_span",
            "verified_at": candidate["created_at"],
            "method": "pymupdf_span_in_pdf",
            "audit_passed": bool(passed_machine),
        }
        v2_errors = validate_v2(candidate)
        if v2_errors:
            trace = list(trace) + [f"FAIL: claim-v2 {err}" for err in v2_errors]
            passed_machine = False
        if not passed_machine:
            candidate["gate"] = {
                "machine_passed": False,
                "machine_checked_at": candidate["created_at"],
                "machine_rule_trace": trace,
                "human_approved": False,
                "human_approved_by": None,
                "gate_notes": "Rejected by span admit. Not written as KEEP.",
            }
            target = self.quarantine_db if any("License" in line for line in trace) else self.rejected_db
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(candidate) + "\n")
            return {"status": "REJECTED", "candidate": candidate, "trace": trace}
        candidate["gate"] = {
            "machine_passed": True,
            "machine_checked_at": candidate["created_at"],
            "machine_rule_trace": trace,
            "human_approved": False,
            "human_approved_by": None,
            "gate_notes": "Span-verified reported KEEP. No human signature. Not a replication.",
        }
        with open(self.claims_db, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")
        return {"status": "KEEP_ADMITTED", "candidate": candidate, "trace": trace}

    def emit_wake_card(self, claim: Dict[str, Any]) -> Path:
        """Write self-contained molecular Markdown Wake Card for agent retrieval."""
        item_id = claim["item_id"]
        card_path = self.wake_cards_dir / f"{item_id}.md"
        content = f"""# Wake Card: {item_id}

> **Directive:** {claim['claim_text']}
> **Status:** {claim['status']} · **Lifecycle:** {claim['lifecycle']} · **Transfer:** {claim['transfer']}

---

### Primary Receipt
- **Source:** `{claim['source_path']}`
- **Source SHA-256:** `{claim['source_hash']}`
- **Content Hash:** `{claim['content_hash']}`
- **License:** `{claim['license_class']}`
- **Evidence Span:**
  > "{claim['evidence_span']}"

### Falsifier
`{claim['falsifier']}`

### Verification Gate
- **Machine Gate:** Passed ({claim['gate']['machine_checked_at']})
- **Human Authority:** Approved by `{claim['gate']['human_approved_by']}` on `{claim['gate']['human_approved_at']}`
- **Trace:** `{"; ".join(claim['gate']['machine_rule_trace'])}`
"""
        with open(card_path, "w", encoding="utf-8") as f:
            f.write(content)
        return card_path

    def retract_claim(self, item_id: str, reason: str, superseded_by: str, author: str = "Jon Simone (BigBoss)") -> Dict[str, Any]:
        """Persist withdrawal before its card; retry the same request after interruption.

        Original claims stay byte-for-byte in the historical ledger. The retraction
        ledger is authoritative for evidence_envelope/consume, not raw get_claim.
        Atomic replacement covers process interruption, not disk/power failure.
        The OS lock serializes this API's writers; external ledger editors must be
        quiescent. A failed card update raises; withdrawal remains effective.
        """
        import tempfile
        if not isinstance(item_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", item_id):
            raise ValueError("Invalid retraction item_id")
        if not all(isinstance(x, str) and x.strip() for x in (reason, superseded_by, author)):
            raise ValueError("Retraction reason, successor and author must be explicit")

        def replace(path, data):
            fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".partial", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)

        # A persistent lock file is not a stale lock: the OS releases its lock
        # when the process dies. Never unlink it (that creates two lock domains).
        with open(self.retractions_db.with_suffix(".lock"), "a+b") as lock:
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                raw = self.retractions_db.read_bytes() if self.retractions_db.exists() else b""
                records = [json.loads(line) for line in raw.decode("utf8").splitlines() if line.strip()]
                prior = [r for r in records if r["retracted_item_id"] == item_id]
                if len(prior) > 1:
                    raise ValueError("Retraction conflict: duplicate withdrawal records")
                if prior:
                    record = prior[0]
                    if any(record.get(k) != v for k, v in
                           (("reason", reason), ("superseded_by", superseded_by), ("retracted_by", author))):
                        raise ValueError("Retraction conflict: request differs from committed withdrawal")
                    if not isinstance(record.get("original_claim"), dict):
                        raise ValueError("Retraction conflict: original evidence unavailable")
                else:
                    matches = [c for c in self.load_existing_claims() if c.get("item_id") == item_id]
                    if len(matches) != 1:
                        raise ValueError("Claim not found or duplicate item_id")
                    record = dict(retracted_item_id=item_id, original_claim=matches[0],
                                  retracted_at=datetime.now(timezone.utc).isoformat(),
                                  retracted_by=author, reason=reason, superseded_by=superseded_by)
                    # Preserve every previous byte, including a missing final newline.
                    data = raw + (b"\n" if raw and not raw.endswith(b"\n") else b"")
                    data += (json.dumps(record, ensure_ascii=False) + "\n").encode("utf8")
                    replace(self.retractions_db, data)
                tombstone = (f"# RETRACTED / TOMBSTONED: {item_id}\n\n"
                             f"Withdrawn: {record['retracted_at']} by {record['retracted_by']}\n"
                             f"Reason: {record['reason']}\nSuperseded By: {record['superseded_by']}\n\n"
                             f"Original statement:\n~~{record['original_claim'].get('claim_text')}~~\n")
                replace(self.wake_cards_dir / f"{item_id}.md", tombstone.encode("utf8"))
                return {"status": "RETRACTED", "record": record}
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def get_claim(self, item_id: str) -> Optional[Dict[str, Any]]:
        for c in self.load_existing_claims():
            if c.get("item_id") == item_id:
                return c
        return None

    def get_source(self, item_id_or_path: str) -> Dict[str, Any]:
        """Check source file existence locally without internet."""
        claim = self.get_claim(item_id_or_path)
        rel_path = claim["source_path"].split("#")[0] if claim else item_id_or_path.split("#")[0]
        full_path = self.root / rel_path
        
        if not full_path.exists():
            return {"exists_locally": False, "path": str(full_path)}
        
        actual_hash = sha256_file(full_path)
        return {
            "exists_locally": True,
            "path": str(full_path),
            "bytes": full_path.stat().st_size,
            "sha256": actual_hash,
            "hash_matches_claim": (claim["source_hash"] == actual_hash) if claim else True
        }

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Content-token search. Stopwords and lone digits do not count as hits."""
        results = []
        for c in self.load_existing_claims():
            score = score_query_against_claim(query, c)
            if score is None:
                continue
            hit = {
                "score": score,
                "item_id": c["item_id"],
                "claim_text": c["claim_text"],
                "status": c.get("status"),
                "source_path": c.get("source_path"),
                "source_hash": c.get("source_hash"),
                "falsifier": c.get("falsifier"),
                "evidence_span": c.get("evidence_span"),
            }
            if "usable_as_constraint" in c:
                hit["usable_as_constraint"] = bool(c.get("usable_as_constraint"))
            if c.get("negative"):
                hit["negative"] = c["negative"]
            if c.get("conflicts_with"):
                hit["conflicts_with"] = list(c["conflicts_with"])
            results.append(hit)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def list_claims(self) -> List[Dict[str, Any]]:
        """Catalog of KEEP rows for browsing. Not a truth score."""
        rows = []
        for c in self.load_existing_claims():
            klass, defaulted = epistemic_class(c)
            rows.append(
                {
                    "item_id": c.get("item_id"),
                    "epistemic_class": klass,
                    "calibrated_status": calibrated_status(c),
                    "claim_text": c.get("claim_text"),
                    "source_path": c.get("source_path"),
                    "school_role": c.get("school_role") or "spine",
                }
            )
        rows.sort(key=lambda r: r["item_id"] or "")
        return rows

    def consume(
        self,
        query: str,
        log_reuse: bool = False,
        consumer: str = "agent",
        task: str = "consume_query",
        use: Optional[str] = None,
        expected_snapshot: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Complete inspectable answer, or honest empty. Does not generate claims.

        A passing span check writes one library card when ``use`` is set.
        The card stays reported and is not a constraint. A repeat of the same
        item and use does not append a second card.
        """
        checked = self.evidence_envelope(query, expected_snapshot=expected_snapshot)
        if checked["status"] not in {"answered", "ambiguous"}:
            diagnostics = []
            if checked.get("reason") == "span_not_in_source_region":
                # Preserve failed-span diagnostics, never let an old successful
                # machine receipt turn this refused answer into an admission.
                diagnostics = [self.machine_check(hit["item_id"])
                               for hit in self.search(query)[:5]]
            return dict(checked, library_cards=[], machine_checks=diagnostics)
        allowed = {row["item_id"] for row in checked["claims"]}
        ranked = [hit for hit in self.search(query) if hit["item_id"] in allowed]
        packets = []
        for hit in ranked[:5]:
            iid = hit["item_id"]
            claim = self.get_claim(iid)
            if not claim:
                continue
            packets.append(
                {
                    "claim": claim,
                    "evidence": show_evidence(claim, self.get_source(iid)),
                    "uncertainty": explain_uncertainty(
                        claim,
                        show_conflicts(iid, claim, self.load_existing_claims(), self.load_retractions()),
                        show_history(iid, claim, self.load_retractions()),
                        self.get_source(iid),
                    ),
                    "conflicts": show_conflicts(iid, claim, self.load_existing_claims(), self.load_retractions()),
                    "history": show_history(iid, claim, self.load_retractions()),
                }
            )
        res = consume_result(query, ranked, packets)
        check_ids = []
        if res.get("status") == "answered" and res.get("item_id"):
            check_ids.append(res["item_id"])
        if res.get("status") == "ambiguous":
            check_ids.extend(c.get("item_id") for c in (res.get("candidates") or []) if c.get("item_id"))
        checks = []
        for iid in check_ids:
            checks.append(self.ensure_machine_checked(iid))
        if checks:
            res["machine_checks"] = [
                {"item_id": c.get("item_id"), "verdict": c.get("verdict")} for c in checks
            ]
        current = self.evidence_envelope(query, expected_snapshot=checked["snapshot_version"])
        if (current["status"] not in {"answered", "ambiguous"}
                or current["claims"] != checked["claims"]
                or res.get("answer") != current.get("answer")
                or res.get("status") != current["status"]):
            return dict(current, status="unavailable", reason="evidence_changed_during_consume",
                        answer=None, claims=[], library_cards=[], candidates=[])
        # These are historical application records, not offline currentness
        # permissions. A caller must check again when using saved work.
        if log_reuse and packets:
            self.append_reuse(item_id=packets[0]["claim"]["item_id"], consumer=consumer,
                              task=task, source="consumer.consume")
        res["library_cards"] = self._library_cards_from_checks(res, checks, use)
        final = self.evidence_envelope(query, expected_snapshot=current["snapshot_version"])
        if final["status"] != current["status"] or final["claims"] != current["claims"]:
            return dict(final, status="unavailable", reason="evidence_changed_during_consume",
                        answer=None, claims=[], library_cards=[], candidates=[])
        res["snapshot_version"] = current["snapshot_version"]
        res["checked_evidence"] = current
        res["usable_as_constraint"] = False
        return res

    def _library_cards_from_checks(
        self,
        res: Dict[str, Any],
        checks: List[Dict[str, Any]],
        use: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Write one card per span that just passed. Empty when use is unset or the check failed."""
        use_name = (use or "").strip()
        if not use_name or res.get("status") not in {"answered", "ambiguous"}:
            return []
        passed = {
            c.get("item_id")
            for c in checks
            if c.get("verdict") == "machine-checked" and c.get("item_id")
        }
        if res.get("status") == "answered" and res.get("item_id"):
            candidate_ids = [res["item_id"]]
        else:
            candidate_ids = [
                c.get("item_id") for c in (res.get("candidates") or []) if c.get("item_id")
            ]
        written: List[Dict[str, Any]] = []
        for item_id in candidate_ids:
            if item_id not in passed:
                continue
            claim = self.get_claim(item_id)
            if not claim:
                continue
            rivals = [other for other in candidate_ids if other != item_id] if res.get("status") == "ambiguous" else []
            card = make_card(claim, use_name, rivals)
            if card is None:
                continue
            stored = admit_library_card(self.library_db, card)
            if stored.get("card"):
                row = dict(stored["card"])
                row["appended"] = bool(stored.get("appended"))
                written.append(row)
        return written

    def nuance(self, query: str) -> Dict[str, Any]:
        """Contrast KEEP rivals. Does not blend answers or assign a truth score."""
        return attach_nuance(self.consume(query))

    def evidence_envelope(self, query: str, expected_snapshot: Optional[str] = None) -> Dict[str, Any]:
        """Read-only, version-bound serving contract for the harness adapter.

        Hash/span checks establish artifact identity and text membership, not
        entailment or truth. No stored verification receipt bypasses these checks.
        The response describes the checked snapshot, not future/offline freshness.
        """
        schema = "historylab-evidence-v1"
        base = {"schema_version": schema, "query": query, "vault": "historylab-keep",
                "answer": None, "claims": [], "blended_answer": None,
                "declares_truth": False, "usable_as_constraint": False}

        def unavailable(reason):
            return dict(base, status="unavailable", reason=reason)

        def read_snapshot():
            return (self.claims_db.read_bytes(),
                    self.retractions_db.read_bytes() if self.retractions_db.exists() else b"")

        def digest(data):
            return hashlib.sha256(data).hexdigest()

        try:
            raw_claims, raw_retractions = read_snapshot()
            base["snapshot_version"] = digest(json.dumps(
                [schema, digest(raw_claims), digest(raw_retractions)]).encode())
            base["checked_at"] = datetime.now(timezone.utc).isoformat()
            if expected_snapshot is not None and expected_snapshot != base["snapshot_version"]:
                return unavailable("stale_snapshot")
            claims = [json.loads(line) for line in raw_claims.decode("utf-8").splitlines() if line.strip()]
            withdrawals = [json.loads(line) for line in raw_retractions.decode("utf-8").splitlines() if line.strip()]
            ids = [c["item_id"] for c in claims]
            if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
                return unavailable("invalid_or_duplicate_claim_id")
            withdrawn = {r["retracted_item_id"] for r in withdrawals}
            active = [c for c in claims if c.get("lifecycle") == "KEEP"
                      and c["item_id"] not in withdrawn
                      and epistemic_class(c)[0] != "superseded"
                      and c.get("transfer") != "SUPERSEDED" and not c.get("superseded_by")]
            ranked = []
            for claim in active:
                score = score_query_against_claim(query, claim)
                if score is not None:
                    ranked.append(dict(claim, score=score))
            ranked.sort(key=lambda c: c["score"], reverse=True)
            if not ranked or ranked[0]["score"] < 3.0:
                if read_snapshot() != (raw_claims, raw_retractions):
                    return unavailable("snapshot_changed_during_read")
                return dict(base, status="empty", reason="no_sufficient_active_evidence")

            dominant = len(ranked) == 1 or ranked[0]["score"] >= ranked[1]["score"] + 2.0
            base["ranked_candidate_count"] = len(ranked)
            if not dominant and len(ranked) > 5:
                return unavailable("candidate_limit_exceeded_refine_query")
            packets, evidence_rows, source_versions = [], [], {}
            for claim in (ranked[:1] if dominant else ranked[:5]):
                klass, defaulted = epistemic_class(claim)
                if defaulted or klass == "unknown":
                    return unavailable("unknown_evidence_class")
                for field in ("claim_text", "falsifier", "source_path", "evidence_span"):
                    if not isinstance(claim.get(field), str) or not claim[field].strip():
                        return unavailable("missing_" + field)
                expected_hash = claim.get("source_hash", "")
                if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
                    return unavailable("invalid_source_hash")
                path_text, _, locator = claim["source_path"].partition("#")
                path = self.root / path_text
                data = path.read_bytes()
                actual_hash = digest(data)
                if actual_hash != expected_hash.lower():
                    return unavailable("source_hash_mismatch")
                source_versions[path] = actual_hash
                pages = []
                if path.suffix.lower() == ".pdf":
                    import fitz
                    with fitz.open(stream=data, filetype="pdf") as doc:
                        if locator and not re.fullmatch(r"page=[1-9][0-9]*", locator):
                            return unavailable("unsupported_source_locator")
                        indices = [int(locator[5:]) - 1] if locator else range(len(doc))
                        for index in indices:
                            if index >= len(doc):
                                return unavailable("source_page_out_of_range")
                            if span_in_text(claim["evidence_span"], doc[index].get_text()):
                                pages.append(index + 1)
                        found = bool(pages)
                elif path.suffix.lower() in {".txt", ".md"} and not locator:
                    found = span_in_text(claim["evidence_span"], data.decode("utf-8"))
                else:
                    return unavailable("unsupported_source_format_or_locator")
                if not found:
                    return unavailable("span_not_in_source_region")
                source = {"exists_locally": True, "path": str(path), "sha256": actual_hash,
                          "hash_matches_claim": True, "bytes": len(data)}
                evidence = show_evidence(claim, source)
                history = show_history(claim["item_id"], claim, withdrawals)
                conflicts = show_conflicts(claim["item_id"], claim, claims, withdrawals)
                uncertainty = explain_uncertainty(claim, conflicts, history, source)
                packets.append(dict(claim=claim, evidence=evidence, uncertainty=uncertainty,
                                    conflicts=conflicts, history=history))
                record = {k: v for k, v in claim.items() if k != "score"}
                evidence_rows.append(dict(
                    evidence, record_version=digest(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()),
                    matched_pages=pages, check_scope="source_hash_and_normalized_span_membership",
                    support_assessment=claim.get("support_assessment", "unassessed"),
                    usable_as_constraint=False, negative=claim.get("negative"),
                    validity_interval=claim.get("validity_interval"),
                    correction_links=claim.get("correction_links", []),
                    nuance_envelope=claim.get("nuance_envelope"),
                    uncertainty=uncertainty, conflicts=conflicts, history=history))
            result = attach_nuance(consume_result(query, ranked, packets))
            if read_snapshot() != (raw_claims, raw_retractions):
                return unavailable("snapshot_changed_during_read")
            if any(digest(path.read_bytes()) != version for path, version in source_versions.items()):
                return unavailable("source_changed_during_read")
            selected = evidence_rows if result["status"] == "ambiguous" else evidence_rows[:1]
            if result["status"] == "empty":
                selected = []
            return dict(base, status=result["status"], answer=result.get("answer"),
                        reason=result.get("reason"), claims=selected,
                        answer_kind=("source_span" if result.get("answer_is_evidence_span") else "recorded_claim")
                        if result.get("answer") is not None else None,
                        answer_note=result.get("note"),
                        must_not_treat_as=result.get("must_not_treat_as"),
                        note="Snapshot only; source membership is not entailment, replication or certification.")
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError, RuntimeError):
            return unavailable("evidence_unreadable_or_invalid")

    CLUB_VERDICTS = (
        "still-reported",
        "contested",
        "retract-queued",
        "unknown",
        "machine-checked",
        "machine-failed",
    )
    HUMAN_VERDICTS = ("still-reported", "contested", "retract-queued", "unknown")

    def club_log(
        self,
        item_id: str,
        *,
        by: str,
        verdict: str,
        note: str = "",
    ) -> Dict[str, Any]:
        """Record consumption. Machine-checked scales; human verdicts do not change KEEP."""
        claim = self.get_claim(item_id)
        if not claim:
            raise KeyError(item_id)
        v = (verdict or "").strip().lower()
        if v not in self.CLUB_VERDICTS:
            raise ValueError(f"verdict must be one of {self.CLUB_VERDICTS}")
        if v in self.HUMAN_VERDICTS and not (by or "").strip():
            raise ValueError("human verdicts require --by")
        row = {
            "at": datetime.now(timezone.utc).isoformat(),
            "item_id": item_id,
            "by": by.strip(),
            "verdict": v,
            "note": (note or "").strip(),
            "epistemic_class_at_club": epistemic_class(claim)[0],
            "does_not_change_keep": True,
            "kind": "human" if v in self.HUMAN_VERDICTS else "machine",
        }
        with open(self.club_db, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def last_machine_event(self, item_id: str) -> Optional[Dict[str, Any]]:
        last = None
        if not self.club_db.exists():
            return None
        with open(self.club_db, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                e = json.loads(line)
                if e.get("item_id") == item_id and e.get("verdict") in (
                    "machine-checked",
                    "machine-failed",
                ):
                    last = e
        return last

    def ensure_machine_checked(self, item_id: str) -> Dict[str, Any]:
        last = self.last_machine_event(item_id)
        if last and last.get("verdict") == "machine-checked":
            return last
        return self.machine_check(item_id)

    def machine_check(self, item_id: str) -> Dict[str, Any]:
        """Hash + span-in-PDF. Scales. Does not mean replicated or human-read."""
        claim = self.require_claim(item_id)
        src = self.get_source(item_id)
        rel = (claim.get("source_path") or "").split("#")[0]
        full = self.root / rel
        ok = True
        reasons = []
        if not src.get("exists_locally"):
            ok = False
            reasons.append("source missing")
        elif src.get("hash_matches_claim") is False:
            ok = False
            reasons.append("hash mismatch")
        if full.suffix.lower() == ".pdf" and full.exists():
            try:
                text = pdf_plain_text(full)
            except Exception as exc:
                ok = False
                reasons.append(f"pdf read failed: {exc}")
            else:
                if not span_in_text(claim.get("evidence_span") or "", text):
                    ok = False
                    reasons.append("span not in PDF")
        verdict = "machine-checked" if ok else "machine-failed"
        return self.club_log(
            item_id,
            by="consumer.machine_check",
            verdict=verdict,
            note="; ".join(reasons),
        )

    def machine_check_all(self) -> Dict[str, Any]:
        rows = []
        for c in self.load_existing_claims():
            rows.append(self.machine_check(c["item_id"]))
        failed = [r["item_id"] for r in rows if r["verdict"] == "machine-failed"]
        return {
            "checked": len(rows),
            "passed": len(rows) - len(failed),
            "failed": failed,
            "note": "machine-checked = bytes+span. Not replicated. Not human-read.",
        }

    def club_status(self) -> Dict[str, Any]:
        events = []
        if self.club_db.exists():
            with open(self.club_db, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        latest: Dict[str, Dict[str, Any]] = {}
        latest_machine: Dict[str, Dict[str, Any]] = {}
        latest_human: Dict[str, Dict[str, Any]] = {}
        for e in events:
            latest[e["item_id"]] = e
            if e.get("kind") == "human" or e.get("verdict") in self.HUMAN_VERDICTS:
                latest_human[e["item_id"]] = e
            if e.get("verdict") in ("machine-checked", "machine-failed"):
                latest_machine[e["item_id"]] = e
        keep_ids = [c["item_id"] for c in self.load_existing_claims()]
        never = [i for i in keep_ids if i not in latest]
        machine_ok = [
            i
            for i in keep_ids
            if latest_machine.get(i, {}).get("verdict") == "machine-checked"
        ]
        machine_bad = [
            i
            for i in keep_ids
            if latest_machine.get(i, {}).get("verdict") == "machine-failed"
        ]
        return {
            "keep": len(keep_ids),
            "machine_checked": len(machine_ok),
            "machine_failed": machine_bad,
            "human_clubbed": len(latest_human),
            "never_touched": never,
            "latest": latest,
            "note": (
                "machine-checked scales (hash+span). "
                "Humans do not scale; they only contest, retract-queue, or confirm. "
                "None of this is replication."
            ),
        }

    def append_reuse(
        self,
        item_id: str,
        consumer: str = "agent",
        task: str = "unspecified",
        source: Optional[str] = None,
        outcome: str = "SUCCESS",
    ) -> Dict[str, Any]:
        """Record an immutable consumption/reuse event in claims/reuse.jsonl."""
        allowed_consumers = {"agent", "human", "cli", "model"}
        if consumer not in allowed_consumers:
            consumer = "agent"

        item_id = item_id.strip()
        task = task.strip()
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        row = {
            "timestamp": now_ts,
            "item_id": item_id,
            "card_id": item_id,
            "consumer": consumer,
            "task": task,
            "outcome": outcome,
        }
        if source:
            row["source"] = str(source).strip()

        self.reuse_db.parent.mkdir(parents=True, exist_ok=True)
        with open(self.reuse_db, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

        return {"ok": True, "path": str(self.reuse_db), "row": row}

    def get_reuse_stats(self) -> Dict[str, Any]:
        """Compute consumption coverage, reuse counts, and cold unconsumed claims."""
        events = []
        if self.reuse_db.exists():
            with open(self.reuse_db, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            events.append(json.loads(line))
                        except Exception:
                            pass

        claims = self.load_existing_claims()
        total_claims = len(claims)
        all_claim_ids = {c.get("item_id") or c.get("claim_id") for c in claims if (c.get("item_id") or c.get("claim_id"))}

        consumed_counts: Dict[str, int] = {}
        consumer_breakdown: Dict[str, int] = {}

        for ev in events:
            cid = ev.get("item_id") or ev.get("card_id")
            if cid:
                consumed_counts[cid] = consumed_counts.get(cid, 0) + 1
            cons = ev.get("consumer", "unknown")
            consumer_breakdown[cons] = consumer_breakdown.get(cons, 0) + 1

        unique_consumed = set(consumed_counts.keys()) & all_claim_ids
        cold_claims = sorted(list(all_claim_ids - unique_consumed))

        ratio = (len(unique_consumed) / total_claims * 100.0) if total_claims > 0 else 0.0

        top_consumed = sorted(
            [{"item_id": cid, "count": cnt} for cid, cnt in consumed_counts.items() if cid in all_claim_ids],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        return {
            "total_consumption_events": len(events),
            "unique_claims_consumed": len(unique_consumed),
            "total_admitted_claims": total_claims,
            "consumption_ratio_pct": round(ratio, 2),
            "consumer_breakdown": consumer_breakdown,
            "top_consumed": top_consumed,
            "cold_claims_count": len(cold_claims),
            "cold_claims_sample": cold_claims[:5],
        }

    def require_claim(self, item_id: str) -> Dict[str, Any]:
        c = self.get_claim(item_id)
        if not c:
            raise KeyError(item_id)
        return c

    def show_evidence(self, item_id: str) -> Dict[str, Any]:
        claim = self.require_claim(item_id)
        return show_evidence(claim, self.get_source(item_id))

    def show_conflicts(self, item_id: str) -> Dict[str, Any]:
        claim = self.require_claim(item_id)
        return show_conflicts(item_id, claim, self.load_existing_claims(), self.load_retractions())

    def show_history(self, item_id: str) -> Dict[str, Any]:
        claim = self.require_claim(item_id)
        return show_history(item_id, claim, self.load_retractions())

    def explain_uncertainty(self, item_id: str) -> Dict[str, Any]:
        claim = self.require_claim(item_id)
        source = self.get_source(item_id)
        conflicts = show_conflicts(item_id, claim, self.load_existing_claims(), self.load_retractions())
        history = show_history(item_id, claim, self.load_retractions())
        return explain_uncertainty(claim, conflicts, history, source)

    def verify_bundle(self, pack_dir: Path) -> Dict[str, Any]:
        pack = Path(pack_dir)
        claims_path = pack / "claims.jsonl"
        if not claims_path.exists():
            return {
                "ok": False,
                "pack": str(pack),
                "error": "claims.jsonl missing",
                "issues": [{"item_id": None, "error": "claims.jsonl missing"}],
            }
        claims = []
        with open(claims_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    claims.append(json.loads(line))

        # Temporarily overlay pack claims for source lookup by id.
        overlay = {c.get("item_id"): c for c in claims}
        portable = bool(claims) and all(c.get("bundle_source_path") for c in claims)

        def get_source_for(item_id: str) -> Dict[str, Any]:
            claim = overlay.get(item_id)
            if not claim:
                return {"exists_locally": False, "path": None}
            bundled = claim.get("bundle_source_path")
            rel = (bundled or claim.get("source_path") or "").split("#")[0]
            base = pack if bundled else self.root
            full = (base / rel).resolve()
            # Bundled sources may never escape the package or fall back to this host.
            if bundled and (Path(rel).is_absolute() or not full.is_relative_to(pack.resolve())):
                return {"exists_locally": False, "path": str(full)}
            if not full.is_file():
                return {"exists_locally": False, "path": str(full)}
            actual = sha256_file(full)
            claimed = claim.get("source_hash")
            return {
                "exists_locally": True,
                "path": str(full),
                "sha256": actual,
                "hash_matches_claim": (claimed == actual) if claimed else False,
            }

        issues = bundle_issues(claims, get_source_for)
        for claim in claims:
            if claim.get("schema_version") == "ssr-claim-v2":
                issues.extend({"item_id": claim.get("item_id"), "error": f"v2: {error}"} for error in validate_v2(claim))
        return {
            "ok": not issues,
            "pack": str(pack),
            "claim_count": len(claims),
            "issues": issues,
            "verification_scope": "structure and source-byte integrity only; not claim support or truth",
            "source_resolution": "bundle-only" if portable else "host-dependent",
            "portable_integrity_verified": portable and not issues,
        }


def _print_json(obj: Any) -> None:
    try:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    except (UnicodeEncodeError, UnicodeError):
        print(json.dumps(obj, indent=2, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description="Ultimate Consumer v0 — Fort Knox CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # get-claim
    p_get = subparsers.add_parser("get-claim", help="Retrieve claim and its receipts by ID")
    p_get.add_argument("item_id", help="Unique claim ID (e.g. claim-hl-mla-kv-reduction)")

    # get-source
    p_src = subparsers.add_parser("get-source", help="Inspect local source file and verify offline presence")
    p_src.add_argument("target", help="Claim ID or relative source path")

    p_search = subparsers.add_parser("search", help="Search KEEP claims offline")
    p_search.add_argument("query", help="Search query string")

    subparsers.add_parser("list", help="Catalog KEEP ids, class, and claim text")

    p_ev = subparsers.add_parser("show-evidence", help="Claim + span + hash + epistemic class")
    p_ev.add_argument("item_id")

    p_cf = subparsers.add_parser("show-conflicts", help="Recorded dissent; empty is not consensus")
    p_cf.add_argument("item_id")

    p_hi = subparsers.add_parser("show-history", help="Supersession, retraction, timestamps")
    p_hi.add_argument("item_id")

    p_un = subparsers.add_parser("explain-uncertainty", help="Class, gaps, what would falsify or raise")
    p_un.add_argument("item_id")

    p_co = subparsers.add_parser(
        "consume",
        help="Complete inspectable answer to a question, or honest empty",
    )
    p_co.add_argument("query", nargs="+", help="Natural-language question")
    p_co.add_argument("--log-reuse", action="store_true", help="Log proof of consumption to claims/reuse.jsonl")
    p_co.add_argument("--consumer", default="agent", choices=["agent", "human", "cli", "model"])
    p_co.add_argument("--task", default="consume_query", help="Consuming task context")
    p_co.add_argument(
        "--use",
        default="",
        help="Library use key. A passing span check appends one card for this use.",
    )

    p_nu = subparsers.add_parser(
        "nuance",
        help="Contrast KEEP rivals; never blend into one truth",
    )
    p_nu.add_argument("query", nargs="+", help="Natural-language question")

    p_club = subparsers.add_parser("club", help="Journal-club a KEEP row (human verdict; does not retract)")
    p_club.add_argument("item_id")
    p_club.add_argument("--by", required=True, help="Who stood behind this reading")
    p_club.add_argument(
        "--verdict",
        required=True,
        choices=["still-reported", "contested", "retract-queued", "unknown"],
    )
    p_club.add_argument("--note", default="")
    subparsers.add_parser("club-status", help="Machine-checked vs never-touched KEEP")
    subparsers.add_parser(
        "club-sweep",
        help="Hash+span check every KEEP (scales; not human-read, not replicated)",
    )

    p_gy = subparsers.add_parser(
        "graveyard",
        help="Search institutional negative results, falsifiers, and failure regimes",
    )
    p_gy.add_argument("query", nargs="+", help="Topic or hypothesis query")

    p_lr = subparsers.add_parser("log-reuse", help="Append an immutable proof of consumption / reuse to claims/reuse.jsonl")
    p_lr.add_argument("--item-id", required=True, help="Claim / card ID")
    p_lr.add_argument("--consumer", default="agent", choices=["agent", "human", "cli", "model"])
    p_lr.add_argument("--task", required=True, help="Task description")
    p_lr.add_argument("--outcome", default="SUCCESS", help="Outcome (SUCCESS, FAILURE, etc.)")
    p_lr.add_argument("--source", default=None, help="Optional source / binder")

    subparsers.add_parser("reuse-stats", help="Show consumption coverage, reuse counts, and cold unconsumed claims")

    p_vb = subparsers.add_parser("verify-bundle", help="Check a pack directory offline")
    p_vb.add_argument("pack_dir")

    subparsers.add_parser("ingest-demo", help="Run end-to-end ingestion demo on HistoryLab claims")

    args = parser.parse_args()
    consumer = UltimateConsumer()

    try:
        if args.command == "get-claim":
            c = consumer.get_claim(args.item_id)
            if c:
                _print_json(c)
            else:
                print(f"Claim '{args.item_id}' not found in KEEP vault.", file=sys.stderr)
                sys.exit(1)

        elif args.command == "get-source":
            _print_json(consumer.get_source(args.target))

        elif args.command == "list":
            rows = consumer.list_claims()
            print(f"{len(rows)} KEEP rows (historylab-keep). Class is not a truth score.\n")
            for r in rows:
                text = (r.get("claim_text") or "").replace("\n", " ")
                if len(text) > 100:
                    text = text[:97] + "..."
                print(f"{r['item_id']}\t{r['epistemic_class']}\t{text}")

        elif args.command == "search":
            res = consumer.search(args.query)
            print(f"Found {len(res)} matches for '{args.query}':\n")
            for r in res:
                print(f"[{r['item_id']}] (score: {r['score']})")
                if r.get("negative") and "headline is not the page sentence" in r["negative"]:
                    print(f"  Page sentence: {r.get('evidence_span')}")
                    print(f"  Headline (not on the page): {r['claim_text']}")
                else:
                    print(f"  Claim: {r['claim_text']}")
                if r.get("negative"):
                    print(f"  Boundary: {r['negative']}")
                if "usable_as_constraint" in r:
                    print(f"  Constraint: {r['usable_as_constraint']}")
                print(f"  Receipt: {r['source_path']} (SHA: {r['source_hash'][:16]}...)")
                print(f"  Falsifier: {r['falsifier']}\n")

        elif args.command == "show-evidence":
            _print_json(consumer.show_evidence(args.item_id))

        elif args.command == "show-conflicts":
            _print_json(consumer.show_conflicts(args.item_id))

        elif args.command == "show-history":
            _print_json(consumer.show_history(args.item_id))

        elif args.command == "explain-uncertainty":
            _print_json(consumer.explain_uncertainty(args.item_id))

        elif args.command == "consume":
            q = " ".join(args.query)
            auto_log = args.log_reuse or os.environ.get("SSR_AUTO_LOG_REUSE") == "1"
            _print_json(
                consumer.consume(
                    q,
                    log_reuse=auto_log,
                    consumer=args.consumer,
                    task=args.task,
                    use=args.use or None,
                )
            )

        elif args.command == "nuance":
            q = " ".join(args.query)
            _print_json(consumer.nuance(q))

        elif args.command == "club":
            _print_json(
                consumer.club_log(args.item_id, by=args.by, verdict=args.verdict, note=args.note)
            )

        elif args.command == "club-status":
            _print_json(consumer.club_status())

        elif args.command == "club-sweep":
            _print_json(consumer.machine_check_all())

        elif args.command == "graveyard":
            try:
                from consumer.graveyard import search_graveyard
            except ImportError:
                from graveyard import search_graveyard
            q = " ".join(args.query)
            _print_json({"query": q, "failure_modes_and_falsifiers": search_graveyard(q)})

        elif args.command == "log-reuse":
            res = consumer.append_reuse(
                item_id=args.item_id,
                consumer=args.consumer,
                task=args.task,
                source=args.source,
                outcome=args.outcome,
            )
            _print_json(res)

        elif args.command == "reuse-stats":
            _print_json(consumer.get_reuse_stats())

        elif args.command == "verify-bundle":
            result = consumer.verify_bundle(Path(args.pack_dir))
            _print_json(result)
            if not result.get("ok"):
                sys.exit(1)

        elif args.command == "ingest-demo":
            print("Running end-to-end ingest demo...")
    except KeyError as e:
        print(f"Claim {e} not found in KEEP vault.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
