"""Bounded, read-only discovery of the guided demo's local execution records.

This is storage/selection validation, not a new evaluator. The caller supplies
the unchanged regression assessment and the four bundled prepared artifacts.
"""
import json
from datetime import datetime
import os
from pathlib import Path
import re
import stat

from intent_replay.benchmark_cases import PROFILE, check_seal, digest
from intent_replay.benchmark_execution import validate_prepared
from intent_replay.evidence_handoff import MAX_REPORT_BYTES


ID_PATTERN = re.compile(r"[a-f0-9]{32}\Z")
HASH_PATTERN = re.compile(r"[a-f0-9]{64}\Z")
LIST_LIMIT = 20
SCAN_LIMIT = 200


def _identifier(value):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError("Invalid saved execution identifier.")
    return value


def _regular(info):
    return (stat.S_ISREG(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _finite(unused):
    raise ValueError("Saved report contains non-finite JSON values.")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Saved report contains duplicate JSON keys.")
        result[key] = value
    return result


def read_report(path):
    """Do not follow links or read past the bound, including a file-size race."""
    try:
        before = path.lstat()
        if not _regular(before):
            raise ValueError("Saved report is not a regular, non-linked file.")
        if before.st_size > MAX_REPORT_BYTES:
            raise ValueError("Saved report exceeds the 8 MB bound.")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not _regular(opened) or _identity(opened) != _identity(before):
                raise ValueError("Saved report changed while opening it.")
            raw = stream.read(MAX_REPORT_BYTES + 1)
            after = os.fstat(stream.fileno())
        latest = path.lstat()
        if (not _regular(latest) or _identity(after) != _identity(before)
                or _identity(latest) != _identity(before)):
            raise ValueError("Saved report changed while reading it.")
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError("Saved report exceeds the 8 MB bound.")
        result = json.loads(raw.decode("utf-8"), parse_constant=_finite, object_pairs_hook=_unique)
        # JSON accepts escaped lone surrogates; the response must also be finite
        # UTF-8 JSON without relying on an eventual framework serialization error.
        json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if not isinstance(result, dict):
            raise ValueError("Saved report must be a JSON object.")
        return result
    except FileNotFoundError:
        raise FileNotFoundError("Saved execution report was not found.") from None
    except (UnicodeError, RecursionError, json.JSONDecodeError):
        raise ValueError("Saved report is not readable bounded UTF-8 JSON.") from None
    except OSError:
        raise ValueError("Saved report could not be read safely.") from None


class ReplayHistory:
    def __init__(self, output, supported, regression_result):
        self.output = Path(output)
        # Bind once to server-held, validated, bundled capture objects. No client
        # can supply a replacement artifact or expand the allowed case set.
        self.supported = {}
        for key, prepared in supported.items():
            validate_prepared(prepared)
            self.supported[key] = digest(prepared)
        self.regression_result = regression_result

    def _load(self, identifier, expected_sha256=None):
        identifier = _identifier(identifier)
        report = read_report(self.output / (identifier + ".json"))
        try:
            check_seal(report)
            if report.get("execution_id") != identifier:
                raise ValueError("Saved report identity does not match its filename.")
            if expected_sha256 is not None and report.get("sha256") != expected_sha256:
                raise ValueError("Saved report binding changed; refresh the saved replay list.")
            if (report.get("schema_version") != 7 or report.get("report_type") != "proposal_execution_comparison"
                    or report.get("profile") != PROFILE or not isinstance(report.get("created_at"), str)
                    or not report["created_at"] or not isinstance(report.get("runtime"), dict)
                    or report["runtime"].get("location") != "local"
                    or type(report["runtime"].get("model_requests")) is not int
                    or report["runtime"]["model_requests"] != 0):
                raise ValueError("Saved report is not a supported zero-inference local execution.")
            try:
                recorded_at = datetime.fromisoformat(report["created_at"])
                if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
                    raise ValueError("Timestamp has no timezone.")
            except ValueError:
                raise ValueError("Saved execution timestamp must be an ISO timestamp with timezone.") from None
            prepared = report["prepared"]
            validate_prepared(prepared)
            case_id, provider = prepared["case"]["case_id"], prepared["capture"]["target"]["provider"]
            if self.supported.get((case_id, provider)) != digest(prepared):
                raise ValueError("Saved report is not bound to one of the current four included proposals.")
            if (report.get("experiment_id") != prepared["experiment_id"]
                    or not isinstance(report.get("revalidation"), dict)
                    or report["revalidation"].get("original_prepared_sha256") != prepared["sha256"]):
                raise ValueError("Saved report does not bind its prepared artifact and revalidation.")
            regression = self.regression_result(report, prepared)
            if regression["status"] not in ("PASS", "FAIL"):
                raise ValueError("Saved regression assessment is incomplete; original evidence is retained.")
            source = {"execution_id": identifier, "report_sha256": report["sha256"],
                      "prepared_sha256": prepared["sha256"], "case_id": case_id,
                      "provider": provider, "created_at": report["created_at"]}
            return {"view_mode": "saved", "source": source, "report": report,
                    "regression": regression, "new_model_requests": 0, "new_executions": 0}
        except (KeyError, TypeError, AttributeError, IndexError, RecursionError):
            raise ValueError("Saved report has invalid or incomplete execution evidence.") from None

    def open(self, identifier, expected_sha256):
        if not isinstance(expected_sha256, str) or not HASH_PATTERN.fullmatch(expected_sha256):
            raise ValueError("The exact saved report SHA-256 binding is required.")
        return self._load(identifier, expected_sha256)

    def list(self):
        candidates, scanned, truncated = [], 0, False
        try:
            with os.scandir(self.output) as entries:
                for entry in entries:
                    if scanned == SCAN_LIMIT:
                        truncated = True
                        break
                    scanned += 1
                    if not entry.name.endswith(".json") or not ID_PATTERN.fullmatch(entry.name[:-5]):
                        continue
                    try:
                        modified = entry.stat(follow_symlinks=False).st_mtime_ns
                    except OSError:
                        modified = 0
                    candidates.append((modified, entry.name[:-5]))
        except FileNotFoundError:
            pass
        except OSError:
            raise ValueError("Saved replay directory could not be inspected safely.") from None
        rows = []
        for _, identifier in sorted(candidates, reverse=True)[:LIST_LIMIT]:
            row = dict(execution_id=identifier, status="error", created_at=None, case_id=None,
                       provider=None, report_sha256=None, prepared_sha256=None, regression_status=None,
                       regression_exit_code=None, can_open=False, can_rerun=False, error=None)
            try:
                saved = self._load(identifier)
                row.update(saved["source"], status="ready", regression_status=saved["regression"]["status"],
                           regression_exit_code=saved["regression"]["exit_code"], can_open=True, can_rerun=True)
            except (ValueError, FileNotFoundError) as exc:
                row["error"] = str(exc)[:300]
            rows.append(row)
        return {"schema_version": "saved-local-replay-history-v1", "items": rows,
                "limit": LIST_LIMIT, "scan_limit": SCAN_LIMIT, "scanned_entries": scanned,
                "candidate_count": len(candidates), "returned_count": len(rows),
                "scan_truncated": truncated, "has_more": truncated or len(candidates) > LIST_LIMIT,
                "ordering": "filesystem-modified-desc-within-bounded-scan"}
