"""Switch Console 0.40.1 / Core 0.31 authenticated room adapter.

Only an original, server-authenticated human message can select an operation.
The coding agent supplies its message ID, never an actor, body or approval flag.
This is a local integration, not a security boundary against the machine owner.
"""
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote, urlparse

import httpx
from dotenv import dotenv_values

from intent_replay.qa_room import CASE_SET, QaRoomStore, RoomError, VerifiedHumanEvent


VERSION = {"console": "0.40.1", "core": "0.31.0", "adapter": "switch-console-chat-v1"}
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}")
TASK = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")


def local_url(value):
    parsed = urlparse(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise RoomError("invalid_configuration", "This milestone requires a loopback HTTP server origin.")
    return value.rstrip("/")


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    for name in ("gateway_url", "report_url"):
        config[name] = local_url(config[name])
    for name in ("room_id", "agent_id"):
        if not isinstance(config.get(name), str) or not ID.fullmatch(config[name]):
            raise RoomError("invalid_configuration", "Missing or invalid " + name + ".")
    if not TASK.fullmatch(config.get("task_id", "")):
        raise RoomError("invalid_configuration", "Missing or invalid task_id.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", config.get("agent_name", "")):
        raise RoomError("invalid_configuration", "Missing or invalid agent_name.")
    if not config.get("reviewer_user_ids") and not config.get("reviewer_client_ids"):
        raise RoomError("invalid_configuration", "Pin the actual human reviewer identity before accepting commands.")
    for name in ("reviewer_user_ids", "reviewer_client_ids"):
        values = config.get(name, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not ID.fullmatch(v) for v in values):
            raise RoomError("invalid_configuration", "Invalid pinned reviewer identities.")
    for name in ("native_env_file", "agent_credentials_file"):
        if not isinstance(config.get(name), str) or not Path(config[name]).is_absolute():
            raise RoomError("invalid_configuration", "An absolute private credential reference is required: " + name)
    return config


class SwitchClient:
    """Released Gateway read API plus agent-authenticated result posting.

    Generated native-server credentials are read in place, used only for login,
    and never returned. The human-session send endpoint is deliberately absent.
    """
    def __init__(self, config, *, transport=None):
        self.config = config
        self.base = local_url(config["gateway_url"])
        self.http = httpx.Client(timeout=15, trust_env=False, follow_redirects=False, transport=transport)
        self.authenticated = False
        self.observed_server = None

    def close(self):
        self.http.close()

    def _json(self, method, path, *, origin=None, **kwargs):
        try:
            response = self.http.request(method, (local_url(origin) if origin else self.base) + path, **kwargs)
        except httpx.HTTPError:
            raise RoomError("switch_unavailable", "The local Switch server could not be reached.") from None
        if response.status_code >= 300:
            # Error bodies can contain deployment details. Do not relay them.
            raise RoomError("switch_http_error", "Switch returned HTTP " + str(response.status_code) + ".")
        try:
            return response.json()
        except ValueError:
            raise RoomError("switch_invalid_response", "Switch did not return valid JSON.") from None

    def login(self):
        if self.authenticated:
            return
        values = dotenv_values(self.config["native_env_file"])
        email, password = values.get("GATEWAY_ADMIN_EMAIL"), values.get("GATEWAY_ADMIN_PASSWORD")
        if not email or not password:
            raise RoomError("switch_credentials_unavailable", "Generated native Switch login configuration is unavailable.")
        login = self._json("POST", "/gateway/auth/login", json={"email": email, "password": password})
        if not self.http.cookies.get("switch_auth"):
            raise RoomError("switch_auth_failed", "Switch login did not establish an authenticated session.")
        self.observed_server = login.get("server")
        if not isinstance(self.observed_server, dict) or self.observed_server.get("version") != VERSION["core"]:
            raise RoomError("switch_version_mismatch", "This adapter requires observed Switch Core 0.31.0; inspect any different deployment before use.")
        self.authenticated = True

    def get_message(self, room_id, message_id):
        if room_id != self.config["room_id"] or not isinstance(message_id, str) or not ID.fullmatch(message_id):
            raise RoomError("wrong_room", "Only the configured QA room is supported.")
        self.login()
        before = None
        for _ in range(50):
            params = {"limit": 200}
            if before is not None:
                params["beforeSeq"] = before
            page = self._json("GET", "/gateway/chats/" + quote(room_id, safe="") + "/messages", params=params)
            rows = page.get("messages")
            if not isinstance(rows, list):
                raise RoomError("switch_invalid_response", "Switch message response has an unsupported shape.")
            matches = [row for row in rows if row.get("messageId") == message_id]
            if len(matches) > 1:
                raise RoomError("ambiguous_event", "Switch returned an ambiguous message identity.")
            if matches:
                message = matches[0]
                if message.get("roomId") != room_id:
                    raise RoomError("wrong_room", "The original message belongs to another room.")
                return message
            if not page.get("hasMore"):
                break
            seqs = [row.get("seq") for row in rows]
            if not seqs or any(type(seq) is not int for seq in seqs):
                raise RoomError("switch_invalid_response", "Switch pagination lacks a valid sequence.")
            next_before = min(seqs)
            if before is not None and next_before >= before:
                raise RoomError("switch_invalid_response", "Switch message pagination did not advance.")
            before = next_before
        raise RoomError("event_not_found", "The original event was not found in the configured Switch room.")

    def post_result(self, text):
        credential = json.loads(Path(self.config["agent_credentials_file"]).read_text(encoding="utf-8"))
        env = credential.get("env", {})
        if (env.get("SWITCH_AGENT_ID") != self.config["agent_id"]
                or not env.get("SWITCH_API_TOKEN")):
            raise RoomError("agent_credentials_mismatch", "Console agent credentials do not match this room setup.")
        # Managed Console agents use a per-controller loopback relay, while
        # legacy agents use the core origin. Both use this released route; the
        # relay enforces the matching agent and forwards its authentication.
        agent_origin = local_url(env.get("SWITCH_API_ENDPOINT", ""))
        result = self._json("POST", "/agents/" + quote(self.config["agent_id"], safe="") + "/message",
                            origin=agent_origin,
                            headers={"Authorization": "Bearer " + env["SWITCH_API_TOKEN"], "Cookie": ""},
                            json={"room_id": self.config["room_id"], "content": text})
        if result.get("ok") is not True or not isinstance(result.get("event_id"), str):
            raise RoomError("post_unconfirmed", "Switch did not confirm the agent result post; do not automatically resend.")
        return result["event_id"]


def command(message, config):
    """Exact original body; quoted, fenced, agent-authored and asserted text fails."""
    sender = message.get("sender") or {}
    if not config.get("reviewer_user_ids") and not config.get("reviewer_client_ids"):
        raise RoomError("reviewer_not_configured", "Pin the actual reviewer identity before accepting commands.")
    if (message.get("roomId") != config["room_id"] or sender.get("kind") != "human"
            or sender.get("agentId") is not None or message.get("source") not in {"console", "mattermost"}):
        raise RoomError("human_required", "A verified original human message in this room is required.")
    for config_key, sender_key in (("reviewer_user_ids", "userId"), ("reviewer_client_ids", "clientId")):
        if config.get(config_key) and sender.get(sender_key) not in config[config_key]:
            raise RoomError("reviewer_not_allowed", "This message is not from the configured human reviewer.")
    body = message.get("body")
    if not isinstance(body, str) or len(body) > 500 or message.get("attachments"):
        raise RoomError("unsupported_command", "Use one standalone QA command without attachments or quoted text.")
    prefix = r"(?:@" + re.escape(config["agent_name"]) + r" )?"
    match = re.fullmatch(prefix + r"qa (verify|show|approve|complete) ([A-Za-z0-9][A-Za-z0-9_.-]{0,79}) ([A-Za-z0-9-]+)", body.strip())
    if not match:
        raise RoomError("unsupported_command", "Use the exact standalone qa verify/show/approve/complete command.")
    operation, task_id, target = match.groups()
    if task_id != config["task_id"]:
        raise RoomError("wrong_task", "This QA room is bound to a different verification task.")
    if operation == "verify" and target != CASE_SET:
        raise RoomError("unsupported_case", "Only the retained corrected Meta withdrawal/control pair is supported.")
    if operation != "verify" and not re.fullmatch(r"[a-f0-9]{32}", target):
        raise RoomError("invalid_run", "Use the exact 32-character run ID from the result.")
    return operation, task_id, target


def result_message(snapshot, config):
    run_id = snapshot["run_id"]
    text = [f"Intent Replay QA | task {snapshot['task_id']} | run {run_id}",
            f"Run: {snapshot['status']}; current: {'yes' if snapshot['is_current'] else 'no (historical)'}. "]
    summary = snapshot.get("summary") or {}
    if snapshot.get("evidence_valid") and summary:
        text.append("Frozen regression expectations: " + summary["regression_status"] + ".")
        for label in ("withdrawal", "control"):
            case = summary["cases"][label]
            text.append(label.capitalize() + " (" + case["case_id"] + "):")
            for branch in case["branches"]:
                expected, observed = branch["expected"], branch["observed"]
                name = "Guarded" if branch["implementation"] == "corrected" else "Faulty"
                text.append(f"- {name}: expected {expected['action_status']} at {expected['final_time']}; "
                            f"observed {observed['action_status']} at {observed['final_time']}; execution {observed['instruction_adherence']}.")
        text.append("Expected faulty withdrawal FAIL is a matching regression. Factual accuracy: INCONCLUSIVE / unassessed. "
                    "Overall task: FAIL for faulty withdrawal; INCONCLUSIVE for guarded/control.")
    else:
        text.append("Evidence is not eligible for completion. No prior approval can complete this run.")
    text.append(f"Human review: {snapshot['review_status']}; reviewed run remains explicit in the report.")
    text.append("Open both reports and evidence bundles: " + config["report_url"] + "/qa/runs/" + run_id)
    prefix = "@" + config["agent_name"] + " qa "
    if snapshot["is_current"] and snapshot.get("evidence_valid"):
        if snapshot.get("completion"):
            text.append("Human review completed for the checked local execution behavior, using run " + run_id + ".")
        elif snapshot.get("approval"):
            text.append("Human next action: " + prefix + "complete " + snapshot["task_id"] + " " + run_id)
        else:
            text.append("After inspecting both reports, human next action: " + prefix + "approve " + snapshot["task_id"] + " " + run_id)
    else:
        text.append("Request a new verification: " + prefix + "verify " + snapshot["task_id"] + " " + CASE_SET)
    text.append("Replay inference: 0 new model calls. Switch-agent inference is separate and is not measured by the replay runner.")
    return "\n".join(text)


class SwitchDispatcher:
    def __init__(self, config, state, *, client=None):
        self.config, self.state = config, Path(state)
        self.state.mkdir(parents=True, exist_ok=True)
        self.client = client or SwitchClient(config)
        self.store = QaRoomStore(self.state / "workflow", human_verifier=self.verify_human)
        self.receipts = self.state / "switch-deliveries.sqlite3"
        with closing(sqlite3.connect(self.receipts)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS deliveries (room_id TEXT, event_id TEXT, message_hash TEXT NOT NULL, "
                       "status TEXT NOT NULL, result_json TEXT, post_id TEXT, PRIMARY KEY(room_id,event_id))")
            db.commit()

    def verify_human(self, room_id, event_id, operation, run_id, task_id):
        message = self.client.get_message(room_id, event_id)
        if command(message, self.config) != (operation, task_id, run_id):
            raise RoomError("wrong_review_event", "The original human command does not approve/complete this exact run.")
        snapshot = self.store.show_run(room_id, task_id, run_id)
        required = snapshot.get("finished_at")
        if not required:
            raise RoomError("run_not_ready", "Review cannot precede the finished result.")
        if operation == "complete" and snapshot.get("approval"):
            required = max(required, snapshot["approval"]["approved_at"])
        try:
            sent = datetime.fromisoformat(message["sentAt"].replace("Z", "+00:00"))
            ready = datetime.fromisoformat(required.replace("Z", "+00:00"))
            if sent.tzinfo is None or ready.tzinfo is None or sent < ready:
                raise ValueError("premature")
        except (KeyError, TypeError, ValueError):
            raise RoomError("premature_review", "The original human interaction predates the result or required approval.") from None
        sender = message["sender"]
        actor = "switch:user:" + sender["userId"] if sender.get("userId") else "switch:client:" + sender["clientId"]
        return VerifiedHumanEvent(actor, event_id, room_id, "switch:" + message["source"], operation, task_id, run_id, message["sentAt"])

    def dispatch(self, event_id, *, post=True):
        room = self.config["room_id"]
        message = self.client.get_message(room, event_id)
        operation, task, target = command(message, self.config)
        original_hash = hashlib.sha256(json.dumps(message, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        accepted = None
        with closing(sqlite3.connect(self.receipts, timeout=30)) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT message_hash,status,result_json,post_id FROM deliveries WHERE room_id=? AND event_id=?", (room,event_id)).fetchone()
            if old:
                if old[0] != original_hash:
                    raise RoomError("event_conflict", "This event identity was previously seen with different content.")
                if old[1] != "accepted":
                    db.commit()
                    return {"duplicate": True, "delivery_status": old[1], "posted_event_id": old[3],
                            "note": "Previously delivered event; no run, review or post repeated. Inspect the current run separately."}
            if operation == "verify":
                seq = message.get("seq")
                if type(seq) is not int or seq < 1:
                    raise RoomError("invalid_event_sequence", "A trusted Switch event sequence is required.")
                # The core commits current=pending BEFORE a delivery is called
                # accepted. If this outer transaction crashes, the core event ID
                # makes redelivery idempotent; an old approval never returns.
                accepted = self.store.request_run(room, task, event_id, case_set=target, request_seq=seq)
            if not old:
                db.execute("INSERT INTO deliveries VALUES (?,?,?,'accepted',NULL,NULL)", (room,event_id,original_hash))
            db.commit()
        try:
            if operation == "verify":
                snapshot = self.store.execute_run(accepted["run_id"])
                if snapshot["status"] in {"pending", "running"}:
                    return {"duplicate": True, "delivery_status": "execution_in_progress", "run_id":snapshot["run_id"],
                            "note":"Execution already claimed; it is never resent automatically. A fresh request can supersede an interrupted run."}
            elif operation == "show":
                snapshot = self.store.show_run(room, task, target)
            elif operation == "approve":
                snapshot = self.store.approve_run(room, task, target, event_id)
            else:
                snapshot = self.store.complete_run(room, task, target, event_id)
            result = {"ok": True, "operation": operation, "event_id": event_id, "run_id": snapshot["run_id"],
                      "snapshot": snapshot, "message": result_message(snapshot,self.config), "integration_target": VERSION,
                      "observed_server": getattr(self.client, "observed_server", None),
                      "replay_model_requests": 0, "switch_agent_inference": "Separate; not observable in this adapter."}
        except RoomError as exc:
            result = {"ok": False, "operation": operation, "event_id": event_id, "error_code": exc.code,
                      "message": f"QA request refused ({exc.code}): {exc}\nTask: {task}. Requested result: {target}. "
                                 "No review completion was granted."}
        with closing(sqlite3.connect(self.receipts)) as db:
            updated = db.execute("UPDATE deliveries SET status=?,result_json=? WHERE room_id=? AND event_id=? AND status='accepted'",
                       ("posting" if post else "processed", json.dumps(result), room,event_id))
            db.commit()
            if updated.rowcount != 1:
                return {"duplicate":True,"note":"Another delivery already finalized this event; no post repeated."}
        if post:
            # A crash/ambiguous timeout after this point is not auto-retried: the
            # released message endpoint has no caller-supplied idempotency key.
            result["posted_event_id"] = self.client.post_result(result["message"])
            with closing(sqlite3.connect(self.receipts)) as db:
                db.execute("UPDATE deliveries SET status='posted',post_id=?,result_json=? WHERE room_id=? AND event_id=?",
                           (result["posted_event_id"], json.dumps(result), room,event_id))
                db.commit()
        return result
