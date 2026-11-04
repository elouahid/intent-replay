import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal


Implementation = Literal["faulty", "corrected"]


@dataclass(frozen=True)
class Booking:
    reference: str
    service: str
    starts_at: str
    timezone: str


@dataclass(frozen=True)
class Turn:
    id: str
    role: str
    text: str


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    event: str
    detail: str
    booking_reference: str
    target_time: str | None = None
    observed_time: str | None = None


@dataclass
class WorkflowResult:
    initial_booking: Booking
    final_booking: Booking | None
    final_state_status: str
    final_state_detail: str
    conversation: list[Turn]
    action_trace: list[TraceEvent]


def reset_database(path: Path, initial: Booking, target_time: str, available: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(
            "DROP TABLE IF EXISTS bookings; DROP TABLE IF EXISTS slots;"
            "CREATE TABLE bookings (reference TEXT PRIMARY KEY, service TEXT NOT NULL, "
            "starts_at TEXT NOT NULL, timezone TEXT NOT NULL);"
            "CREATE TABLE slots (starts_at TEXT PRIMARY KEY, available INTEGER NOT NULL);"
        )
        connection.execute(
            "INSERT INTO bookings VALUES (?, ?, ?, ?)",
            (initial.reference, initial.service, initial.starts_at, initial.timezone),
        )
        connection.executemany(
            "INSERT INTO slots VALUES (?, ?)",
            [(initial.starts_at, 0), (target_time, int(available))],
        )


def read_booking(path: Path, reference: str) -> Booking | None:
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute(
            "SELECT reference, service, starts_at, timezone FROM bookings WHERE reference = ?",
            (reference,),
        ).fetchone()
    return Booking(*row) if row else None


def run_workflow(
    path: Path,
    initial: Booking,
    target_time: str,
    customer_request: str,
    implementation: Implementation,
    slot_available: bool = True,
    final_read_available: bool = True,
) -> WorkflowResult:
    if implementation not in ("faulty", "corrected"):
        raise ValueError("Unknown implementation.")
    reset_database(path, initial, target_time, slot_available)
    initial_record = read_booking(path, initial.reference)
    if initial_record != initial:
        raise RuntimeError("The initial booking could not be verified.")
    trace: list[TraceEvent] = []

    def record(event: str, detail: str, observed: str | None = None) -> None:
        trace.append(TraceEvent(len(trace) + 1, event, detail, initial.reference, target_time, observed))

    record("reset", "Reset and independently read the initial SQLite booking.", initial.starts_at)
    original = datetime.fromisoformat(initial.starts_at)
    target = datetime.fromisoformat(target_time)
    conversation = [
        Turn(
            "turn-1", "assistant",
            f"Booking {initial.reference}: {initial.service}, on {original:%Y-%m-%d} "
            f"at {original:%H:%M} ({initial.timezone}).",
        ),
        Turn("turn-2", "customer", customer_request),
    ]
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        slot = connection.execute(
            "SELECT available FROM slots WHERE starts_at = ?", (target_time,)
        ).fetchone()
        available = bool(slot and slot[0])
        record("availability_checked", "Requested slot is available." if available else "Requested slot is unavailable.")
        if not available:
            record("rejected", "Rejected the reschedule because the requested slot is unavailable.")
        elif implementation == "corrected":
            connection.execute(
                "UPDATE bookings SET starts_at = ? WHERE reference = ?",
                (target_time, initial.reference),
            )
            connection.execute("UPDATE slots SET available = 0 WHERE starts_at = ?", (target_time,))
            connection.execute("UPDATE slots SET available = 1 WHERE starts_at = ?", (initial.starts_at,))
        else:
            record("write_skipped", "Controlled demonstration: the handler skips the database write.")

    verified = True
    if available and implementation == "corrected":
        record("committed", "Committed the reschedule transaction.", target_time)
        committed = read_booking(path, initial.reference)
        verified = bool(committed and committed.starts_at == target_time)
        record("handler_readback", "Handler checked the committed record through a new connection.", committed.starts_at if committed else None)

    if not available:
        reply = (
            f"I could not reschedule booking {initial.reference}: {target:%H:%M} on "
            f"{target:%Y-%m-%d} ({initial.timezone}) is unavailable. "
            f"Your booking remains at {original:%H:%M} on {original:%Y-%m-%d} ({initial.timezone})."
        )
    elif not verified:
        reply = f"I could not verify the saved booking {initial.reference}, so I cannot confirm the change."
    else:
        reply = (
            f"Confirmed: booking {initial.reference} has been moved to {target:%H:%M} "
            f"on {target:%Y-%m-%d} ({initial.timezone})."
        )
    conversation.append(Turn("turn-3", "assistant", reply))
    record("confirmation_issued", "Returned the assistant message recorded in turn-3.")

    read_path = path if final_read_available else path.with_name(path.stem + ".unavailable.sqlite3")
    try:
        final = read_booking(read_path, initial.reference)
        status = "available" if final else "missing"
        detail = "Read the committed booking through a separate read-only SQLite connection." if final else "No committed booking record was found."
        record("final_read", detail, final.starts_at if final else None)
    except sqlite3.Error:
        final = None
        status = "unavailable"
        detail = "Controlled evidence outage: the final read uses an unavailable SQLite database." if not final_read_available else "The committed booking could not be read from SQLite."
        record("final_read_failed", detail)

    return WorkflowResult(initial_record, final, status, detail, conversation, trace)