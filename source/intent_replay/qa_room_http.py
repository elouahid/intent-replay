"""HTTP evidence for one QA room/task, using the existing exporter.

Read-only by default. An explicitly configured local bridge may pass an original
message ID to the authenticated platform adapter; it never accepts room text,
an actor or an approval claim. Bind the launcher to loopback.
"""
from html import escape
import inspect
import json
import re
import secrets
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from intent_replay.qa_room import RoomError


HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
        "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
}
_SAFE_NAME = re.compile(r"[a-zA-Z0-9_-][a-zA-Z0-9_.-]{0,127}\Z")
_MESSAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}\Z")
_DISPATCH_CONFLICTS = frozenset({
    "event_conflict", "stale_run", "out_of_order_request", "event_sequence_required",
    "execution_version_changed", "input_changed", "evidence_binding", "evidence_assessment",
    "evidence_tampered", "required_checks_failed", "missing_control", "run_not_ready",
    "human_verification_unavailable", "premature_review", "review_binding", "unapproved_run",
    "switch_unavailable", "switch_http_error", "switch_invalid_response", "switch_auth_failed",
    "switch_version_mismatch", "switch_credentials_unavailable", "agent_credentials_mismatch",
    "post_unconfirmed", "reviewer_not_configured", "invalid_configuration",
})
_DISPATCH_REFUSALS = _DISPATCH_CONFLICTS | frozenset({
    "invalid_identity", "invalid_task", "invalid_run", "unsupported_input", "control_binding",
    "wrong_run_scope", "unsupported_case_set", "invalid_event_sequence", "unknown_run",
    "human_event_invalid", "unknown_task", "unknown_artifact", "wrong_room", "ambiguous_event",
    "event_not_found", "human_required", "reviewer_not_allowed", "unsupported_command",
    "wrong_task", "unsupported_case", "wrong_review_event",
})


def _dispatch_refusal(code):
    """Only known codes and fixed text cross this boundary, never exception text."""
    code = code if isinstance(code, str) and code in _DISPATCH_REFUSALS else "dispatch_refused"
    return JSONResponse({"ok": False, "error_code": code,
                         "message": "QA dispatch did not return a confirmed result. Inspect the configured room and current run before retrying."},
                        status_code=409 if code in _DISPATCH_CONFLICTS else 400)


def _dispatch_receipt(result, message_id):
    if not isinstance(result, dict) or not (result.get("ok") is True or result.get("duplicate") is True):
        if isinstance(result, dict) and result.get("ok") is False:
            return _dispatch_refusal(result.get("error_code"))
        raise ValueError("Invalid dispatch receipt")
    receipt = {"event_id": message_id}
    for key in ("ok", "duplicate"):
        if type(result.get(key)) is bool:
            receipt[key] = result[key]
    if result.get("operation") in {"verify", "show", "approve", "complete"}:
        receipt["operation"] = result["operation"]
    if isinstance(result.get("run_id"), str) and re.fullmatch(r"[0-9a-f]{32}", result["run_id"]):
        receipt["run_id"] = result["run_id"]
    if isinstance(result.get("posted_event_id"), str) and _MESSAGE_ID.fullmatch(result["posted_event_id"]):
        receipt["posted_event_id"] = result["posted_event_id"]
    if result.get("delivery_status") in {"accepted", "posting", "posted", "processed", "execution_in_progress"}:
        receipt["delivery_status"] = result["delivery_status"]
    return JSONResponse(receipt)


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _text(value):
    return escape(str(value if value is not None else "Not available"), quote=True)


def _command(mention, operation, task_id, target):
    prefix = (mention.strip() + " ") if mention else ""
    return prefix + "qa " + operation + " " + task_id + " " + target


def _observed(value):
    if not isinstance(value, dict):
        return "Not available"
    return _text(value.get("final_time")) + "<br>" + _text(value.get("action_status"))


def _review_commands(snapshot, task_id, agent_mention):
    run_id = snapshot["run_id"]
    if not snapshot.get("is_current"):
        return ('<p class="notice"><strong>Historical run.</strong> Its approval cannot complete '
                'the current verification task. <a href="/qa/current">Open the current run</a>.</p>')
    if not snapshot.get("evidence_valid") or snapshot.get("status") not in ("ready", "succeeded", "completed"):
        return ('<p class="notice">Human approval and completion are unavailable while this run is '
                'pending, failed or its required evidence is invalid.</p>')
    if snapshot.get("completion") and snapshot.get("task_status") == "completed":
        return ('<p class="notice">Human review completed for the checked local execution behavior, '
                'using run <code>' + _text(run_id) + '</code>.</p>')
    if snapshot.get("approval"):
        operation, label = "complete", "Complete review of this exact run"
    else:
        operation, label = "approve", "Approve this exact run after inspecting both reports"
    return ('<p>' + label + ' by sending this as your own standalone message in the configured room:</p>'
            '<pre>' + _text(_command(agent_mention, operation, task_id, run_id)) + '</pre>'
            '<p class="muted">Quoted text or an agent saying you approved does not count as human review. '
            'The platform adapter verifies the original author and exact run.</p>')


def render_run(snapshot, *, room_id, task_id, agent_mention="@intent-replay-qa"):
    """Render store-validated observations; never reinterpret a verdict."""
    run_id = snapshot["run_id"]
    base = "/qa/runs/" + quote(run_id, safe="")
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>Intent Replay — QA Room evidence</title><style>',
             'body{margin:0;background:#f6f6f0;color:#173b37;font:16px/1.5 system-ui,sans-serif}'
             'main{max-width:1120px;margin:auto;padding:28px 22px}h1{line-height:1.15}'
             'h2{margin-top:1.8em}a{color:#174f80}code,pre{font:14px/1.5 ui-monospace,monospace;overflow-wrap:anywhere}'
             'pre{white-space:pre-wrap;background:white;padding:14px;border:1px solid #d7dfda}'
             'table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{text-align:left;vertical-align:top;'
             'padding:9px 7px;border-bottom:1px solid #d7dfda;overflow-wrap:anywhere}'
             '.scroll{overflow:auto}.notice{padding:14px 18px;background:#fff9e8;border-left:4px solid #b78115}'
             '.muted{color:#4b6059}dt{font-weight:600}dd{margin:0 0 9px;overflow-wrap:anywhere}'
             'li{margin:8px 0}@media(max-width:650px){main{padding:18px 12px}}',
             '</style></head><body><main><p class="muted">Intent Replay · QA Room</p>',
             '<h1>Review this execution result</h1><dl><dt>Room / task</dt><dd>',
             _text(room_id), ' / ', _text(task_id), '</dd><dt>Run</dt><dd><code>', _text(run_id),
             '</code></dd><dt>Verification status</dt><dd>', _text(snapshot.get("status")),
             '</dd><dt>Human review</dt><dd>', _text(snapshot.get("review_status")),
             '</dd><dt>Current verification</dt><dd>', 'Yes' if snapshot.get("is_current") else 'No — historical run',
             '</dd></dl><p class="muted">This page refers to this exact run. Refresh or ',
             '<a href="/qa/current">open the current run</a> to check for a newer request. ',
             'The server rechecks freshness atomically when review is completed.</p>']
    # A tampered stored summary is not an execution finding. The JSON endpoint
    # retains the record with evidence_valid=false, but never promote it here.
    summary = (snapshot.get("summary") or {}) if snapshot.get("evidence_valid") is True else {}
    parts += ['<h2>Execution findings</h2><p><strong>Frozen regression expectations:</strong> ',
              _text(summary.get("regression_status", summary.get("status"))),
              '. An expected execution FAIL in the deliberately faulty branch can match a passing regression.</p>']
    for role, case in summary.get("cases", {}).items():
        label = "Withdrawal comparison" if role == "withdrawal" else "No-withdrawal control"
        parts += ['<h3>', label, ' · ', _text(case.get("case_id")), '</h3>',
                  '<p>Regression: ', _text(case.get("regression_status", case.get("status"))),
                  ' · execution <code>', _text(case.get("execution_id")), '</code></p>',
                  '<div class="scroll"><table><thead><tr><th>Worker</th><th>Expected booking behavior</th>',
                  '<th>Observed booking behavior</th><th>Execution result</th><th>Frozen expectations</th>',
                  '<th>Factual accuracy</th><th>Overall task</th></tr></thead><tbody>']
        for branch in case.get("branches", []):
            observed = branch.get("observed") or {}
            factual = branch.get("factual_accuracy") or {}
            implementation = branch.get("implementation")
            label = "Guarded" if implementation == "corrected" else _text(implementation)
            parts += ['<tr><td>', label, '</td><td>', _observed(branch.get("expected")),
                      '</td><td>', _observed(observed), '</td><td>',
                      _text(observed.get("instruction_adherence")), '</td><td>',
                      'Match' if branch.get("matches") is True else 'Mismatch / incomplete',
                      '</td><td>', _text(factual.get("status")),
                      ' / unassessed' if factual.get("assessed") is False else '',
                      '</td><td>', _text(branch.get("overall_task")), '</td></tr>']
        parts += ['</tbody></table></div>']
    parts += ['<h2>Open the actual evidence</h2>']
    if snapshot.get("evidence_valid"):
        parts.append('<ul>')
        artifacts = snapshot.get("artifacts") or {}
        for name in sorted(artifacts):
            if not _SAFE_NAME.fullmatch(name) or not name.endswith((".html", ".json", ".zip")):
                continue
            parts += ['<li><a href="', base, '/artifacts/', quote(name, safe=""), '">', _text(name), '</a></li>']
        parts.append('</ul>')
    else:
        parts += ['<p class="notice">Evidence is not available as a validated report for this run.</p>']
        if snapshot.get("evidence_error") or snapshot.get("error"):
            parts += ['<p>', _text(snapshot.get("evidence_error") or snapshot.get("error")), '</p>']
    parts += ['<p><a href="/api/qa/runs/', quote(run_id, safe=""), '">Run identity and review record (JSON)</a></p>',
              '<h2>Next review action</h2>', _review_commands(snapshot, task_id, agent_mention)]
    for key, title in (("approval", "Recorded human approval"), ("completion", "Recorded completion")):
        if snapshot.get(key):
            parts += ['<details><summary>', title, '</summary><pre>',
                      _text(json.dumps(snapshot[key], ensure_ascii=False, indent=2)), '</pre></details>']
    parts += ['<h2>Request another verification</h2><pre>',
              _text(_command(agent_mention, "verify", task_id, "corrected-meta-withdrawal-control")),
              '</pre><p>A new accepted request becomes current before execution begins and invalidates the old approval ',
              'for completing this task, even if the new run remains pending or fails.</p>',
              '<p class="muted">Scope: checked local SQLite booking behavior. Factual and overall-task uncertainty ',
              'remain separate from human review. This does not establish production readiness or external booking success. ',
              'Replay uses saved model captures; any QA-agent inference is a separate activity.</p></main></body></html>']
    return ''.join(parts)


def create_app(store, *, room_id, task_id, agent_mention="@intent-replay-qa",
               dispatch_message=None, dispatch_token=None):
    """Create fixed-scope evidence; opt in to authenticated original-ID dispatch.

    Dispatch refusals return 400 (invalid request/authority) or 409 (current
    state/evidence conflict), with an allowlisted error_code and fixed message.
    The callback must perform the authoritative platform lookup and all normal
    command/review checks. Its token authorizes delivery only, never review.
    """
    if (dispatch_message is None) != (dispatch_token is None):
        raise ValueError("Configure both dispatch_message and dispatch_token, or neither.")
    if dispatch_message is not None and (
            not callable(dispatch_message) or inspect.iscoroutinefunction(dispatch_message)
            or inspect.iscoroutinefunction(getattr(dispatch_message, "__call__", None))
            or not isinstance(dispatch_token, str)
            or not re.fullmatch(r"[A-Za-z0-9._~-]{32,256}", dispatch_token)):
        raise ValueError("Dispatch requires a synchronous callback and a random ASCII bearer token of 32–256 characters.")
    app = FastAPI(title="Intent Replay QA Room evidence", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.qa_room_store = store
    app.state.qa_room_id = room_id
    app.state.qa_task_id = task_id

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers.update(HEADERS)
        return response

    def show(run_id=None):
        if run_id is not None and not _SAFE_NAME.fullmatch(run_id):
            raise HTTPException(404, "Unknown run.")
        try:
            return store.show_run(room_id, task_id, run_id)
        except (ValueError, KeyError, FileNotFoundError):
            raise HTTPException(404, "Run not found in this room and task.") from None

    if dispatch_message is not None:
        @app.post("/api/qa/dispatch")
        async def dispatch(request: Request):
            # Browser fetches cannot use this bridge, even with a leaked token.
            # Authentication precedes reading/parsing any caller-controlled body.
            if "origin" in request.headers or any(key.lower().startswith("sec-fetch-") for key in request.headers):
                raise HTTPException(403, "Browser dispatch is not supported.")
            authorizations = request.headers.getlist("authorization")
            supplied = authorizations[0] if len(authorizations) == 1 else ""
            expected = "Bearer " + dispatch_token
            if not secrets.compare_digest(supplied.encode("utf-8"), expected.encode("ascii")):
                raise HTTPException(401, "Dispatch authentication required.", headers={"WWW-Authenticate": "Bearer"})
            if request.url.query:
                raise HTTPException(400, "Dispatch accepts no query parameters.")
            if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise HTTPException(415, "Dispatch requires application/json.")
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 1024:
                    raise HTTPException(413, "Dispatch request exceeds 1024 bytes.")
                body.extend(chunk)
            try:
                data = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_json_object)
                valid = (isinstance(data, dict) and set(data) == {"message_id"}
                         and isinstance(data["message_id"], str) and _MESSAGE_ID.fullmatch(data["message_id"]))
            except (ValueError, UnicodeError, RecursionError):
                valid = False
            if not valid:
                raise HTTPException(400, "Supply only a valid original message_id in a JSON object.")
            try:
                result = await run_in_threadpool(dispatch_message, data["message_id"])
                return _dispatch_receipt(result, data["message_id"])
            except RoomError as exc:
                return _dispatch_refusal(exc.code)
            except Exception:
                return JSONResponse({"ok": False, "error_code": "dispatch_failed",
                                     "message": "QA dispatch failed. Inspect the configured room and current run before retrying."},
                                    status_code=500)

    @app.get("/qa/current")
    def current():
        snapshot = show()
        return RedirectResponse('/qa/runs/' + quote(snapshot['run_id'], safe=''), status_code=303)

    @app.get("/qa/runs/{run_id}", response_class=HTMLResponse)
    def run_page(run_id: str):
        return HTMLResponse(render_run(show(run_id), room_id=room_id, task_id=task_id, agent_mention=agent_mention))

    @app.get("/api/qa/runs/{run_id}")
    def run_data(run_id: str):
        return JSONResponse(show(run_id))

    @app.get("/qa/runs/{run_id}/artifacts/{name}")
    def artifact(run_id: str, name: str):
        snapshot = show(run_id)
        if (not _SAFE_NAME.fullmatch(name) or name not in (snapshot.get("artifacts") or {})
                or not name.endswith((".html", ".json", ".zip"))):
            raise HTTPException(404, "Unknown evidence artifact.")
        if snapshot.get("evidence_valid") is not True:
            raise HTTPException(409, "Run evidence is unavailable or failed validation.")
        try:
            data = store.read_artifact(room_id, task_id, run_id, name)
        except (ValueError, KeyError, FileNotFoundError):
            raise HTTPException(409, "Evidence failed validation; the artifact is not served.") from None
        media_type = "text/html" if name.endswith(".html") else "application/json" if name.endswith(".json") else "application/zip"
        headers = {"Content-Disposition": 'attachment; filename="' + name + '"'} if name.endswith(".zip") else {}
        return Response(data, media_type=media_type, headers=headers)

    return app
