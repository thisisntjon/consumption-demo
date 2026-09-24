"""Read-only, bounded transport check of one caller-pinned shared V0 packet.

This checks the envelope and directly listed bytes, not dependency closure,
logical-revision resolution, V1 task semantics, current authority or acceptance.
"""

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import stat


MAX_PACKET = 1_048_576
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError("expected lowercase SHA-256 digest")
    return value


def _reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400)


def _safe_file(root, name):
    if not isinstance(name, str) or not name:
        raise ValueError("path must be a nonempty string")
    parts = name.split("/")
    if (any(c in name for c in '\\<>:"|?*') or any(ord(c) < 32 for c in name)
            or PureWindowsPath(name).drive
            or any(p in {"", ".", ".."} or p.endswith((".", " "))
                   or PureWindowsPath(p).is_reserved() for p in parts)):
        raise ValueError("unsafe relative POSIX path")
    target = root
    for part in parts:
        target /= part
        if _reparse(target):
            raise ValueError("symlink/reparse path is unsupported")
    target.resolve(strict=True).relative_to(root)
    if not stat.S_ISREG(target.stat().st_mode):
        raise ValueError("path must name a regular file")
    return target


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject(value):
        raise ValueError("V0 requires integer-only numeric encoding")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_float=reject, parse_constant=reject)


def check_packet(root, packet, expected_sha256):
    """No writes, discovery, subprocesses, implicit revision or historical lookup."""
    result = {
        "schema_version": "consumption-packet-check-v1",
        "integrity": "failed", "accepted_use": False, "errors": [], "files": [],
        "scope": "pinned V0 envelope and direct file bytes only",
        "limits": ["No dependency closure or logical-revision resolution",
                   "No V1 assignment/recipient validation or acknowledgment",
                   "No currentness, authenticated author, acceptance or truth check",
                   "Observed reads are not an atomic snapshot against concurrent writers"],
    }
    try:
        _digest(expected_sha256)
        root = Path(root).absolute()
        for ancestor in (*reversed(root.parents), root):
            if _reparse(ancestor):
                raise ValueError("root ancestry contains symlink/reparse point")
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("root must be a directory")
        target = _safe_file(root, packet)
        with target.open("rb") as stream:
            raw = stream.read(MAX_PACKET + 1)
        if len(raw) > MAX_PACKET:
            raise ValueError("packet exceeds 1 MiB")
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("packet SHA-256 differs from caller pin")
        native = _json(raw)
        if not isinstance(native, dict):
            raise ValueError("packet must be an object")
        if native.get("schema_version") != "ssr-shared-v0":
            raise ValueError("unsupported packet schema")
        digest = _digest(native.get("content_sha256"))
        canonical = json.dumps({k: v for k, v in native.items() if k != "content_sha256"},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                               allow_nan=False).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != digest:
            raise ValueError("canonical envelope hash mismatch")
        for key in ("logical_id", "producer_node", "created_at", "status", "object_type"):
            if not isinstance(native.get(key), str) or not native[key].strip():
                raise ValueError(f"{key} must be a nonblank string")
        created = datetime.fromisoformat(native["created_at"].replace("Z", "+00:00"))
        if created.utcoffset() != timedelta(0):
            raise ValueError("created_at must have UTC offset")
        for key in ("dependency_references", "payload_paths", "limitations"):
            if not isinstance(native.get(key), list):
                raise ValueError(f"{key} must be an array")
        if not all(isinstance(x, str) for x in native["limitations"]):
            raise ValueError("limitations must contain strings")
        if not isinstance(native.get("data"), dict):
            raise ValueError("data must be an object")
        # Preserve qualifiers verbatim; returning them never executes their contents.
        result["native"] = native
        payloads = native["payload_paths"]
        entries = native["data"].get("files", [])
        dependencies = native["dependency_references"]
        if not isinstance(entries, list) or len(entries) + len(dependencies) > 512:
            raise ValueError("unsupported files list or more than 512 direct references")
        if not all(isinstance(p, str) for p in payloads):
            raise ValueError("payload_paths must contain strings")
        if len(set(p.casefold() for p in payloads)) != len(payloads):
            raise ValueError("duplicate payload path")
        if (not all(isinstance(e, dict) and isinstance(e.get("path"), str) for e in entries)
                or len({e["path"].casefold() for e in entries}) != len(entries)
                or {e["path"] for e in entries} != set(payloads)):
            raise ValueError("data.files must cover payload_paths exactly once")
        total = 0
        for kind, records in (("dependency", dependencies), ("payload", entries)):
            for index, entry in enumerate(records):
                checked = {"kind": kind, "index": index, "match": False}
                result["files"].append(checked)
                try:
                    if total > MAX_TOTAL:
                        raise ValueError("direct read budget already exceeded")
                    if not isinstance(entry, dict):
                        raise ValueError("reference must be an object")
                    if kind == "dependency":
                        if not isinstance(entry.get("logical_id"), str) or not entry["logical_id"].strip():
                            raise ValueError("dependency logical_id is required")
                        if "path" not in entry or "sha256" not in entry:
                            raise ValueError("revision-only dependency requires external resolution; unsupported")
                        checked["logical_id"] = entry["logical_id"]
                    checked["path"] = entry.get("path")
                    expected = _digest(entry.get("sha256"))
                    file = _safe_file(root, entry.get("path"))
                    expected_size = entry.get("bytes")
                    if kind == "payload" and (type(expected_size) is not int or expected_size < 0):
                        raise ValueError("payload bytes must be a nonnegative integer")
                    digest = hashlib.sha256()
                    size = 0
                    with file.open("rb") as stream:
                        while True:
                            # One extra byte distinguishes the exact cap from overflow.
                            chunk = stream.read(min(1024 * 1024, MAX_FILE - size + 1,
                                                    MAX_TOTAL - total + 1))
                            if not chunk:
                                break
                            size += len(chunk)
                            total += len(chunk)
                            if size > MAX_FILE or total > MAX_TOTAL:
                                raise ValueError("direct read exceeds 64 MiB/file or 256 MiB total")
                            digest.update(chunk)
                    checked.update(observed_sha256=digest.hexdigest(), observed_bytes=size)
                    if digest.hexdigest() != expected:
                        raise ValueError("file hash mismatch (missing historical version or changed bytes)")
                    if kind == "payload" and size != expected_size:
                        raise ValueError("payload size mismatch")
                    checked["match"] = True
                except (ValueError, OSError, RuntimeError) as exc:
                    checked["error"] = str(exc)
                    result["errors"].append(f"{kind}[{index}]: {exc}")
        if not result["errors"]:
            result["integrity"] = "direct_files_match"
    except (ValueError, OSError, RuntimeError, RecursionError) as exc:
        result["errors"].append(str(exc))
    return result
