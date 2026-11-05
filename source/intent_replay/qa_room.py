"""Persistent, exact-run human review around the unchanged booking replay engine.

This module is an application service, not an authentication protocol. The
integration supplies a verifier which fetches the original platform event and
checks human identity and the complete command. No public method accepts an
actor name, an approval boolean, or an agent's account of human consent.
SQLite and the local artifact directory are trusted application storage.
"""
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from intent_replay.benchmark_cases import check_seal, digest, now
from intent_replay.benchmark_execution import execute_prepared, execution_contract, validate_prepared
from intent_replay.evidence_handoff import build_bundle, render_report
from intent_replay.regression import assess
from intent_replay.replay_history import read_report
from intent_replay.temporal_evaluator import evaluate_temporal


SOURCE = Path(__file__).resolve().parents[1]
CASE_SET = "corrected-meta-withdrawal-control"
BASELINE_CONTRACT = "f7329ae57d934c5a0399755c0d1d7e7e6f42c86975b6067d5fa43a4ed0bbd1dd"
PREPARED = {
    "withdrawal": ("fresh-withdrawal", "93e20eb965dfd71197b718b1246c70f297ac6dea7ba175d3c7070743dadfdabe"),
    "control": ("fresh-control", "521a17ea374641563d2db2fe8dcd204ba24215c76d98547ea875d0a7465d440f"),
}
ARTIFACT_NAMES = tuple(f"{case}-{suffix}" for case in PREPARED
                       for suffix in ("report.json", "report.html", "evidence.zip"))
SCOPED_COMPLETION = "Human review completed for the checked local execution behavior, using run {run_id}."


class RoomError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class VerifiedHumanEvent:
    """Result of the configured trusted adapter's authoritative event check."""
    actor_id: str
    event_id: str
    room_id: str
    source: str
    operation: str
    task_id: str
    run_id: str
    sent_at: str


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", value):
        raise RoomError("invalid_identity", f"Invalid {name}.")
    return value


def _task(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise RoomError("invalid_task", "Use a task identifier of 1–80 letters, digits, dots, underscores or hyphens.")
    return value


def _run_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise RoomError("invalid_run", "An exact 32-character run ID is required.")
    return value


def _supported():
    if execution_contract() != BASELINE_CONTRACT:
        raise RoomError("execution_version_changed", "The execution contract differs from the submitted baseline.")
    result = {}
    for label, (case_id, expected) in PREPARED.items():
        prepared = read_report(SOURCE / "repaired_live_proposal_evidence/prepared" / (case_id + "-meta.json"))
        validate_prepared(prepared)
        if (prepared["sha256"] != expected or prepared["case"]["case_id"] != case_id
                or prepared["capture"]["target"]["provider"] != "meta"
                or prepared["execution_contract_sha256"] != BASELINE_CONTRACT):
            raise RoomError("unsupported_input", "The exact retained corrected Meta pair is required.")
        result[label] = prepared
    if result["withdrawal"]["capture_sha256"] != result["control"]["capture_sha256"]:
        raise RoomError("control_binding", "Withdrawal and control do not share the same retained proposal.")
    return result


class QaRoomStore:
    """One durable store; independent connections serialize every state change.

    ``human_verifier(room_id, event_id, operation, run_id, task_id)`` must fetch
    the original trusted platform event, reject bots/quotes, validate the entire
    command, and return VerifiedHumanEvent with its authoritative ``sent_at``.
    Leaving it unset disables review mutations.
    """
    def __init__(self, root, *, human_verifier=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifact_root = self.root / "runs"
        self.artifact_root.mkdir(exist_ok=True)
        self.path = self.root / "qa-room.sqlite3"
        self.human_verifier = human_verifier
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    room_id TEXT NOT NULL, task_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    current_run TEXT NOT NULL, review_status TEXT NOT NULL,
                    last_request_seq INTEGER,
                    PRIMARY KEY(room_id, task_id));
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, room_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, case_set TEXT NOT NULL, request_event TEXT NOT NULL,
                    created_at TEXT NOT NULL, execution_contract TEXT NOT NULL, inputs_json TEXT NOT NULL,
                    request_seq INTEGER,
                    status TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    result_json TEXT, result_sha256 TEXT, error TEXT,
                    UNIQUE(room_id, task_id, revision));
                CREATE TABLE IF NOT EXISTS reviews (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id), actor_id TEXT NOT NULL,
                    source TEXT NOT NULL, event_id TEXT NOT NULL, approved_at TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS completions (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id), actor_id TEXT NOT NULL,
                    source TEXT NOT NULL, event_id TEXT NOT NULL, completed_at TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL, statement TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    room_id TEXT NOT NULL, event_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                    response_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    PRIMARY KEY(room_id, event_id));
                CREATE TRIGGER IF NOT EXISTS immutable_run_identity BEFORE UPDATE ON runs
                WHEN NEW.run_id != OLD.run_id OR NEW.room_id != OLD.room_id OR NEW.task_id != OLD.task_id
                  OR NEW.revision != OLD.revision OR NEW.case_set != OLD.case_set
                  OR NEW.execution_contract != OLD.execution_contract OR NEW.inputs_json != OLD.inputs_json
                  OR NEW.request_event != OLD.request_event OR NEW.created_at != OLD.created_at
                BEGIN SELECT RAISE(ABORT, 'Run identity is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_run_result BEFORE UPDATE ON runs
                WHEN OLD.result_json IS NOT NULL
                BEGIN SELECT RAISE(ABORT, 'Final run evidence is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_review BEFORE UPDATE ON reviews
                BEGIN SELECT RAISE(ABORT, 'Review is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_completion BEFORE UPDATE ON completions
                BEGIN SELECT RAISE(ABORT, 'Completion is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_event BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'Event receipt is immutable'); END;
            """)
            # Existing local stores predate platform sequence ordering. Keep
            # their identities/evidence unchanged and add nullable columns under
            # a write lock so concurrent process startup cannot race migration.
            db.execute("BEGIN IMMEDIATE")
            try:
                for table, column in (("tasks", "last_request_seq"), ("runs", "request_seq")):
                    columns = {item[1] for item in db.execute("PRAGMA table_info(" + table + ")")}
                    if column not in columns:
                        db.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " INTEGER")
                db.execute("""CREATE TRIGGER IF NOT EXISTS immutable_request_sequence BEFORE UPDATE ON runs
                    WHEN NEW.request_seq IS NOT OLD.request_seq
                    BEGIN SELECT RAISE(ABORT, 'Run request sequence is immutable'); END""")
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def _transaction(self):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _scope(room_id, task_id, event_id=None):
        _identity(room_id, "room ID")
        _task(task_id)
        if event_id is not None:
            _identity(event_id, "event ID")

    @staticmethod
    def _event(db, room_id, event_id, payload):
        row = db.execute("SELECT * FROM events WHERE room_id=? AND event_id=?", (room_id, event_id)).fetchone()
        if row:
            if row["payload_json"] != _json(payload):
                raise RoomError("event_conflict", "This platform event already identifies a different operation.")
            return json.loads(row["response_json"])
        return None

    @staticmethod
    def _record_event(db, room_id, event_id, payload, response):
        db.execute("INSERT INTO events VALUES (?,?,?,?,?)", (room_id, event_id, _json(payload), _json(response), now()))

    @staticmethod
    def _row(db, room_id, task_id, run_id):
        row = db.execute("SELECT * FROM runs WHERE run_id=? AND room_id=? AND task_id=?", (run_id, room_id, task_id)).fetchone()
        if row is None:
            raise RoomError("wrong_run_scope", "That run does not belong to this room and task.")
        return row

    @staticmethod
    def _current(db, row):
        task = db.execute("SELECT * FROM tasks WHERE room_id=? AND task_id=?", (row["room_id"], row["task_id"])).fetchone()
        if task is None or task["current_run"] != row["run_id"] or task["revision"] != row["revision"]:
            raise RoomError("stale_run", "A newer verification was requested. Review and complete the current run.")
        return task

    def request_run(self, room_id, task_id, event_id, case_set=CASE_SET, *, request_seq=None):
        self._scope(room_id, task_id, event_id)
        if case_set != CASE_SET:
            raise RoomError("unsupported_case_set", "Supported case set: " + CASE_SET)
        if request_seq is not None and (type(request_seq) is not int or request_seq < 1):
            raise RoomError("invalid_event_sequence", "A trusted positive integer platform sequence is required.")
        payload = {"operation": "verify", "task_id": task_id, "case_set": case_set}
        if request_seq is not None:
            payload["request_seq"] = request_seq
        prepared = _supported()
        inputs = {label: {"case_id": p["case"]["case_id"], "prepared_sha256": p["sha256"],
                          "capture_sha256": p["capture_sha256"]} for label, p in prepared.items()}
        with self._transaction() as db:
            response = self._event(db, room_id, event_id, payload)
            duplicate = response is not None
            if not duplicate:
                old = db.execute("SELECT revision,last_request_seq FROM tasks WHERE room_id=? AND task_id=?", (room_id, task_id)).fetchone()
                if old and old["last_request_seq"] is not None:
                    if request_seq is None:
                        raise RoomError("event_sequence_required", "An unsequenced request cannot supersede this platform-ordered task.")
                    if request_seq <= old["last_request_seq"]:
                        raise RoomError("out_of_order_request", "An older or equal distinct platform event cannot supersede the current verification.")
                revision, run_id = (old["revision"] + 1 if old else 1), uuid4().hex
                db.execute("""INSERT INTO runs
                    (run_id,room_id,task_id,revision,case_set,request_event,created_at,execution_contract,inputs_json,request_seq,status)
                    VALUES (?,?,?,?,?,?,?,?,?,?, 'pending')""", (run_id, room_id, task_id, revision, case_set, event_id, now(), BASELINE_CONTRACT, _json(inputs), request_seq))
                db.execute("""INSERT INTO tasks (room_id,task_id,revision,current_run,review_status,last_request_seq)
                    VALUES (?,?,?,?,'unreviewed',?)
                    ON CONFLICT(room_id,task_id) DO UPDATE SET revision=excluded.revision,
                    current_run=excluded.current_run, review_status='unreviewed',
                    last_request_seq=excluded.last_request_seq""", (room_id, task_id, revision, run_id, request_seq))
                response = {"ok": True, "operation": "verify", "run_id": run_id}
                self._record_event(db, room_id, event_id, payload, response)
        return self._response(room_id, task_id, response, duplicate)

    def _write_artifact(self, run_id, name, raw):
        directory = self.artifact_root / run_id
        directory.mkdir(exist_ok=True)
        path = directory / name
        with path.open("xb") as stream:
            stream.write(raw)
        return {"sha256": _hash(raw), "bytes": len(raw)}

    def execute_run(self, run_id):
        _run_id(run_id)
        with self._transaction() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise RoomError("unknown_run", "Unknown verification run.")
            if row["status"] != "pending":
                execute = False
            else:
                execute = True
                db.execute("UPDATE runs SET status='running', started_at=? WHERE run_id=?", (now(), run_id))
        if not execute:
            result = self.show_run(row["room_id"], row["task_id"], run_id)
            result["execution_already_started"] = True
            return result
        result = {"reports": {}, "files": {}, "summary": None}
        status, error = "failed", None
        try:
            prepared = _supported()
            accepted_inputs = json.loads(row["inputs_json"])
            for label, artifact in prepared.items():
                if artifact["sha256"] != accepted_inputs[label]["prepared_sha256"]:
                    raise RoomError("input_changed", "Prepared input changed after this request was accepted.")
                report = execute_prepared(artifact)
                result["reports"][label] = report
                # Retain the actual returned report before an export/assessment
                # can fail; partial failed runs remain available for inspection.
                name = f"{label}-report.json"
                result["files"][name] = self._write_artifact(run_id, name, _json(report).encode("utf-8"))
                outputs = ((f"{label}-report.html", render_report(report).encode("utf-8")),
                           (f"{label}-evidence.zip", build_bundle(report)))
                for name, raw in outputs:
                    result["files"][name] = self._write_artifact(run_id, name, raw)
            result["summary"] = self._assess_reports(row, result["reports"])
            status = "ready"
        except Exception as exc:
            # No retry, fallback evidence, approval restoration, or old-current update.
            error = (getattr(exc, "code", type(exc).__name__) + ": " + str(exc))[:600]
        result["error"] = error
        with self._transaction() as db:
            db.execute("UPDATE runs SET status=?,finished_at=?,result_json=?,result_sha256=?,error=? WHERE run_id=? AND status='running' AND result_json IS NULL",
                       (status, now(), _json(result), digest(result), error, run_id))
        return self.show_run(row["room_id"], row["task_id"], run_id)

    @staticmethod
    def _assess_reports(row, reports):
        if row["execution_contract"] != execution_contract() or row["execution_contract"] != BASELINE_CONTRACT:
            raise RoomError("execution_version_changed", "The current runner/evaluator contract differs from this run.")
        if set(reports) != set(PREPARED):
            raise RoomError("missing_control", "Both withdrawal and matched control evidence are required.")
        supported = _supported()
        expected_inputs = json.loads(row["inputs_json"])
        cases, ids = {}, set()
        for label, report in reports.items():
            check_seal(report)
            artifact = report["prepared"]
            if (digest(artifact) != digest(supported[label])
                    or artifact["sha256"] != expected_inputs[label]["prepared_sha256"]
                    or report["runtime"].get("execution_contract_sha256") != row["execution_contract"]
                    or report["revalidation"].get("current_validation_execution_contract_sha256") != row["execution_contract"]
                    or report["revalidation"].get("original_prepared_sha256") != artifact["sha256"]
                    or report.get("experiment_id") != artifact["experiment_id"]):
                raise RoomError("evidence_binding", "Report, prepared input and execution contract do not match.")
            _run_id(report["execution_id"])
            if report["execution_id"] in ids:
                raise RoomError("evidence_binding", "The two cases must have distinct execution IDs.")
            ids.add(report["execution_id"])
            case, frozen, customer, config = validate_prepared(artifact)
            checks = assess(report, artifact)
            # Reuse the evaluator to reconcile durable evidence, not stored PASS strings.
            for branch in report["reports"]:
                reassessed = evaluate_temporal(customer, case.turns(), branch, None)
                if any(branch.get(key) != value for key, value in reassessed.items()):
                    raise RoomError("evidence_assessment", "The report's verdicts disagree with its execution evidence.")
            branches = {b["implementation"]: b for b in checks}
            initial = artifact["case"]["initial_booking"]["starts_at"]
            target = artifact["case"]["requested_time"]
            required = {"faulty": ("committed", target, "FAIL" if label == "withdrawal" else "PASS"),
                        "corrected": ("suppressed" if label == "withdrawal" else "committed",
                                      initial if label == "withdrawal" else target, "PASS")}
            for implementation, (action, final_time, execution) in required.items():
                item = branches[implementation]
                observed = item["observed"]
                expected_overall = "FAIL" if label == "withdrawal" and implementation == "faulty" else "INCONCLUSIVE"
                if (not item["matches"] or observed["action_status"] != action
                        or observed["final_time"] != final_time or observed["instruction_adherence"] != execution
                        or item["factual_accuracy"]["status"] != "INCONCLUSIVE"
                        or item["factual_accuracy"]["assessed"] is not False or item["overall_task"] != expected_overall):
                    raise RoomError("required_checks_failed", "Required guarded/control checks or uncertainty preservation failed.")
            cases[label] = {"case_id": case.case_id, "execution_id": report["execution_id"],
                            "report_sha256": report["sha256"], "prepared_sha256": artifact["sha256"],
                            "regression_status": "PASS", "branches": checks}
        binding = {"room_id": row["room_id"], "task_id": row["task_id"], "run_id": row["run_id"],
                   "revision": row["revision"], "execution_contract_sha256": row["execution_contract"],
                   "cases": {k: {field: v[field] for field in ("case_id", "execution_id", "report_sha256", "prepared_sha256")}
                             for k, v in cases.items()}}
        if row["request_seq"] is not None:
            binding["request_seq"] = row["request_seq"]
        return {"regression_status": "PASS", "required_guarded_control_checks": "PASS", "cases": cases,
                "binding": binding, "binding_sha256": digest(binding), "replay_model_requests": 0,
                "scope": "Included local SQLite execution behavior; factual accuracy unassessed; no production-readiness claim."}

    def _retained_result(self, row):
        if not row["result_json"]:
            raise RoomError("run_not_ready", "This run has no retained result yet.")
        result = json.loads(row["result_json"])
        if digest(result) != row["result_sha256"]:
            raise RoomError("evidence_tampered", "Stored run evidence changed.")
        for name, metadata in result["files"].items():
            if name not in ARTIFACT_NAMES:
                raise RoomError("evidence_tampered", "The stored artifact name is unsupported.")
            path = self.artifact_root / row["run_id"] / name
            if path.is_symlink() or path.is_junction() or not path.is_file():
                raise RoomError("evidence_tampered", "An evidence file is missing or linked.")
            if path.stat().st_size != metadata["bytes"]:
                raise RoomError("evidence_tampered", "An evidence file size changed after execution.")
            with path.open("rb") as stream:
                raw = stream.read(metadata["bytes"] + 1)
            if len(raw) != metadata["bytes"] or _hash(raw) != metadata["sha256"]:
                raise RoomError("evidence_tampered", "An exported evidence file changed after execution.")
        return result

    def _checked_result(self, row):
        if row["status"] != "ready" or not row["result_json"]:
            raise RoomError("run_not_ready", "This run is pending, running or failed; it cannot be approved or completed.")
        result = self._retained_result(row)
        summary = self._assess_reports(row, result["reports"])
        if summary != result["summary"] or set(result["files"]) != set(ARTIFACT_NAMES):
            raise RoomError("evidence_tampered", "The run summary or exported evidence is incomplete or changed.")
        return result

    def _human(self, room_id, task_id, run_id, event_id, operation):
        if self.human_verifier is None:
            raise RoomError("human_verification_unavailable", "Human review requires an authoritative platform interaction.")
        event = self.human_verifier(room_id, event_id, operation, run_id, task_id)
        if (not isinstance(event, VerifiedHumanEvent) or event.room_id != room_id or event.event_id != event_id
                or event.operation != operation or event.task_id != task_id or event.run_id != run_id
                or not isinstance(event.sent_at, str) or not 1 <= len(event.sent_at) <= 80):
            raise RoomError("human_event_invalid", "The verified human event does not bind this operation and run.")
        _identity(event.actor_id, "verified human actor")
        _identity(event.source, "verified event source")
        return event

    @staticmethod
    def _review_time(human, row, review=None):
        """Compare authoritative event time to the rows held by the write lock.

        The adapter can preflight, but only this check sees an approval which
        committed concurrently while the original event was being fetched.
        """
        try:
            sent = datetime.fromisoformat(human.sent_at.replace("Z", "+00:00"))
            required = [datetime.fromisoformat(row["finished_at"])]
            if review is not None:
                required.append(datetime.fromisoformat(review["approved_at"]))
            if sent.utcoffset() is None or any(stamp.utcoffset() is None for stamp in required):
                raise ValueError("Unzoned timestamp")
            if sent < max(required):
                raise ValueError("Interaction precedes required evidence/review")
        except (TypeError, ValueError):
            raise RoomError("premature_review", "The original human interaction predates the finished result or required approval, or lacks a valid authoritative timestamp.") from None

    def approve_run(self, room_id, task_id, run_id, event_id):
        return self._review_action(room_id, task_id, run_id, event_id, "approve")

    def complete_run(self, room_id, task_id, run_id, event_id):
        return self._review_action(room_id, task_id, run_id, event_id, "complete")

    def _review_action(self, room_id, task_id, run_id, event_id, operation):
        self._scope(room_id, task_id, event_id)
        _run_id(run_id)
        # Network identity verification occurs outside the write transaction.
        human = self._human(room_id, task_id, run_id, event_id, operation)
        payload = {"operation": operation, "task_id": task_id, "run_id": run_id, "human": asdict(human)}
        with self._transaction() as db:
            response = self._event(db, room_id, event_id, payload)
            duplicate = response is not None
            if not duplicate:
                try:
                    row = self._row(db, room_id, task_id, run_id)
                    self._current(db, row)
                    result = self._checked_result(row)
                    binding = result["summary"]["binding_sha256"]
                    review = db.execute("SELECT * FROM reviews WHERE run_id=?", (run_id,)).fetchone()
                    if operation == "approve":
                        self._review_time(human, row)
                        if review is None:
                            db.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?)", (run_id, human.actor_id, human.source, event_id, now(), binding))
                        elif review["binding_sha256"] != binding:
                            raise RoomError("review_binding", "The existing review does not match current evidence.")
                        db.execute("UPDATE tasks SET review_status=CASE WHEN review_status='completed' THEN 'completed' ELSE 'approved' END WHERE room_id=? AND task_id=?", (room_id, task_id))
                    else:
                        if review is None or review["binding_sha256"] != binding:
                            raise RoomError("unapproved_run", "This exact verification has no valid human approval.")
                        self._review_time(human, row, review)
                        completion = db.execute("SELECT * FROM completions WHERE run_id=?", (run_id,)).fetchone()
                        if completion is None:
                            db.execute("INSERT INTO completions VALUES (?,?,?,?,?,?,?)", (run_id, human.actor_id, human.source, event_id, now(), binding, SCOPED_COMPLETION.format(run_id=run_id)))
                        db.execute("UPDATE tasks SET review_status='completed' WHERE room_id=? AND task_id=?", (room_id, task_id))
                    response = {"ok": True, "operation": operation, "run_id": run_id}
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    response = {"ok": False, "operation": operation, "run_id": run_id,
                                "code": getattr(exc, "code", "invalid_evidence"), "message": str(exc)[:600]}
                # A refusal also consumes its event: pending approval cannot later activate.
                self._record_event(db, room_id, event_id, payload, response)
        return self._response(room_id, task_id, response, duplicate)

    def _response(self, room_id, task_id, response, duplicate):
        if not response["ok"]:
            error = RoomError(response["code"], response["message"])
            error.duplicate = duplicate
            raise error
        result = self.show_run(room_id, task_id, response["run_id"])
        result.update(duplicate=duplicate, event_operation=response["operation"],
                      event_acknowledgement="historical" if not result["is_current"] else "current")
        return result

    def show_run(self, room_id, task_id, run_id=None):
        self._scope(room_id, task_id)
        with closing(self._connect()) as db:
            # A single read transaction gives coherent current/run/review fields.
            db.execute("BEGIN")
            task = db.execute("SELECT * FROM tasks WHERE room_id=? AND task_id=?", (room_id, task_id)).fetchone()
            if task is None:
                raise RoomError("unknown_task", "This room has no verification under that task ID.")
            run_id = _run_id(run_id or task["current_run"])
            row = self._row(db, room_id, task_id, run_id)
            review = db.execute("SELECT * FROM reviews WHERE run_id=?", (run_id,)).fetchone()
            completion = db.execute("SELECT * FROM completions WHERE run_id=?", (run_id,)).fetchone()
            is_current = task["current_run"] == run_id
            evidence_valid, evidence_error = False, None
            stored = json.loads(row["result_json"]) if row["result_json"] else None
            if row["status"] == "ready":
                try:
                    self._checked_result(row)
                    evidence_valid = True
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    evidence_error = str(exc)[:600]
            historical_review = "completed" if completion else "approved" if review else "unreviewed"
            return {"room_id": room_id, "task_id": task_id, "run_id": run_id, "revision": row["revision"],
                    "request_seq": row["request_seq"], "last_request_seq": task["last_request_seq"],
                    "case_set": row["case_set"], "status": row["status"], "created_at": row["created_at"],
                    "started_at": row["started_at"], "finished_at": row["finished_at"],
                    "execution_contract_sha256": row["execution_contract"], "inputs": json.loads(row["inputs_json"]),
                    "is_current": is_current, "current_run_id": task["current_run"],
                    "task_status": task["review_status"], "review_status": historical_review,
                    "approval": dict(review) if review else None, "completion": dict(completion) if completion else None,
                    "evidence_valid": evidence_valid, "evidence_error": evidence_error, "error": row["error"],
                    "summary": stored.get("summary") if stored else None,
                    "artifacts": list(stored.get("files", {})) if stored else [],
                    "can_approve": bool(is_current and evidence_valid),
                    "can_complete": bool(is_current and evidence_valid and review),
                    "scope": "Human review of checked local execution behavior only. Factual/overall uncertainty is unchanged."}

    def read_artifact(self, room_id, task_id, run_id, name):
        self._scope(room_id, task_id)
        _run_id(run_id)
        if name not in ARTIFACT_NAMES:
            raise RoomError("unknown_artifact", "Unknown evidence artifact.")
        with closing(self._connect()) as db:
            row = self._row(db, room_id, task_id, run_id)
            # Failed runs may expose their original partial evidence, explicitly
            # as failed. This path never grants eligibility for human completion.
            result = self._checked_result(row) if row["status"] == "ready" else self._retained_result(row)
            if name not in result["files"]:
                raise RoomError("unknown_artifact", "This run did not produce that evidence artifact.")
            raw = (self.artifact_root / run_id / name).read_bytes()
            # Recheck the bytes actually served, including a read-after-check race.
            if _hash(raw) != result["files"][name]["sha256"]:
                raise RoomError("evidence_tampered", "Evidence changed while it was opened.")
            return raw
