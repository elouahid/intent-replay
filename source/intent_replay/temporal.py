import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from intent_replay.booking import Booking, Implementation, reset_database


@dataclass(frozen=True)
class Instruction:
    turn_id: str
    operation: Literal["reschedule", "withdraw_pending"]
    booking_reference: str
    target_time: str
    timezone: str
    evidence_turn_ids: tuple[str, ...]
    interpretation_id: str


class RevisionStore:
    def __init__(self, path: Path):
        self.path = path

    @classmethod
    def create(cls, path: Path, initial: Booking, target_time: str, available: bool = True):
        if path.exists():
            raise FileExistsError("A replay must use a new database; existing evidence is not overwritten.")
        target_time = datetime.fromisoformat(target_time).isoformat()
        reset_database(path, initial, target_time, available)
        store = cls(path)
        with closing(store._connect()) as connection, connection:
            connection.executescript(
                "CREATE TABLE replay_context (initial_time TEXT NOT NULL, target_time TEXT NOT NULL);"
                "CREATE TABLE accepted_intents (revision INTEGER PRIMARY KEY, turn_id TEXT UNIQUE NOT NULL, "
                "operation TEXT NOT NULL, booking_reference TEXT NOT NULL, target_time TEXT NOT NULL, "
                "timezone TEXT NOT NULL, interpretation_id TEXT NOT NULL, evidence_turn_ids TEXT NOT NULL);"
                "CREATE TABLE queued_actions (action_id TEXT PRIMARY KEY, booking_reference TEXT NOT NULL, "
                "operation TEXT NOT NULL, target_time TEXT NOT NULL, accepted_revision INTEGER NOT NULL, "
                "status TEXT NOT NULL, checked_revision INTEGER, decision_sequence INTEGER, "
                "FOREIGN KEY (accepted_revision) REFERENCES accepted_intents(revision));"
                "CREATE TABLE journal (sequence INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id TEXT NOT NULL, "
                "event TEXT NOT NULL, data TEXT NOT NULL);"
            )
            connection.execute("INSERT INTO replay_context VALUES (?, ?)", (initial.starts_at, target_time))
            store._record(connection, uuid4().hex, "initialized", {
                "booking": asdict(initial), "target_time": target_time, "slot_available": available,
            })
        return store

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _record(connection, transaction_id: str, event: str, data: dict) -> int:
        cursor = connection.execute(
            "INSERT INTO journal(transaction_id, event, data) VALUES (?, ?, ?)",
            (transaction_id, event, json.dumps(data, sort_keys=True)),
        )
        return cursor.lastrowid

    def accept(self, instruction: Instruction, *, enqueue: bool = True) -> int:
        if type(enqueue) is not bool:
            raise ValueError("Queue admission must be an explicit boolean.")
        if instruction.operation not in ("reschedule", "withdraw_pending"):
            raise ValueError("Only rescheduling and withdrawal of that pending reschedule are supported.")
        if not instruction.interpretation_id or instruction.turn_id not in instruction.evidence_turn_ids:
            raise ValueError("Acceptance requires a validated interpretation linked to the customer turn.")
        requested = datetime.fromisoformat(instruction.target_time)
        if requested.tzinfo is None or requested.utcoffset() != requested.astimezone(ZoneInfo(instruction.timezone)).utcoffset():
            raise ValueError("The instruction must have a consistent explicit date, time, and timezone.")
        canonical_target = requested.isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            initial_time, target_time = connection.execute("SELECT * FROM replay_context").fetchone()
            booking = connection.execute("SELECT * FROM bookings").fetchone()
            accepted = connection.execute("SELECT * FROM accepted_intents ORDER BY revision").fetchall()
            if instruction.booking_reference != booking["reference"] or instruction.timezone != booking["timezone"]:
                raise ValueError("The supported instruction must identify this booking and timezone.")
            if not accepted:
                supported = instruction.operation == "reschedule" and canonical_target == datetime.fromisoformat(target_time).isoformat()
            else:
                supported = len(accepted) == 1 and instruction.operation == "withdraw_pending" and canonical_target == datetime.fromisoformat(initial_time).isoformat()
            if not supported:
                raise ValueError("Only one reschedule followed by its withdrawal is supported; no restoration is inferred.")
            revision = len(accepted) + 1
            transaction_id = uuid4().hex
            connection.execute(
                "INSERT INTO accepted_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (revision, instruction.turn_id, instruction.operation, instruction.booking_reference,
                 canonical_target, instruction.timezone, instruction.interpretation_id,
                 json.dumps(instruction.evidence_turn_ids)),
            )
            self._record(connection, transaction_id, "instruction_accepted", {
                "revision": revision, **asdict(instruction), "target_time": canonical_target,
            })
            if instruction.operation == "reschedule" and enqueue:
                self._enqueue(connection, transaction_id, revision, instruction.booking_reference, canonical_target)
            elif instruction.operation == "withdraw_pending" and connection.execute("SELECT 1 FROM queued_actions WHERE status != 'pending'").fetchone():
                self._record(connection, transaction_id, "withdrawal_too_late", {
                    "revision": revision, "turn_id": instruction.turn_id,
                    "detail": "The earlier action is already complete. No restoration action was executed.",
                })
        return revision

    def _enqueue(self, connection, transaction_id, revision, reference, target_time):
        if connection.execute("SELECT 1 FROM queued_actions").fetchone():
            raise ValueError("Only one mutation proposal may be admitted in this run.")
        action_id = uuid4().hex
        connection.execute(
            "INSERT INTO queued_actions VALUES (?, ?, 'reschedule', ?, ?, 'pending', NULL, NULL)",
            (action_id, reference, target_time, revision),
        )
        self._record(connection, transaction_id, "action_queued", {
            "action_id": action_id, "booking_reference": reference, "operation": "reschedule",
            "target_time": target_time, "accepted_revision": revision,
        })
        return action_id

    def enqueue_proposal(self, originating_revision: int, booking_reference: str, target_time: str, timezone: str) -> str:
        """Admit an actual actor proposal, bound to its host-recorded input revision."""
        if type(originating_revision) is not int or originating_revision < 1:
            raise ValueError("A proposal requires its originating accepted revision.")
        requested = datetime.fromisoformat(target_time)
        if requested.tzinfo is None or requested.utcoffset() != requested.astimezone(ZoneInfo(timezone)).utcoffset():
            raise ValueError("The proposal requires a consistent date, time, and timezone.")
        canonical_target = requested.isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            accepted = connection.execute("SELECT * FROM accepted_intents WHERE revision = ?", (originating_revision,)).fetchone()
            if not accepted or accepted["operation"] != "reschedule" or accepted["booking_reference"] != booking_reference or accepted["target_time"] != canonical_target or accepted["timezone"] != timezone:
                raise ValueError("Actor arguments do not match the originating accepted instruction.")
            return self._enqueue(connection, uuid4().hex, originating_revision, booking_reference, canonical_target)

    def read_evidence(self) -> dict:
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            booking = connection.execute("SELECT * FROM bookings").fetchone()
            accepted = [dict(row) for row in connection.execute("SELECT * FROM accepted_intents ORDER BY revision")]
            actions = [dict(row) for row in connection.execute("SELECT * FROM queued_actions ORDER BY action_id")]
            journal = [dict(row) for row in connection.execute("SELECT * FROM journal ORDER BY sequence")]
        for item in accepted:
            item["evidence_turn_ids"] = json.loads(item["evidence_turn_ids"])
        for event in journal:
            event["data"] = json.loads(event["data"])
        return {
            "booking": dict(booking) if booking else None, "accepted_instructions": accepted,
            "actions": actions, "journal": journal,
            "read_after_sequence": journal[-1]["sequence"] if journal else None,
            "read_source": "independent read-only SQLite transaction",
        }

    def receive(self, turn_id: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._record(connection, uuid4().hex, "instruction_received", {"turn_id": turn_id})

    def record_statement(self, turn_id: str, text: str, describes_sequence: int, snapshot: dict) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            anchor = connection.execute("SELECT event FROM journal WHERE sequence = ?", (describes_sequence,)).fetchone()
            if not anchor or anchor["event"] not in ("action_committed", "action_suppressed", "action_rejected", "withdrawal_too_late"):
                raise ValueError("A statement must describe a persisted execution event.")
            if snapshot["read_after_sequence"] < describes_sequence or not snapshot["booking"]:
                raise ValueError("A statement requires readback after its described event committed.")
            self._record(connection, uuid4().hex, "assistant_statement", {
                "turn_id": turn_id, "text": text, "describes_sequence": describes_sequence,
                "snapshot": {key: snapshot[key] for key in ("booking", "read_after_sequence", "read_source")},
            })

    def execute(
        self,
        implementation: Implementation,
        after_preliminary_read: Callable[[], None] | None = None,
        before_commit: Callable[[], None] | None = None,
    ) -> dict:
        if implementation not in ("faulty", "corrected"):
            raise ValueError("Unknown execution behaviour.")
        preliminary = self.read_evidence()
        if len(preliminary["actions"]) != 1:
            raise ValueError("Exactly one queued reschedule is required.")
        action_id = preliminary["actions"][0]["action_id"]
        if preliminary["actions"][0]["status"] != "pending":
            return preliminary
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._record(connection, uuid4().hex, "worker_preliminary_read", {
                "action_id": action_id,
                "observed_revision": preliminary["accepted_instructions"][-1]["revision"],
                "observed_sequence": preliminary["read_after_sequence"],
            })
        if after_preliminary_read is not None:
            after_preliminary_read()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            transaction_id = uuid4().hex
            action = connection.execute("SELECT * FROM queued_actions WHERE action_id = ?", (action_id,)).fetchone()
            if action["status"] != "pending":
                raise ValueError("The action has already been resolved.")
            current = connection.execute("SELECT * FROM accepted_intents ORDER BY revision DESC LIMIT 1").fetchone()
            before = dict(connection.execute("SELECT * FROM bookings WHERE reference = ?", (action["booking_reference"],)).fetchone())
            authorized = (
                current["revision"] == action["accepted_revision"]
                and current["operation"] == action["operation"]
                and current["booking_reference"] == action["booking_reference"]
                and current["target_time"] == action["target_time"]
            )
            self._record(connection, transaction_id, "authorization_checked", {
                "action_id": action_id, "accepted_revision": action["accepted_revision"],
                "checked_revision": current["revision"], "authorized": authorized,
            })
            available = connection.execute("SELECT available FROM slots WHERE starts_at = ?", (action["target_time"],)).fetchone()
            if not authorized and implementation == "corrected":
                status, reason = "suppressed", "A newer accepted revision no longer authorizes this queued action."
            elif not available or not available[0]:
                status, reason = "rejected", "The target slot is unavailable; the booking was not changed."
            else:
                connection.execute("UPDATE bookings SET starts_at = ? WHERE reference = ?", (action["target_time"], action["booking_reference"]))
                connection.execute("UPDATE slots SET available = 0 WHERE starts_at = ?", (action["target_time"],))
                connection.execute("UPDATE slots SET available = 1 WHERE starts_at = ?", (before["starts_at"],))
                status = "committed"
                reason = "The queued reschedule was committed." if authorized else "Controlled fault: committed despite a newer accepted revision."
            after = dict(connection.execute("SELECT * FROM bookings WHERE reference = ?", (action["booking_reference"],)).fetchone())
            sequence = self._record(connection, transaction_id, "action_" + status, {
                "action_id": action_id, "booking_reference": action["booking_reference"],
                "operation": action["operation"], "target_time": action["target_time"],
                "accepted_revision": action["accepted_revision"], "checked_revision": current["revision"],
                "authorized": authorized, "before": before, "after": after, "reason": reason,
            })
            connection.execute(
                "UPDATE queued_actions SET status = ?, checked_revision = ?, decision_sequence = ? WHERE action_id = ?",
                (status, current["revision"], sequence, action_id),
            )
            if before_commit is not None:
                before_commit()
        return self.read_evidence()
