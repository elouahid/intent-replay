"""Guided submission demo: saved model evidence and fresh local execution only.

This launcher deliberately has no live, campaign, or credential option.
"""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intent_replay.regression import assess
from intent_replay.benchmark_cases import digest


def regression_command(prepared):
    """Offer a command only for the exact immutable artifact bundled here."""
    case_id = prepared["case"]["case_id"]
    provider = prepared["capture"]["target"]["provider"]
    if case_id not in ("fresh-control", "fresh-withdrawal") or provider not in ("meta", "baseten"):
        return None
    name = f"{case_id}-{provider}.json"
    for directory in ("fresh_case_evidence", "repaired_live_proposal_evidence"):
        path = ROOT / directory / "prepared" / name
        try:
            if digest(json.loads(path.read_text(encoding="utf-8"))) != digest(prepared):
                continue
        except (OSError, ValueError):
            continue
        return {"working_directory": "extracted package source directory",
                "prepared_sha256": prepared["sha256"],
                "powershell": "python -B .\\scripts\\run_saved_regression.py --prepared .\\" + directory + "\\prepared\\" + name}
    return None


def regression_result(report, prepared):
    """Reuse the CLI assessment; retain the execution report on check errors."""
    result = {"schema_version": "selected-booking-regression-v1",
              "execution_id": report["execution_id"], "prepared_sha256": prepared["sha256"],
              "case_id": prepared["case"]["case_id"], "provider": prepared["capture"]["target"]["provider"],
              "status": "ERROR", "exit_code": 2, "branches": [], "command": None}
    try:
        result["branches"] = assess(report, prepared)
        matches = all(b["matches"] for b in result["branches"])
        result.update(status="PASS" if matches else "FAIL", exit_code=0 if matches else 1,
                      command=regression_command(prepared))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return result


def configure(output: Path, evidence: Path):
    from fastapi import HTTPException, Request
    from fastapi.responses import FileResponse, JSONResponse, Response
    from typing import Literal
    from intent_replay.app import app
    from intent_replay.benchmark_api import guarded, report as saved_report
    from intent_replay.benchmark_budget import Ledger
    from intent_replay.development_workflow import RecordedFreshController
    from intent_replay.models import Contract
    from intent_replay.replay_history import ReplayHistory

    ledger = Ledger(output / "closed-authority")
    ledger.fix("inference_closed", "Submission demo: recorded model evidence only")
    app.state.benchmark_enabled = True
    app.state.benchmark_controller = RecordedFreshController(
        json.loads(evidence.read_text(encoding="utf-8")),
        ledger=ledger, output=output / "reports",
    )
    app.state.recorded_demo_enabled = False
    supported = {}
    for row in app.state.benchmark_controller.workflow()["cases"]:
        case_id = row["case"]["case_id"]
        for provider in ("meta", "baseten"):
            stage = row["providers"].get(provider, {})
            prepared = stage.get("prepared")
            if stage.get("status") == "prepared" and prepared and regression_command(prepared):
                if prepared["case"]["case_id"] == case_id and prepared["capture"]["target"]["provider"] == provider:
                    supported[case_id, provider] = prepared
    app.state.replay_history = ReplayHistory(app.state.benchmark_controller.output, supported, regression_result)

    @app.get("/demo", include_in_schema=False)
    async def submission_demo():
        return FileResponse(ROOT / "intent_replay/static/submission.html")

    class SavedReplay(Contract):
        case_id: str
        provider: Literal["meta", "baseten"]
        prepared_sha256: str

    @app.post("/api/benchmark/saved-replay")
    def saved_replay(body: SavedReplay, request: Request):
        def execute(ctl):
            rows = [r for r in ctl.workflow()["cases"] if r["case"]["case_id"] == body.case_id]
            if len(rows) != 1:
                raise ValueError("Exact saved case is missing or ambiguous.")
            stage = rows[0]["providers"].get(body.provider, {})
            prepared = stage.get("prepared")
            if stage.get("status") != "prepared" or not prepared or prepared.get("sha256") != body.prepared_sha256:
                raise ValueError("Exact saved proposal binding is unavailable.")
            if prepared["case"]["case_id"] != body.case_id or prepared["capture"]["target"]["provider"] != body.provider:
                raise ValueError("Saved proposal identity does not match the selection.")
            # Resolve the original object rather than reserializing through JS,
            # which turns e.g. 300.0 into 300 and invalidates its existing seal.
            # Existing replay performs full artifact and source revalidation.
            replay = ctl.replay(prepared)
            return {**replay, "regression": regression_result(replay["report"], prepared)}
        return guarded(request, execute)

    @app.get("/api/benchmark/replay-history")
    def replay_history(request: Request):
        try:
            return JSONResponse(request.app.state.replay_history.list(), headers={"Cache-Control": "no-store"})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/benchmark/replay-history/{identifier}")
    def open_replay(identifier: str, request: Request, expected_report_sha256: str):
        try:
            return JSONResponse(request.app.state.replay_history.open(identifier, expected_report_sha256),
                                headers={"Cache-Control": "no-store"})
        except FileNotFoundError:
            raise HTTPException(404, "Saved execution report was not found.") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    class RerunSavedReplay(Contract):
        expected_report_sha256: str

    @app.post("/api/benchmark/replay-history/{identifier}/rerun")
    def rerun_saved_replay(identifier: str, body: RerunSavedReplay, request: Request):
        def execute(ctl):
            try:
                previous = request.app.state.replay_history.open(identifier, body.expected_report_sha256)
            except FileNotFoundError:
                raise HTTPException(404, "Saved execution report was not found.") from None
            prepared = previous["report"]["prepared"]
            # The exact Python object is loaded from the bound original record;
            # no browser round-trip can normalize 300.0 or replace its capture.
            replay = ctl.replay(prepared)
            fresh = replay["report"]
            if fresh["execution_id"] == identifier or digest(fresh["prepared"]) != digest(prepared):
                raise ValueError("Fresh replay identity or prepared binding was not preserved; result retained for inspection.")
            return {**replay, "regression": regression_result(fresh, prepared), "view_mode": "fresh",
                    "new_executions": 1,
                    "replayed_from": {key: previous["source"][key] for key in
                                      ("execution_id", "report_sha256", "prepared_sha256")}}
        return guarded(request, execute)

    @app.get("/api/benchmark/reports/{identifier}/review-bundle")
    def review_bundle(identifier: str, request: Request):
        from intent_replay.evidence_handoff import build_bundle
        try:
            saved = saved_report(identifier, request)
            if saved.get("execution_id") != identifier:
                raise ValueError("Stored report identity does not match the requested report.")
            payload = build_bundle(saved)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise HTTPException(400, "Review bundle unavailable: " + str(exc)[:300]) from None
        return Response(payload, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="intent-replay-review-{identifier}.zip"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    return app


def deny_http(*args, **kwargs):
    raise RuntimeError("Provider HTTP is disabled in the submission demo")


async def deny_async_http(*args, **kwargs):
    raise RuntimeError("Provider HTTP is disabled in the submission demo")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8048)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/submission-demo")
    parser.add_argument("--evidence", type=Path, default=ROOT / "fresh_case_evidence/workflow.json")
    args = parser.parse_args()
    import uvicorn
    app = configure(args.output, args.evidence)
    with patch("httpx.Client.send", new=deny_http), patch("httpx.AsyncClient.send", new=deny_async_http):
        print(f"Intent Replay guided demo: http://127.0.0.1:{args.port}/demo (no keys; recorded model evidence)", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
