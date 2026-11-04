"""Explicit opt-in local benchmark API. Historical endpoints keep their contracts."""
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from intent_replay.benchmark_budget import BudgetBlocked
from intent_replay.benchmark_cases import CaseSpec, digest
from intent_replay.benchmark_service import BenchmarkController
from intent_replay.benchmark_targets import TargetConfig
from intent_replay.meta_client import PROJECT_ROOT
from intent_replay.models import Contract

router = APIRouter()


class FreezeBody(Contract):
    case: CaseSpec


class CaptureBody(FreezeBody):
    target: TargetConfig


class ReplayBody(Contract):
    prepared: dict


def controller(request):
    if not request.app.state.benchmark_enabled:
        raise HTTPException(403, "Start with --benchmark to enable the new workflow.")
    return request.app.state.benchmark_controller


def guarded(request, action):
    from intent_replay.app import acquire_local_run
    ctl = controller(request)
    acquire_local_run(request)
    try:
        return action(ctl)
    except (BudgetBlocked, ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from None
    finally:
        request.app.state.run_lock.release()


@router.get("/api/benchmark/status")
def status(request: Request):
    return controller(request).readiness()


@router.get("/api/benchmark/workflow")
def workflow(request: Request):
    ctl = controller(request)
    return ctl.workflow() if hasattr(ctl, "workflow") else {"enabled": False}


@router.get("/api/benchmark/template")
def template():
    return json.loads((PROJECT_ROOT / "fixtures" / "benchmark_cases.v1.json").read_text())


@router.get("/api/benchmark/seed")
def seed(example: Literal["withdrawal", "control"] = "withdrawal"):
    if example == "control":
        # Fixed public fictional capture only; callers cannot select filesystem paths.
        path = PROJECT_ROOT / "benchmark_evidence" / "executions" / "pilot-custom-1-meta-r1.json"
        if not path.is_file():
            raise HTTPException(404, "The packaged no-withdrawal control is unavailable; import its prepared JSON artifact.")
        return json.loads(path.read_text())["prepared"]
    path = PROJECT_ROOT / "benchmark_evidence" / "no-key-prepared-accounted.json"
    if not path.is_file():
        path = PROJECT_ROOT / "benchmark_evidence" / "no-key-prepared.json"
    if not path.is_file():
        raise HTTPException(404, "No packaged prepared capture is available; import a prepared JSON artifact.")
    return json.loads(path.read_text())


@router.post("/api/benchmark/check")
def check(body: FreezeBody, request: Request):
    controller(request)
    errors = body.case.wording_errors()
    return {"status": "unsupported" if errors else "supported", "case_sha256": digest(body.case.model_dump()), "errors": errors, "new_model_requests": 0}


@router.post("/api/benchmark/freeze")
def freeze(body: FreezeBody, request: Request):
    return guarded(request, lambda ctl: ctl.freeze(body.case, interpreter=request.app.state.benchmark_customer_interpreter))


@router.post("/api/benchmark/capture")
def capture(body: CaptureBody, request: Request):
    def run(ctl):
        result = ctl.capture(body.case, body.target, responder=request.app.state.benchmark_responder)
        if result["prepared"]:
            result["execution"] = ctl.replay(result["prepared"])
        return result
    return guarded(request, run)


@router.post("/api/benchmark/replay")
def replay(body: ReplayBody, request: Request):
    return guarded(request, lambda ctl: ctl.replay(body.prepared))


@router.get("/api/benchmark/reports")
def reports(request: Request):
    ctl = controller(request)
    records = []
    for path in ctl.output.glob("*.json"):
        if len(path.stem) == 32:
            data = ctl.report(path.stem)
            records.append({"execution_id": data["execution_id"], "case_id": data["prepared"]["case"]["case_id"], "created_at": data["created_at"]})
    return {"reports": sorted(records, key=lambda r: r["created_at"], reverse=True)}


@router.get("/api/benchmark/reports/{identifier}")
def report(identifier: str, request: Request):
    try:
        return controller(request).report(identifier)
    except FileNotFoundError:
        raise HTTPException(404, "Execution report not found.") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/benchmark")
def page():
    return FileResponse(PROJECT_ROOT / "intent_replay" / "static" / "benchmark.html")


@router.get("/api/benchmark/reports/{identifier}/download/{kind}")
def attachment(identifier: str, kind: Literal["report", "prepared"], request: Request):
    saved = report(identifier, request)
    payload = saved if kind == "report" else saved["prepared"]
    filename = "intent-replay-" + saved["execution_id"] if kind == "report" else "prepared-" + saved["experiment_id"]
    return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="{filename}.json"'})


def configure_benchmark(app, output=None, ledger=None):
    app.state.recorded_demo_enabled = False
    app.state.benchmark_enabled = True
    app.state.benchmark_controller = BenchmarkController(output=output, ledger=ledger)
