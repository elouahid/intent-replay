"""One explicit live Meta proposal followed by the unchanged local replay demo."""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intent_replay.live_proposal_demo import LiveProposal, checked_transport, deny_async_http, AUTO_PROFILE, LEGACY_PROFILE, PROFILES
from scripts.serve_submission_demo import configure as configure_recorded, regression_result


def configure(output, evidence, retained_capture=None, *, profile=AUTO_PROFILE):
    from fastapi import HTTPException, Request
    from fastapi.responses import JSONResponse
    from intent_replay.app import acquire_local_run
    from intent_replay.models import Contract
    from intent_replay.replay_history import ReplayHistory

    if retained_capture and Path(output).resolve().is_relative_to(Path(retained_capture).resolve()):
        raise ValueError("Replay output must be separate from retained evidence.")
    manager = LiveProposal(retained_capture or output, json.loads(Path(evidence).read_text(encoding="utf-8")), retained=bool(retained_capture), profile=profile)
    app = configure_recorded(Path(output) / "replay", Path(evidence))
    app.state.live_proposal = manager

    def refresh():
        ctl = app.state.benchmark_controller
        ctl.snapshot = manager.workflow()
        supported = {(row["case"]["case_id"], "meta"): row["providers"]["meta"]["prepared"]
                     for row in ctl.snapshot["cases"] if row["providers"]["meta"].get("prepared")}
        app.state.replay_history = ReplayHistory(ctl.output, supported, regression_result)

    refresh()

    @app.middleware("http")
    async def live_post_alias(request: Request, call_next):
        # The unchanged application middleware admits only benchmark-prefixed
        # mutations. Rewrite this one exact new route before that middleware;
        # no historical endpoint gains an exception or a transport allowance.
        if request.method == "POST" and request.scope["path"] == "/api/live-proposal/generate":
            request.scope["path"] = "/api/benchmark/live-proposal-generate"
            request.scope["raw_path"] = b"/api/benchmark/live-proposal-generate"
        return await call_next(request)

    @app.get("/api/live-proposal/status")
    def live_status():
        return JSONResponse(manager.status(), headers={"Cache-Control": "no-store"})

    class Generate(Contract):
        pass

    @app.post("/api/benchmark/live-proposal-generate")
    def generate(body: Generate, request: Request):
        acquire_local_run(request)
        try:
            if not manager.status()["can_generate"]:
                raise HTTPException(409, "The single attempt is already consumed or unavailable; no retry.")
            try:
                result = manager.generate()
            except (ValueError, RuntimeError, OSError):
                # Preserve partial files and the consumed marker, never resend.
                result = manager.status()
            refresh()
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        finally:
            request.app.state.run_lock.release()

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8052)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/live-proposal-repair/20261104/runtime")
    parser.add_argument("--evidence", type=Path, default=ROOT / "fresh_case_evidence/workflow.json")
    parser.add_argument("--env-file", type=Path, help="Existing private .env; read in place, never copied")
    parser.add_argument("--retained-capture", type=Path, help="Read-only retained capture directory; no key or inference operation")
    parser.add_argument("--profile", choices=PROFILES, default=AUTO_PROFILE,
                        help="New requests use auto-direct-v2; select legacy-forced-v1 only to inspect earlier retained evidence")
    args = parser.parse_args()
    if not args.retained_capture:
        if args.profile == LEGACY_PROFILE:
            parser.error("The known-invalid legacy forced profile is retained-evidence-only; it cannot dispatch a new request.")
        if not args.env_file or not args.env_file.is_file():
            parser.error("Live mode requires --env-file pointing to the existing private environment file.")
        from dotenv import load_dotenv
        load_dotenv(args.env_file.resolve(), override=True)
    import httpx
    import uvicorn
    app = configure(args.output, args.evidence, args.retained_capture, profile=args.profile)
    guard = checked_transport(app.state.live_proposal, httpx.Client.send)
    with patch("httpx.Client.send", new=guard), patch("httpx.AsyncClient.send", new=deny_async_http):
        print(f"Intent Replay: http://127.0.0.1:{args.port}/demo (one explicit Meta proposal; backup http://127.0.0.1:8048/demo)", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
