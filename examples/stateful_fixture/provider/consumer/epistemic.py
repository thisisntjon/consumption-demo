"""Epistemic classes and inspectability reports.

SSR does not assign a truth score. A claim is labeled by how it is
supported, and missing support stays missing.
"""

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9\s]+")

STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "of", "to", "for", "on", "in", "and", "or", "not", "no", "yes",
        "what", "which", "who", "whom", "how", "when", "where", "why",
        "does", "do", "did", "with", "from", "that", "this", "these", "those",
        "it", "its", "as", "at", "by", "into", "about", "over", "under",
        "all", "you", "your",
    }
)
# Alone, these do not justify a KEEP hit.
WEAK_TOKENS = frozenset(
    {
        "parameter", "parameters", "model", "models", "training", "data",
        "size", "test", "error", "count", "number", "value", "rate", "paper",
        "layer", "token", "tokens", "loss", "score", "accuracy", "dataset",
        "evaluation", "eval", "claim", "source", "gpt",
        "method", "methods", "used", "defined", "depends", "section",
        "optimization", "variable", "distance", "metric",
        "need", "year", "published", "when", "date", "how", "many",
    }
)

# ==============================================================================
# CALIBRATED EPISTEMIC STATUS TAXONOMY
# SSR does not declare objective "truth". A claim is output with a calibrated
# label reflecting its empirical basis, replication state, and remaining uncertainty.
# ==============================================================================
EPISTEMIC_STATUS_SUPPORTED_PRIMARY = "Supported by primary evidence"
EPISTEMIC_STATUS_REPLICATED = "Independently replicated"
EPISTEMIC_STATUS_DERIVED = "Derived from verified inputs"
EPISTEMIC_STATUS_REPORTED_UNCONFIRMED = "Reported but not independently confirmed"
EPISTEMIC_STATUS_CONTESTED = "Contested"
EPISTEMIC_STATUS_SUPERSEDED = "Superseded"
EPISTEMIC_STATUS_INSUFFICIENT = "Insufficient evidence"
EPISTEMIC_STATUS_FALSIFIED_OR_RETRACTED = "Falsified or retracted"

CALIBRATED_STATUSES = (
    EPISTEMIC_STATUS_SUPPORTED_PRIMARY,
    EPISTEMIC_STATUS_REPLICATED,
    EPISTEMIC_STATUS_DERIVED,
    EPISTEMIC_STATUS_REPORTED_UNCONFIRMED,
    EPISTEMIC_STATUS_CONTESTED,
    EPISTEMIC_STATUS_SUPERSEDED,
    EPISTEMIC_STATUS_INSUFFICIENT,
    EPISTEMIC_STATUS_FALSIFIED_OR_RETRACTED,
)

# ==============================================================================
# CLAIM TYPE TO BEST AVAILABLE TRUTH TEST MATRIX
# ==============================================================================
CLAIM_TYPE_TRUTH_TESTS = {
    "mathematics": {
        "description": "Formal mathematical theorems and symbolic invariants",
        "best_truth_test": "Formal proof checked by an independent proof assistant (Lean, SymPy, Coq)",
        "oracle": "Symbolic proof engine / CAS",
    },
    "software_computation": {
        "description": "Algorithms, throughput, floating-point and memory behaviors",
        "best_truth_test": "Reproducible execution with pinned code, data, environment, and hashes",
        "oracle": "Hermetic containerized Python / C++ execution",
    },
    "empirical_science": {
        "description": "Empirical model performance, scaling laws, physical measurements",
        "best_truth_test": "Primary evidence, controls, preregistration, independent replication",
        "oracle": "Pre-registered benchmark datasets + primary PDF CAS bytes",
    },
    "historical_current_facts": {
        "description": "Authorship, publication dates, hardware specs, historical events",
        "best_truth_test": "Primary records, chain of custody, independent corroboration, timestamps",
        "oracle": "Immutable CAS archival records + cryptographic timestamping",
    },
    "ethics_values": {
        "description": "Normative standards, alignment trade-offs, preferences",
        "best_truth_test": "Explicit assumptions, arguments, disagreement—not objective fact",
        "oracle": "Multi-perspective debate ledger + dialectical trade-off analysis",
    },
}

# ==============================================================================
# "WHAT NOT TO TRUST" DOCTRINE
# Useful signals that must never be conflated with definitive proof.
# ==============================================================================
WHAT_NOT_TO_TRUST = {
    "model_agreement": "Agreement between multiple AI models is NOT proof. Models share training biases, common dataset errors, and architectural priors.",
    "citation_presence": "A citation is NOT proof. Research on generative search engines found only 51.5% of generated sentences were fully supported by citations (Liu et al. 2023, arXiv:2304.09848).",
    "cryptographic_hash": "A cryptographic hash is NOT proof of correctness. It proves an artifact was unchanged, not that it was correct.",
    "reproducibility": "Reproducibility is NOT proof of truth. A reproducible bug or simulation artifact reproduces identically every time.",
    "statistical_significance": "Statistical significance (p < 0.05) is NOT proof. It does not prove the experiment was well-designed or free of leakage.",
    "agent_audit_reports": "Agent-written audit reports are NOT proof. They are claims that themselves require independent audit and verification.",
}

CITATION_VERIFIABILITY_WARNING = (
    "Liu et al. (2023, arXiv:2304.09848) demonstrated that only 51.5% of generated "
    "sentences are fully supported by their citations. Citation presence != evidence validity."
)

EPISTEMIC_CLASSES = (
    "reported",
    "observed",
    "derived",
    "replicated",
    "contested",
    "superseded",
    "unknown",
)

CLASS_MEANING = {
    "reported": "A cited source says this. Not a lab measurement.",
    "observed": "Directly measured or recorded in this lab.",
    "derived": "Calculated from cited inputs.",
    "replicated": "Independently reproduced.",
    "contested": "Credible evidence disagrees. Dissent stays live.",
    "superseded": "Later evidence replaced this claim.",
    "unknown": "Insufficient evidence. Empty is a valid result.",
}

# What a class is not allowed to be treated as.
CLASS_NOT = {
    "reported": "observed fact or lab replication",
    "observed": "a general law beyond the recorded setup",
    "derived": "an independent measurement",
    "replicated": "the first observation",
    "contested": "a low truth score to be averaged away",
    "superseded": "a quiet deletion",
    "unknown": "a guess with a citation",
}

# Calibrated consume language. Never "true".
CLASS_TO_CALIBRATED = {
    "reported": EPISTEMIC_STATUS_REPORTED_UNCONFIRMED,
    "observed": EPISTEMIC_STATUS_SUPPORTED_PRIMARY,
    "derived": EPISTEMIC_STATUS_DERIVED,
    "replicated": EPISTEMIC_STATUS_REPLICATED,
    "contested": EPISTEMIC_STATUS_CONTESTED,
    "superseded": EPISTEMIC_STATUS_SUPERSEDED,
    "unknown": EPISTEMIC_STATUS_INSUFFICIENT,
}


def calibrated_status(claim: Dict[str, Any], *, retracted: bool = False) -> str:
    if retracted:
        return EPISTEMIC_STATUS_FALSIFIED_OR_RETRACTED
    klass, _ = epistemic_class(claim)
    return CLASS_TO_CALIBRATED[klass]


_PLACEHOLDER_CLAIM = re.compile(
    r"flawed attempt:\s*\.\s*reason:\s*\.\s*counterexample:",
    re.I,
)


def is_substantive_claim(text: str, *, min_alnum: int = 8) -> bool:
    """Reject empty templates. Count is not knowledge."""
    s = (text or "").strip()
    if not s:
        return False
    if _PLACEHOLDER_CLAIM.search(s):
        return False
    if sum(ch.isalnum() for ch in s) < min_alnum:
        return False
    return True


def normalize_for_span(s: str) -> str:
    """Hyphenation/ligature-aware text for quote-in-PDF checks."""
    s = (s or "").lower()
    for lig, plain in (
        ("\ufb01", "fi"),
        ("\ufb02", "fl"),
        ("\ufb03", "ffi"),
        ("\ufb04", "ffl"),
        ("\ufb00", "ff"),
    ):
        s = s.replace(lig, plain)
    for a, b in (
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("\u2212", "-"),
        ("\u00ad", ""),
    ):
        s = s.replace(a, b)
    s = re.sub(r"-\s+", "", s)
    s = s.replace("-", "").replace("/", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def span_in_text(span: str, text: str, *, min_len: int = 12) -> bool:
    ns = normalize_for_span(span)
    if len(ns) < min_len:
        return False
    return ns in normalize_for_span(text)


def pdf_plain_text(path) -> str:
    import fitz

    doc = fitz.open(path)
    return "\n".join(page.get_text("text") for page in doc)


def normalize_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def content_tokens(text: str) -> List[str]:
    glued = re.sub(r"([A-Za-z])-+(\d)", r"\1\2", text or "")
    glued = re.sub(r"\b(\d+)\s*billion\b", lambda m: m.group(1) + "b " + m.group(0), glued, flags=re.I)
    out = []
    for t in normalize_text(glued).split():
        if t in STOPWORDS:
            continue
        if len(t) <= 1:
            continue
        if t.isdigit() and len(t) == 1:
            continue
        out.append(t)
        m = re.fullmatch(r"([a-z]+)(\d+[a-z0-9]*)", t)
        if m and len(m.group(1)) >= 3 and m.group(1) not in STOPWORDS:
            out.append(m.group(1))
    return out



def facet_mismatch(query: str, claim: Dict[str, Any]) -> bool:
    """True => reject claim for this query (asked facet absent from claim).

    Covers common complete-answer failures: params vs benchmark score,
    language pair, and explicit model-size tokens (7B/13B/...).
    """
    qn = normalize_text(query)
    blob = " ".join(
        [
            claim.get("item_id") or "",
            claim.get("claim_text") or "",
            claim.get("evidence_span") or "",
        ]
    )
    bn = normalize_text(blob)

    # Size-adjective "7 billion parameter LLaMA" is not a parameter-count ask.
    size_adj = bool(
        re.search(
            r"\b\d+[\d.]*\s*(billion|million)\s+parameters?\s+"
            r"(model|network|llm|llama|gpt|bert|transformer|checkpoint)?",
            qn,
        )
    ) or bool(re.search(r"\b\d{1,4}\s*b\s+parameters?\b", qn))

    # Same billion→Nb glue as content_tokens, for size facet checks.
    def _glue_billions(s: str) -> str:
        return re.sub(
            r"\b(\d+)\s*billion\b",
            lambda m: m.group(1) + "b " + m.group(0),
            s,
            flags=re.I,
        )

    qn_g = normalize_text(_glue_billions(query))
    bn_g = normalize_text(_glue_billions(blob))

    param_ask = bool(
        re.search(
            r"\b(parameters?|params?|parameter count|how many parameters|number of parameters)\b",
            qn,
        )
    ) and not size_adj
    if param_ask:
        # Require an explicit parameter-count facet - not MFU/GLUE/BLEU with a bare "540B".
        has_param_facet = bool(
            re.search(
                r"(\d[\d.]*)(\s+(million|billion)\s+|\s*)parameters?"
                r"|\d[\d.]*\s*[mb]\s*parameters?"  # 110M / 7B style counts
                r"|parameter counts?"
                r"|\bparams?\s*(=|:|of|is|are)"
                r"|\b\d{1,4}\s*b\s*(parameter|params|param)\b"
                r"|\b\d{1,4}b\s*(parameter|params|param)\b"
                r"|\btokens\s+per\s+parameter\b",
                bn,
            )
        )
        if not has_param_facet:
            return True

    # Model-size tokens in the query must appear in the claim (7b/13b/70b...).
    for m in re.finditer(r"\b(\d{1,3})\s*b\b", qn_g):
        size = m.group(1)
        if size == "1":
            continue
        if not (
            re.search(rf"\b{size}\s*b\b", bn_g)
            or re.search(rf"\b{size}b\b", bn_g.replace(" ", ""))
        ):
            return True

    if re.search(r"\b(english[- ]french|en[- ]?fr|english to french)\b", qn):
        if not re.search(r"\b(french|en[- ]?fr|english[- ]?(to[- ]?)?french)\b", bn):
            return True

    if re.search(r"\b(english[- ]german|en[- ]?de|english to german)\b", qn):
        if not re.search(r"\b(german|en[- ]?de|english[- ]?(to[- ]?)?german)\b", bn):
            return True

    # Hyperparam facet: if the question names a knob, the claim must name it.
    hyperparams = [
        "beta1", "beta2", "beta 1", "beta 2",
        "epsilon", "learning rate", "momentum",
        "weight decay", "dropout", "warmup", "batch size", "temperature",
    ]
    # also compact forms in tokenized query
    q_compact = qn.replace(" ", "")
    for hp in hyperparams:
        hp_n = normalize_text(hp)
        if hp_n in qn or hp_n.replace(" ", "") in q_compact:
            if hp_n not in bn and hp_n.replace(" ", "") not in bn.replace(" ", ""):
                return True
    # beta1 / beta2 glued
    for m in re.finditer(r"\bbeta\s*([12])\b", qn):
        needle = f"beta{m.group(1)}"
        if needle not in bn.replace(" ", "") and f"beta {m.group(1)}" not in bn:
            return True

    return False


def param_ask_bonus(query: str, claim: Dict[str, Any], strong: Sequence[str]) -> bool:
    """True when query asks for a parameter count and claim carries an explicit count + model hit."""
    qn = normalize_text(query)
    bn = normalize_text(
        " ".join(
            [
                claim.get("item_id") or "",
                claim.get("claim_text") or "",
                claim.get("evidence_span") or "",
            ]
        )
    )
    asks = bool(
        re.search(
            r"how many parameters|parameter count|number of parameters|\bparams\b",
            qn,
        )
    )
    if not asks:
        return False
    has_count = bool(
        re.search(
            r"(\d[\d.]*)(\s+(million|billion)\s+|\s*)parameters?"
            r"|\d[\d.]*\s*[mb]\s*parameters?"
            r"|\b\d{1,4}\s*b\s*(parameter|params|param)\b"
            r"|\b\d{1,4}b\s*(parameter|params|param)\b",
            bn,
        )
    )
    return has_count and bool(strong)

def score_query_against_claim(query: str, claim: Dict[str, Any]) -> Optional[float]:
    q = content_tokens(query)
    if not q:
        return None
    if facet_mismatch(query, claim):
        return None
    blob = " ".join(
        [
            claim.get("item_id") or "",
            claim.get("claim_text") or "",
            claim.get("evidence_span") or "",
        ]
    )
    blob_tokens = set(content_tokens(blob))
    hits = [t for t in q if t in blob_tokens]
    if not hits:
        return None
    strong = [t for t in hits if t not in WEAK_TOKENS]
    if not strong:
        return None
    id_tokens = set(content_tokens(claim.get("item_id") or ""))
    if len(strong) < 2 and not (len(strong) == 1 and strong[0] in id_tokens):
        return None
    if {"year", "published", "when", "date"} & set(q):
        ct = claim.get("claim_text") or ""
        if not re.search(r"publish|released|appeared|year", ct, re.I):
            return None
    if "required" in q and "lab" in q:
        return None
    if "required" in q and claim.get("school_role") in ("skip_always", "off_spine"):
        return None
    score = float(len(hits)) + 0.5 * float(len(strong))
    nq = normalize_text(query)
    if len(nq) >= 12 and nq in normalize_text(blob):
        score += 5.0
    # Curated param-count cards: model name + explicit count should clear MIN_ANSWER_SCORE
    # even when "parameters" is weak (fork A coverage).
    if param_ask_bonus(query, claim, strong):
        score += 1.0
    return score


def _candidate(row: Dict[str, Any]) -> Dict[str, Any]:
    """A rival card. Carries the boundary when the claim has one. Does not pick a winner."""
    item = {
        "item_id": row.get("item_id"),
        "score": row.get("score"),
        "claim_text": row.get("claim_text"),
    }
    if "usable_as_constraint" in row:
        item["usable_as_constraint"] = bool(row.get("usable_as_constraint"))
    if row.get("negative"):
        item["negative"] = row["negative"]
    if row.get("evidence_span"):
        item["evidence_span"] = row["evidence_span"]
    if row.get("negative") and "headline is not the page sentence" in row["negative"]:
        page = (row.get("evidence_span") or "").strip()
        if page:
            item["page_sentence"] = page
    if row.get("conflicts_with"):
        item["conflicts_with"] = list(row["conflicts_with"])
    return item


def consume_result(
    query: str,
    ranked: Sequence[Dict[str, Any]],
    packets: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble a complete inspectable answer. Never invent a claim_text."""
    if not ranked:
        return {
            "query": query,
            "vault": "historylab-keep",
            "status": "empty",
            "answer": None,
            "item_id": None,
            "reason": "no KEEP with sufficient content overlap",
            "candidates": [],
            "completeness": {
                "has_claim": False,
                "has_source": False,
                "has_span": False,
                "has_falsifier": False,
                "uncertainty_visible": True,
                "unsupported_conclusions": [],
                "effort": "one consume command; no follow-up required",
                "usable_for_research": False,
            },
            "vendor_agreement_is_not_proof": True,
        }
    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    top_score = float(top["score"])
    # Weak matches: abstain rather than promote a thin overlap (Q10-class noise).
    MIN_ANSWER_SCORE = 3.0
    MIN_AMBIGUOUS_SCORE = 4.0
    if top_score < MIN_ANSWER_SCORE:
        return {
            "query": query,
            "vault": "historylab-keep",
            "status": "empty",
            "answer": None,
            "item_id": None,
            "reason": "best KEEP overlap below confidence floor; abstaining",
            "candidates": [
                _candidate(r)
                for r in ranked[:5]
            ],
            "completeness": {
                "has_claim": False,
                "has_source": False,
                "has_span": False,
                "has_falsifier": False,
                "uncertainty_visible": True,
                "unsupported_conclusions": [],
                "effort": "one consume command; no follow-up required",
                "usable_for_research": False,
            },
            "vendor_agreement_is_not_proof": True,
        }
    dominant = second is None or top_score >= float(second["score"]) + 2.0
    if not dominant:
        if top_score < MIN_AMBIGUOUS_SCORE:
            return {
                "query": query,
                "vault": "historylab-keep",
                "status": "empty",
                "answer": None,
                "item_id": None,
                "reason": "near-ties below confidence floor; abstaining",
                "candidates": [
                    _candidate(r)
                    for r in ranked[:5]
                ],
                "completeness": {
                    "has_claim": False,
                    "has_source": False,
                    "has_span": False,
                    "has_falsifier": False,
                    "uncertainty_visible": True,
                    "unsupported_conclusions": ["would require picking among weak near-ties"],
                    "effort": "one consume command; no follow-up required",
                    "usable_for_research": False,
                },
                "vendor_agreement_is_not_proof": True,
            }
        return {
            "query": query,
            "vault": "historylab-keep",
            "status": "ambiguous",
            "answer": None,
            "item_id": None,
            "reason": "multiple KEEP cards scored similarly; not choosing a winner",
            "candidates": [
                _candidate(r)
                for r in ranked[:5]
            ],
            "completeness": {
                "has_claim": False,
                "has_source": False,
                "has_span": False,
                "has_falsifier": False,
                "uncertainty_visible": True,
                "unsupported_conclusions": ["would require picking among near-ties"],
                "effort": "inspect candidates with get-claim / show-evidence",
                "usable_for_research": False,
            },
            "vendor_agreement_is_not_proof": True,
        }
    packet = packets[0]
    claim = packet["claim"]
    evidence = packet["evidence"]
    uncertainty = packet["uncertainty"]
    conflicts = packet["conflicts"]
    klass, defaulted = epistemic_class(claim)
    result = {
        "query": query,
        "vault": "historylab-keep",
        "status": "answered",
        "answer": claim.get("claim_text"),
        "item_id": claim.get("item_id"),
        "score": top["score"],
        "epistemic_class": klass,
        "epistemic_class_defaulted": defaulted,
        "calibrated_status": calibrated_status(claim),
        "class_meaning": CLASS_MEANING.get(klass),
        "must_not_treat_as": CLASS_NOT.get(klass),
        "never_merely_true": True,
        "evidence_span": claim.get("evidence_span"),
        "source_path": claim.get("source_path"),
        "source": evidence.get("source"),
        "falsifier": claim.get("falsifier"),
        "gaps": uncertainty.get("gaps") or [],
        "conflicts": conflicts.get("conflicts") or [],
        "history_events": (packet.get("history") or {}).get("events") or [],
        "completeness": {
            "has_claim": bool(claim.get("claim_text")),
            "has_source": bool((evidence.get("source") or {}).get("exists_locally")),
            "has_span": bool((claim.get("evidence_span") or "").strip()),
            "has_falsifier": bool((claim.get("falsifier") or "").strip()),
            "uncertainty_visible": True,
            "unsupported_conclusions": [],
            "effort": "one consume command",
            "usable_for_research": bool(
                claim.get("claim_text")
                and (evidence.get("source") or {}).get("exists_locally")
                and (claim.get("falsifier") or "").strip()
            ),
        },
        "vendor_agreement_is_not_proof": True,
        "nuance_envelope": claim.get("nuance_envelope"),
        "note": "Answer is the KEEP claim_text. Nothing was generated beyond the vault.",
    }
    if "usable_as_constraint" in claim:
        result["usable_as_constraint"] = bool(claim.get("usable_as_constraint"))
    if claim.get("negative"):
        result["negative"] = claim["negative"]
    if (
        result.get("negative")
        and "headline is not the page sentence" in result["negative"]
        and (claim.get("evidence_span") or "").strip()
    ):
        result["paraphrase"] = result["answer"]
        result["answer"] = claim["evidence_span"].strip()
        result["answer_is_evidence_span"] = True
        result["note"] = (
            "Answer is the evidence span from the hashed PDF. "
            "The headline is a paraphrase and was not found on that page."
        )
        if any(
            mark in result["negative"]
            for mark in ("text layer", "not a sentence", "not the whole sentence", "Do not label")
        ):
            result["note"] += " Read the negative before quoting this span."
    span = (claim.get("evidence_span") or "").strip()
    headline = (result.get("paraphrase") or claim.get("claim_text") or "").strip()
    if (
        not result.get("answer_is_evidence_span")
        and span
        and len(headline) > 40
        and headline.casefold() in span.casefold()
        and span.casefold() != headline.casefold()
    ):
        result["paraphrase"] = result.get("answer")
        result["answer"] = span
        result["answer_is_evidence_span"] = True
        result["note"] = (
            "Answer is the evidence span from the hashed PDF. "
            "The headline is the shorter clause inside that sentence."
        )
    if (
        result.get("negative")
        and "Do not" in result["negative"]
        and "Do not quote the headline as that page." not in result["negative"]
        and "Read the negative" not in (result.get("note") or "")
    ):
        result["note"] += " Read the negative before quoting this span."
    return result


def distinct_tokens(texts: Sequence[str]) -> List[List[str]]:
    """Tokens in each text not in the union of the others. No generated labels."""
    sets = [set(content_tokens(t or "")) for t in texts]
    out: List[List[str]] = []
    for i, s in enumerate(sets):
        others: set = set()
        for j, o in enumerate(sets):
            if j != i:
                others |= o
        out.append(sorted(s - others)[:8])
    return out


def attach_nuance(consume_out: Dict[str, Any]) -> Dict[str, Any]:
    """Contrastive view of consume. Never blends claim_text values."""
    out = dict(consume_out)
    out["nuance_engine"] = "contrast-v0"
    out["blended_answer"] = None
    status = out.get("status")
    if status == "empty":
        out["contrast"] = []
        out["axes_note"] = "no KEEP rivals; empty is not a nuance paragraph"
        return out
    if status == "ambiguous":
        cands = list(out.get("candidates") or [])
        texts = [c.get("claim_text") or "" for c in cands]
        deltas = distinct_tokens(texts)
        contrast = []
        for c, delta in zip(cands, deltas):
            contrast.append(
                {
                    "item_id": c.get("item_id"),
                    "claim_text": c.get("claim_text"),
                    "distinct_tokens": delta,
                    "epistemic_class": "reported",
                }
            )
        out["contrast"] = contrast
        out["axes_note"] = (
            "Rivals kept separate. distinct_tokens are from claim_text only; "
            "they are not a declared taxonomy."
        )
        return out
    rivals = []
    out["contrast"] = [
        {
            "item_id": out.get("item_id"),
            "claim_text": out.get("answer"),
            "distinct_tokens": [],
            "epistemic_class": out.get("epistemic_class"),
            "must_not_treat_as": out.get("must_not_treat_as"),
            "calibrated_status": out.get("calibrated_status"),
        }
    ]
    out["rivals"] = rivals
    if consume_out.get("nuance_envelope"):
        out["nuance_envelope"] = consume_out["nuance_envelope"]
        out["axes_note"] = "single KEEP hit with formal nuance envelope (operating_regime, counter_conditions, pareto_trade_offs)"
    else:
        out["axes_note"] = "single KEEP hit; class and must_not_treat_as are the nuance"
    return out



def epistemic_class(claim: Dict[str, Any]) -> Tuple[str, bool]:
    raw = (claim.get("epistemic_class") or "").strip().lower()
    if raw in EPISTEMIC_CLASSES:
        return raw, False
    return "unknown", True


def load_jsonl(path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if path is None or not getattr(path, "exists", lambda: False)():
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(__import__("json").loads(line))
    return rows


def show_evidence(claim: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    klass, defaulted = epistemic_class(claim)
    page = None
    sp = claim.get("source_path") or ""
    if "#page=" in sp:
        try:
            page = int(sp.split("#page=", 1)[1].split("&", 1)[0])
        except ValueError:
            page = None
    return {
        "item_id": claim.get("item_id"),
        "claim_text": claim.get("claim_text"),
        "epistemic_class": klass,
        "epistemic_class_defaulted": defaulted,
        "class_meaning": CLASS_MEANING[klass],
        "evidence_span": claim.get("evidence_span") or "",
        "source_path": sp,
        "page": page,
        "source_hash_claimed": claim.get("source_hash"),
        "source": source,
        "falsifier": claim.get("falsifier"),
        "license_class": claim.get("license_class"),
        "primary_or_secondary": claim.get("source_role") if claim.get("source_role") in ("primary", "secondary", "tertiary") else "unknown",
    }


def show_conflicts(
    item_id: str,
    claim: Dict[str, Any],
    all_claims: List[Dict[str, Any]],
    retractions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    explicit = list(claim.get("conflicts_with") or [])
    related = list(claim.get("related_claims") or [])
    retraction_hits = [
        {
            "retracted_item_id": r.get("retracted_item_id"),
            "superseded_by": r.get("superseded_by"),
            "reason": r.get("reason"),
        }
        for r in retractions
        if r.get("superseded_by") == item_id or r.get("retracted_item_id") == item_id
    ]
    same_task = []
    task = claim.get("task")
    if task:
        for other in all_claims:
            oid = other.get("item_id")
            if oid == item_id:
                continue
            if other.get("task") == task:
                same_task.append(oid)
    return {
        "item_id": item_id,
        "conflicts": explicit,
        "related_claims": related,
        "retractions": retraction_hits,
        "same_task_ids": same_task,
        "note": (
            "Empty conflicts means none were recorded, not that sources agree. "
            "Vendor agreement is not a conflict resolution."
        ),
    }


def show_history(
    item_id: str,
    claim: Dict[str, Any],
    retractions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    supersedes = claim.get("supersedes") or []
    events = []
    gate = claim.get("gate") or {}
    if claim.get("created_at"):
        events.append({"at": claim["created_at"], "event": "created"})
    if gate.get("human_approved_at"):
        events.append(
            {
                "at": gate["human_approved_at"],
                "event": "human_approved",
                "by": gate.get("human_approved_by"),
            }
        )
    for r in retractions:
        if r.get("retracted_item_id") == item_id or r.get("superseded_by") == item_id:
            events.append(
                {
                    "at": r.get("retracted_at"),
                    "event": "retraction" if r.get("retracted_item_id") == item_id else "superseded_prior",
                    "retracted_item_id": r.get("retracted_item_id"),
                    "superseded_by": r.get("superseded_by"),
                    "reason": r.get("reason"),
                }
            )
    events.sort(key=lambda e: e.get("at") or "")
    return {
        "item_id": item_id,
        "supersedes": supersedes,
        "events": events,
        "temporal_validity": claim.get("valid_as_of"),
        "expires": (claim.get("freshness") or {}).get("expires") if isinstance(claim.get("freshness"), dict) else claim.get("expires"),
    }


def explain_uncertainty(
    claim: Dict[str, Any],
    conflicts: Dict[str, Any],
    history: Dict[str, Any],
    source: Dict[str, Any],
) -> Dict[str, Any]:
    klass, defaulted = epistemic_class(claim)
    missing = []
    if defaulted:
        missing.append("epistemic_class missing or invalid; defaulted to unknown")
    if not source.get("exists_locally"):
        missing.append("source artifact missing on disk")
    if source.get("exists_locally") and source.get("hash_matches_claim") is False:
        missing.append("source hash does not match claimed hash")
    if not (claim.get("evidence_span") or "").strip():
        missing.append("evidence_span empty")
    if not conflicts.get("conflicts") and not conflicts.get("retractions"):
        missing.append("no recorded dissent; independence untested")
    if klass != "replicated":
        missing.append("not independently reproduced by this lab")
    if klass == "reported":
        missing.append("single cited source; not source-independent")
    return {
        "item_id": claim.get("item_id"),
        "claim_text": claim.get("claim_text"),
        "epistemic_class": klass,
        "epistemic_class_defaulted": defaulted,
        "means": CLASS_MEANING[klass],
        "must_not_treat_as": CLASS_NOT[klass],
        "what_would_falsify": claim.get("falsifier"),
        "what_would_raise_class": {
            "reported": "a lab observation or independent replication of the same quantity",
            "observed": "a second independent reproduction",
            "derived": "direct measurement of the derived quantity",
            "replicated": "nothing to raise; watch for contesting evidence",
            "contested": "resolution with primary artifacts from disagreeing sources",
            "superseded": "nothing; use the successor",
            "unknown": "a primary source and a testable falsifier",
        }[klass],
        "conflicts_recorded": bool(conflicts.get("conflicts") or conflicts.get("retractions")),
        "history_events": len(history.get("events") or []),
        "gaps": missing,
        "unknowns_stay_unknown": True,
    }


def bundle_issues(claims: List[Dict[str, Any]], get_source) -> List[Dict[str, Any]]:
    """Return verification failures. Empty list means the bundle is structurally sound."""
    issues = []
    seen = set()
    for claim in claims:
        iid = claim.get("item_id")
        if not iid:
            issues.append({"item_id": None, "error": "missing item_id"})
            continue
        if iid in seen:
            issues.append({"item_id": iid, "error": "duplicate item_id in bundle"})
        seen.add(iid)
        for field in ("claim_text", "falsifier", "source_path"):
            if not (claim.get(field) or "").strip():
                issues.append({"item_id": iid, "error": f"missing {field}"})
        if len((claim.get("falsifier") or "").strip()) < 10:
            issues.append({"item_id": iid, "error": "falsifier too short"})
        klass = (claim.get("epistemic_class") or "").strip().lower()
        if klass and klass not in EPISTEMIC_CLASSES:
            issues.append({"item_id": iid, "error": f"invalid epistemic_class {klass}"})
        klass_eff, _ = epistemic_class(claim)
        # Unknown support is not an exemption from artifact integrity checks.
        src = get_source(iid)
        if not src.get("exists_locally"):
            issues.append({"item_id": iid, "error": "source missing on disk", "path": src.get("path")})
        elif src.get("hash_matches_claim") is False:
            issues.append({"item_id": iid, "error": "source hash mismatch"})
        path = src.get("path")
        if src.get("exists_locally") and path and str(path).lower().endswith(".pdf"):
            try:
                text = pdf_plain_text(path)
            except Exception as exc:
                issues.append({"item_id": iid, "error": f"pdf read failed: {exc}"})
            else:
                if not (text or "").strip():
                    issues.append({"item_id": iid, "error": "PDF has no extractable text"})
                elif not span_in_text(claim.get("evidence_span") or "", text):
                    issues.append({"item_id": iid, "error": "evidence_span not in source PDF"})
    return issues


# ==============================================================================
# 11-FIELD MACHINE-VERIFIABLE EVIDENCE RECEIPT
# ==============================================================================
from dataclasses import asdict, dataclass, field


@dataclass
class EvidenceReceipt:
    """11-field machine-verifiable evidence receipt ensuring tamper-evident, falsifiable provenance."""

    receipt_id: str
    calibrated_status: str
    claim_type: str
    truth_test_applied: str

    # 1. Exact claim text and scope
    exact_claim_and_scope: Dict[str, str]

    # 2. Date, population, units, and assumptions
    context_parameters: Dict[str, Any]

    # 3. Source artifact and SHA-256 hash
    source_artifact: Dict[str, str]

    # 4. Exact quotation, table, figure, dataset row, or code reference
    exact_reference: Dict[str, str]

    # 5. Provenance and source-independence graph
    provenance_graph: Dict[str, Any]

    # 6. Computation and transformation history
    computation_history: List[Dict[str, Any]]

    # 7. Reproduction environment and results
    reproduction: Dict[str, Any]

    # 8. Supporting and contradicting evidence
    evidence_balance: Dict[str, Any]

    # 9. Reviewer identities or cryptographic identities
    reviewers: List[Dict[str, str]]

    # 10. Falsifier or acceptance condition
    falsification_criteria: Dict[str, str]

    # 11. Version, expiration, correction, and retraction history
    lifecycle_history: Dict[str, Any]

    schema_version: str = "ssr-evidence-receipt-v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

