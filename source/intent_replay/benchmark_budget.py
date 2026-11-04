"""One durable authority for this milestone, independent of report directories.

Reservations and dispatches are committed before transport. A logical request is
never retried automatically, including after a crash with an unknown outcome.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from intent_replay.benchmark_cases import digest, now
from intent_replay.meta_client import HTTPAttemptLimitError, PROJECT_ROOT

# Fixed milestone identity also survives source extraction/checkouts. Report paths
# and copied source trees must not create a new inference allowance.
AUTHORITY = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "IntentReplay" / "benchmark-20261031"
LIMITS = {"pilot": {"http": 24, "meta": "5", "baseten": "2", "modal": "5"},
          "expansion": {"http": 192, "meta": "25", "baseten": "5", "modal": "5"}}


class BudgetBlocked(HTTPAttemptLimitError):
    pass


class Ledger:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else AUTHORITY
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "ledger.sqlite3"
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, logical_id TEXT NOT NULL,
                  provider TEXT NOT NULL, role TEXT NOT NULL, phase TEXT NOT NULL, case_hash TEXT NOT NULL,
                  target_hash TEXT NOT NULL, repetition INTEGER NOT NULL, experiment_id TEXT NOT NULL,
                  max_output INTEGER NOT NULL, input_bound INTEGER NOT NULL, reservation TEXT NOT NULL,
                  cost TEXT NOT NULL, status TEXT NOT NULL, dispatched INTEGER NOT NULL DEFAULT 0,
                  responses INTEGER NOT NULL DEFAULT 0, success INTEGER NOT NULL DEFAULT 0,
                  usage TEXT, latency REAL, created_at TEXT NOT NULL, completed_at TEXT);
                CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, at TEXT NOT NULL,
                  event TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS computes (execution_id TEXT PRIMARY KEY,
                  experiment_id TEXT NOT NULL, location TEXT NOT NULL, report_hash TEXT NOT NULL);
            """)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
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
    def event(db, name, data):
        db.execute("INSERT INTO events(at,event,data) VALUES(?,?,?)", (now(), name, json.dumps(data, sort_keys=True)))

    @staticmethod
    def setting(db, key):
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def fix(self, key, value):
        with self.transaction() as db:
            old = self.setting(db, key)
            if old is not None and old != value:
                raise BudgetBlocked(f"The durable {key} is already fixed; a new output directory cannot reset it.")
            db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (key, json.dumps(value, sort_keys=True)))
            if old is None:
                self.event(db, "configuration_fixed", {"key": key, "value": value})

    def funding(self, provider, proof=None):
        """A dated, account-specific public attestation; never a key or auth token."""
        if proof is not None:
            rates = {"cpu_per_core_second", "memory_per_gib_second", "image_build_reservation_usd"} if provider == "modal" else {"input_per_million", "output_per_million"}
            required = {"balance_usd", "source", "rate_source", "account_applicability", "checked_at", "valid_until", "expiration_note"} | rates
            if set(proof) != required or any(not isinstance(v, str) or not v for v in proof.values()):
                raise ValueError("Funding needs rates, balance, account applicability and a bounded validity date.")
            for name in {"balance_usd"} | rates:
                if not Decimal(proof[name]).is_finite() or Decimal(proof[name]) < 0:
                    raise ValueError("Invalid funding/rate amount.")
            checked, expires = (datetime.fromisoformat(proof[k]) for k in ("checked_at", "valid_until"))
            if checked.utcoffset() is None or expires.utcoffset() is None or checked > datetime.now(timezone.utc) or expires <= datetime.now(timezone.utc) or expires <= checked:
                raise ValueError("Funding dates must be aware, already checked and currently valid.")
            with self.transaction() as db:
                db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("funding:" + provider, json.dumps(proof, sort_keys=True)))
                self.event(db, "funding_attestation", {"provider": provider, **proof})
        with self.transaction() as db:
            return self.setting(db, "funding:" + provider)

    @staticmethod
    def require_funding(db, provider):
        proof = Ledger.setting(db, "funding:" + provider)
        if not proof or datetime.fromisoformat(proof["valid_until"]) <= datetime.now(timezone.utc):
            raise BudgetBlocked(f"{provider}: applicable balance/credit and current rates are unverified or expired; no paid dispatch.")
        return proof

    def register_case(self, case, phase="pilot"):
        case_hash = digest(case.model_dump())
        with self.transaction() as db:
            cases = self.setting(db, "cases:" + phase) or []
            if phase == "pilot":
                if case_hash not in [c["sha256"] for c in cases]:
                    if len(cases) >= 2 or case.timing in [c["timing"] for c in cases]:
                        raise BudgetBlocked("Pilot permits only two fixed cases: one normal and one pre-commit withdrawal.")
                    cases.append({"sha256": case_hash, "timing": case.timing, "case_id": case.case_id})
                    db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("cases:pilot", json.dumps(cases)))
                    self.event(db, "pilot_case_fixed", cases[-1])
            else:
                gate = self.setting(db, "expansion_preparation")
                if not gate or not gate.get("eligible") or case_hash not in [c["sha256"] for c in cases]:
                    raise BudgetBlocked("Expansion requires the recorded integrity/capability gate and six pre-frozen cases.")
        return case_hash

    def register_target(self, config):
        with self.transaction() as db:
            targets = self.setting(db, "targets") or {}
            if config.provider in targets and targets[config.provider] != config.sha256:
                raise BudgetBlocked("This provider's campaign configuration is already fixed; it cannot be changed for another paid capture.")
            if config.provider not in targets:
                targets[config.provider] = config.sha256
                db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("targets", json.dumps(targets)))
                self.event(db, "target_fixed", {"configuration_sha256": config.sha256, "configuration": config.public()})

    def _reserve(self, db, meta, request_id, logical_id, input_bound):
        if self.setting(db, "inference_closed"):
            raise BudgetBlocked("This milestone's planned inference is closed. Saved artifacts may be reused; unused caps do not authorize more requests.")
        phase, provider, role = meta["phase"], meta["provider"], meta["role"]
        if phase not in LIMITS or provider not in ("meta", "baseten") or role not in ("customer", "actor", "capability"):
            raise BudgetBlocked("Unlisted request role/provider/phase.")
        if db.execute("SELECT 1 FROM requests WHERE id=?", (request_id,)).fetchone():
            raise BudgetBlocked("Request already reserved; its outcome may be unknown. It must not be automatically resent.")
        cases = self.setting(db, "cases:" + phase) or []
        if role != "capability" and meta["case_hash"] not in [c["sha256"] for c in cases]:
            raise BudgetBlocked("Case is not in the fixed campaign.")
        if role == "customer" and (provider != "meta" or meta["max_output"] != 4096):
            raise BudgetBlocked("Customer interpretation stays on the Meta 4096-token path.")
        if role != "customer" and meta["max_output"] != 2048:
            raise BudgetBlocked("Actor/capability output limit must be 2048.")
        gate_name = "expansion_preparation" if role == "customer" else "expansion_gate"
        if phase == "expansion" and not (self.setting(db, gate_name) or {}).get("eligible"):
            raise BudgetBlocked("Expansion integrity gate has not passed.")
        targets = self.setting(db, "targets") or {}
        if role == "actor" and targets.get(provider) != meta["target_hash"]:
            raise BudgetBlocked("Target configuration is not fixed for this campaign.")
        if role == "actor" and provider == "baseten" and not (self.setting(db, "capability:baseten") or {}).get("valid_native_proposal"):
            raise BudgetBlocked("Baseten native-tool capability has not been verified.")
        count = lambda sql, args=(): db.execute(sql, args).fetchone()[0]
        # Reservations count toward ceilings, including unknown/unstarted dispatches.
        if count("SELECT COUNT(*) FROM requests") >= LIMITS[phase]["http"]:
            raise BudgetBlocked("Milestone HTTP reservation/attempt ceiling reached.")
        if phase == "pilot" and count("SELECT COUNT(*) FROM requests WHERE phase='pilot'") >= 24:
            raise BudgetBlocked("Pilot HTTP ceiling reached.")
        if role == "capability" and (provider != "baseten" or phase != "pilot" or count("SELECT COUNT(*) FROM requests WHERE role='capability'") >= 2):
            raise BudgetBlocked("At most two explicit Baseten capability attempts are allowed.")
        if role == "customer" and count("SELECT COUNT(*) FROM requests WHERE role='customer'") >= (2 if phase == "pilot" else 6):
            raise BudgetBlocked("Shared customer freeze request ceiling reached.")
        if role == "actor":
            if meta["repetition"] not in ((1,) if phase == "pilot" else (1, 2, 3)):
                raise BudgetBlocked("Unlisted campaign repetition.")
            if count("SELECT COUNT(*) FROM requests WHERE role='actor' AND experiment_id=?", (meta["experiment_id"],)) >= 4:
                raise BudgetBlocked("Four actor HTTP attempts per comparison exhausted.")
            if count("SELECT COUNT(DISTINCT experiment_id) FROM requests WHERE role='actor' AND phase=?", (phase,)) >= (4 if phase == "pilot" else 36) and not count("SELECT COUNT(*) FROM requests WHERE experiment_id=?", (meta["experiment_id"],)):
                raise BudgetBlocked("Comparison ceiling reached.")
        proof = self.require_funding(db, provider)
        reserve = (Decimal(input_bound) * Decimal(proof["input_per_million"]) + Decimal(meta["max_output"]) * Decimal(proof["output_per_million"])) / Decimal(1_000_000)
        spent = sum((Decimal(r[0]) for r in db.execute("SELECT cost FROM requests WHERE provider=?", (provider,))), Decimal(0))
        if spent + reserve > min(Decimal(LIMITS[phase][provider]), Decimal(proof["balance_usd"])):
            raise BudgetBlocked(f"{provider} conservative cost/credit envelope would be exceeded.")
        db.execute("""INSERT INTO requests(id,logical_id,provider,role,phase,case_hash,target_hash,repetition,
          experiment_id,max_output,input_bound,reservation,cost,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (request_id, logical_id, provider, role, phase, meta["case_hash"], meta["target_hash"], meta["repetition"], meta["experiment_id"],
           meta["max_output"], input_bound, str(reserve), str(reserve), "reserved_unknown", now()))
        self.event(db, "request_reserved", {"request_id": request_id, "reservation_usd": str(reserve), **meta})

    def call(self, *, request, **meta):
        encoded = json.dumps(request, ensure_ascii=True).encode()
        if len(encoded) > 65536:
            raise BudgetBlocked("Native request exceeds the 64-KiB input bound.")
        # One token per UTF-8/escaped byte plus scaffolding is intentionally conservative.
        input_bound = len(encoded) + 4096
        logical_id = digest(meta)
        with self.transaction() as db:
            self._reserve(db, meta, logical_id, logical_id, input_bound)
        return LedgerCall(self, meta, logical_id, input_bound)

    def record_compute(self, report):
        with self.transaction() as db:
            execution_id, experiment_id = report["execution_id"], report["experiment_id"]
            existing = db.execute("SELECT report_hash FROM computes WHERE execution_id=?", (execution_id,)).fetchone()
            if existing:
                if existing[0] != report["sha256"]:
                    raise ValueError("Compute ID reused with different evidence.")
                return True
            duplicate = db.execute("SELECT 1 FROM computes WHERE experiment_id=?", (experiment_id,)).fetchone() is not None
            db.execute("INSERT INTO computes VALUES (?,?,?,?)", (execution_id, experiment_id, report["runtime"]["location"], report["sha256"]))
            self.event(db, "compute_recorded", {"execution_id": execution_id, "experiment_id": experiment_id, "duplicate_experiment": duplicate})
            return duplicate

    def export(self):
        with self.transaction() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM requests ORDER BY created_at,id")]
            settings = {r[0]: json.loads(r[1]) for r in db.execute("SELECT * FROM settings")}
            events = [{**dict(r), "data": json.loads(r["data"])} for r in db.execute("SELECT * FROM events ORDER BY sequence")]
            computes = [dict(r) for r in db.execute("SELECT * FROM computes")]
        totals = {}
        for row in rows:
            row["usage"] = json.loads(row["usage"]) if row["usage"] else None
            key = row["provider"] + "/" + row["role"]
            total = totals.setdefault(key, {"requests": 0, "http_attempts": 0, "http_responses": 0, "successful_http_responses": 0,
                                            "input_tokens": 0, "output_tokens": 0, "usage_missing": 0, "estimated_usd": "0"})
            for field, source in (("http_attempts", "dispatched"), ("http_responses", "responses"), ("successful_http_responses", "success")):
                total[field] += row[source]
            total["requests"] += 1
            total["estimated_usd"] = str(Decimal(total["estimated_usd"]) + Decimal(row["cost"]))
            if row["usage"]:
                for field in ("input_tokens", "output_tokens"):
                    total[field] += row["usage"][field]
            else:
                total["usage_missing"] += 1
        return {"schema_version": "benchmark-ledger-v1", "authority": "one milestone ledger across output directories", "requests": rows,
                "totals_by_provider_role": totals, "settings": settings, "events": events, "computes": computes,
                "cost_note": "Estimates, not billing receipts. Actual usage replaces reservation; unknown usage retains reservation."}


class LedgerCall:
    def __init__(self, ledger, meta, logical_id, input_bound):
        self.ledger, self.meta, self.logical_id, self.input_bound = ledger, meta, logical_id, input_bound
        self.ids = [logical_id]
        self.hops = 0

    def reserve(self):
        """Transport hook, called for EVERY HTTP dispatch including redirects."""
        with self.ledger.transaction() as db:
            if self.hops:
                request_id = self.logical_id + f":hop{self.hops + 1}"
                self.ledger._reserve(db, self.meta, request_id, self.logical_id, self.input_bound)
                self.ids.append(request_id)
            db.execute("UPDATE requests SET dispatched=1,status='dispatched_unknown' WHERE id=?", (self.ids[-1],))
            self.ledger.event(db, "http_dispatch", {"request_id": self.ids[-1]})
        self.hops += 1

    def finish(self, *, usage=None, responses=0, successes=0, latency=None, error=None):
        valid = isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "output_tokens"))
        with self.ledger.transaction() as db:
            proof = self.ledger.setting(db, "funding:" + self.meta["provider"])
            for index, request_id in enumerate(self.ids):
                last = index == len(self.ids) - 1
                counted_response = int(index < responses)
                status = "response_received" if counted_response else ("dispatched_unknown" if self.hops else "reserved_unknown")
                if last and error and counted_response:
                    status = "failed_response"
                actual = ((Decimal(usage["input_tokens"]) * Decimal(proof["input_per_million"]) + Decimal(usage["output_tokens"]) * Decimal(proof["output_per_million"])) / Decimal(1_000_000)) if last and valid else None
                db.execute("UPDATE requests SET status=?,responses=?,success=?,usage=?,latency=?,completed_at=?,cost=COALESCE(?,cost) WHERE id=?",
                  (status, counted_response, int(last and successes > 0), json.dumps(usage) if last and valid else None, latency if last else None, now(), str(actual) if actual is not None else None, request_id))
            self.ledger.event(db, "request_finished", {"logical_id": self.logical_id, "request_ids": self.ids, "error": error, "usage_known": valid})
