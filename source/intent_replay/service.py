import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable
from uuid import uuid4

from intent_replay.booking import Implementation, Turn, run_workflow
from intent_replay.evaluator import evaluate
from intent_replay.interpreter import interpret
from intent_replay.meta_client import MODEL_NAME, PROJECT_ROOT
from intent_replay.models import InterpretationResult, ScenarioCatalog


def load_catalog() -> ScenarioCatalog:
    return ScenarioCatalog.model_validate_json((PROJECT_ROOT / "fixtures" / "scenarios.json").read_text(encoding="utf-8"))


def scenario_options() -> dict:
    catalog = load_catalog()
    return {"initial_booking": asdict(catalog.initial_booking), "scenarios": [scenario.model_dump() for scenario in catalog.scenarios], "model": MODEL_NAME}


def run_replay(
    scenario_id: str,
    implementation: Implementation,
    *,
    storage_root: Path | None = None,
    interpreter: Callable[[list[Turn]], InterpretationResult] | None = None,
) -> dict:
    catalog = load_catalog()
    scenario = next((candidate for candidate in catalog.scenarios if candidate.id == scenario_id), None)
    if scenario is None:
        raise ValueError("Unknown scenario.")
    if implementation not in ("faulty", "corrected"):
        raise ValueError("Unknown implementation.")
    started = perf_counter()
    run_id = uuid4().hex
    root = storage_root if storage_root is not None else PROJECT_ROOT / ".local" / "runs"
    root.mkdir(parents=True, exist_ok=True)
    workflow = run_workflow(
        root / f"{run_id}.sqlite3", catalog.initial_booking, catalog.requested_new_time,
        scenario.customer_request, implementation, scenario.slot_available, scenario.final_read_available,
    )
    try:
        interpretation = (interpreter or interpret)(workflow.conversation)
    except Exception:
        interpretation = InterpretationResult(status="error", errors=["Interpretation could not be completed; diagnostic details were withheld."])
    evaluation = evaluate(interpretation, workflow)
    controlled = []
    if implementation == "faulty":
        controlled.append("Deliberately skipped database write when the requested slot is available.")
    if not scenario.final_read_available:
        controlled.append("Final readback directed to an unavailable SQLite database.")
    report = {
        "schema_version": 2,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": round((perf_counter() - started) * 1000),
        "scenario": {"id": scenario.id, "name": scenario.name, "description": scenario.description},
        "implementation": implementation,
        "controlled_fault": implementation == "faulty",
        "customer_request": scenario.customer_request,
        "conversation": [asdict(turn) for turn in workflow.conversation],
        "initial_booking": asdict(workflow.initial_booking),
        "final_booking": asdict(workflow.final_booking) if workflow.final_booking else None,
        "final_state": {"status": workflow.final_state_status, "detail": workflow.final_state_detail},
        "action_trace": [asdict(event) for event in workflow.action_trace],
        "interpretation": interpretation.model_dump(),
        "evaluation": evaluation.model_dump(),
        "provenance": {
            "database": "SQLite", "reset_before_run": True, "independent_final_read": True,
            "interpretation_mode": "mocked interpretation (test double)" if interpreter else "live Meta API",
            "api_call": interpretation.api_call.model_dump(),
            "mocked_components": ["Meta interpretation (test double)"] if interpreter else [],
            "controlled_demonstrations": controlled,
        },
    }
    (root / f"{run_id}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report