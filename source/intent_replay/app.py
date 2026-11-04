import threading
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from intent_replay.meta_client import AttemptBudget, PROJECT_ROOT
from intent_replay.agent_service import load_agent_report, run_agent_replay, saved_agent_reports
from intent_replay.models import ComparisonRequest, FreezeRequest, RunRequest
from intent_replay.service import run_replay, scenario_options
from intent_replay.temporal_service import freeze_scenario, load_frozen, load_pair, run_frozen_pair, save_frozen, saved_pairs, temporal_options


app = FastAPI(title="Intent Replay", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])
app.state.interpreter = None
app.state.storage_root = None
app.state.temporal_storage_root = None
app.state.customer_interpreter = None
app.state.assistant_interpreter = None
app.state.agent_storage_root = None
app.state.agent_responder = None
app.state.agent_assistant_interpreter = None
app.state.recorded_demo_enabled = False
app.state.recorded_demo_examples = []
app.state.benchmark_enabled = False
app.state.benchmark_controller = None
app.state.benchmark_customer_interpreter = None
app.state.benchmark_responder = None
app.state.run_lock = threading.BoundedSemaphore(1)
static_root = PROJECT_ROOT / "intent_replay" / "static"
app.mount("/static", StaticFiles(directory=static_root), name="static")


@app.middleware("http")
async def response_headers(request: Request, call_next):
    if app.state.benchmark_enabled and request.url.path.startswith("/api/") and not request.url.path.startswith("/api/benchmark/") and request.method not in ("GET", "HEAD"):
        response = JSONResponse(status_code=403, content={"detail": "Benchmark mode permits only the new ledger-controlled proposal workflow. Historical live workflows are disabled in this mode."})
    elif app.state.recorded_demo_enabled and request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD"):
        response = JSONResponse(status_code=403, content={"detail": "Recorded demo is read-only. Opening and exporting saved evidence makes no API inference requests."})
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    return JSONResponse(status_code=500, content={"detail": "The replay could not be completed; private diagnostic details were withheld."})


@app.get("/")
def index():
    return FileResponse(static_root / ("benchmark.html" if app.state.benchmark_enabled else "index.html"))


@app.get("/api/demo")
def recorded_demo():
    return {"enabled": app.state.recorded_demo_enabled, "examples": app.state.recorded_demo_examples,
            "notice": "Recorded Meta tool call — saved comparison — no new API requests.",
            "language_trial": "Closed as failed. Frozen validation was prepared but not assessed; full-response factual assessment is experimental."}


@app.get("/api/scenarios")
def scenarios():
    return scenario_options()


def acquire_local_run(request: Request):
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(status_code=403, detail="Only same-origin local requests are allowed.")
    if not app.state.run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A replay is already running. Try again after it completes.")


@app.post("/api/run")
def replay(body: RunRequest, request: Request):
    acquire_local_run(request)
    try:
        return run_replay(body.scenario_id, body.implementation, storage_root=app.state.storage_root, interpreter=app.state.interpreter)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown scenario or implementation.") from None
    except Exception:
        raise HTTPException(status_code=500, detail="The replay could not be completed; private diagnostic details were withheld.") from None
    finally:
        app.state.run_lock.release()


def temporal_root():
    return app.state.temporal_storage_root or PROJECT_ROOT / ".local" / "temporal"


@app.get("/api/temporal/scenarios")
def temporal_scenarios():
    return temporal_options()


@app.post("/api/temporal/freeze")
def freeze(body: FreezeRequest, request: Request):
    acquire_local_run(request)
    try:
        frozen = freeze_scenario(body.scenario_id, customer_interpreter=app.state.customer_interpreter, budget=AttemptBudget(1))
        save_frozen(frozen, temporal_root())
        return frozen.export()
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown or unsupported temporal inputs.") from None
    finally:
        app.state.run_lock.release()


@app.post("/api/temporal/compare")
def compare(body: ComparisonRequest, request: Request):
    acquire_local_run(request)
    try:
        frozen = load_frozen(body.freeze_id, temporal_root())
        return run_frozen_pair(frozen, storage_root=temporal_root(), assistant_interpreter=app.state.assistant_interpreter, budget=AttemptBudget(2))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Frozen inputs were not found.") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Frozen inputs are invalid or have changed.") from None
    finally:
        app.state.run_lock.release()


@app.get("/api/temporal/reports")
def comparisons():
    return {"reports": saved_pairs(temporal_root())}


@app.get("/api/temporal/reports/{pair_id}")
def comparison(pair_id: str):
    try:
        return load_pair(pair_id, temporal_root())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Comparison report was not found.") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Only saved version-3 comparisons can be opened here.") from None


def agent_root():
    return app.state.agent_storage_root or PROJECT_ROOT / ".local" / "agent"


@app.post("/api/agent/run")
def agent_run(body: ComparisonRequest, request: Request):
    acquire_local_run(request)
    try:
        frozen = load_frozen(body.freeze_id, temporal_root())
        return run_agent_replay(
            frozen, storage_root=agent_root(), agent_responder=app.state.agent_responder,
            assistant_interpreter=app.state.agent_assistant_interpreter, budget=AttemptBudget(16),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Frozen inputs were not found.") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Frozen inputs are invalid or unsupported.") from None
    finally:
        app.state.run_lock.release()


@app.get("/api/agent/reports")
def agent_reports():
    reports = saved_agent_reports(agent_root())
    if app.state.recorded_demo_enabled and agent_root() != PROJECT_ROOT / ".local" / "agent":
        identifiers = {r["run_id"] for r in reports}
        reports += [r for r in saved_agent_reports(PROJECT_ROOT / ".local" / "agent") if r["run_id"] not in identifiers]
    return {"reports": reports}


@app.get("/api/agent/reports/{run_id}")
def agent_report(run_id: str):
    try:
        try:
            return load_agent_report(run_id, agent_root())
        except FileNotFoundError:
            if app.state.recorded_demo_enabled:
                return load_agent_report(run_id, PROJECT_ROOT / ".local" / "agent")
            raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Agent report was not found.") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Only saved version-4, version-5 or version-6 agent comparisons can be opened here.") from None


from intent_replay.benchmark_api import router as benchmark_router
app.include_router(benchmark_router)
