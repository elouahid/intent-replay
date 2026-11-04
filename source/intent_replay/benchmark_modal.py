"""Optional ephemeral Modal CPU runner; inference remains in the local controller."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from decimal import Decimal
from uuid import uuid4

from intent_replay.benchmark_budget import BudgetBlocked
from intent_replay.benchmark_execution import validate_prepared
from intent_replay.meta_client import PROJECT_ROOT

# Explicit dependency closure, not a directory upload. No .env, reports or history.
WORKER_FILES = ("__init__.py", "benchmark_cases.py", "benchmark_targets.py", "benchmark_execution.py", "benchmark_modal.py", "benchmark_budget.py", "models.py", "booking.py",
                "temporal.py", "temporal_evaluator.py", "temporal_interpreter.py", "temporal_service.py", "interpreter.py", "evaluator.py", "meta_client.py", "agent_adapter.py")
WORKER_PACKAGES = ("pydantic>=2.10,<3", "openai>=2,<3", "python-dotenv>=1,<2", "tzdata>=2025.1,<2027")


def stage_worker(destination):
    destination = Path(destination)
    package = destination / "intent_replay"
    package.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in WORKER_FILES:
        source = PROJECT_ROOT / "intent_replay" / name
        content = source.read_bytes()
        (package / name).write_bytes(content)
        hashes["intent_replay/" + name] = hashlib.sha256(content).hexdigest()
    return hashes


def cloud_pair(artifact):
    """Runs inside a private Function. Never receives credentials or native history."""
    from intent_replay.benchmark_execution import execute_prepared
    provider_names = ("MODEL_API_KEY", "BASETEN_API_KEY", "OPENAI_API_KEY")
    if any(os.getenv(k) for k in provider_names):
        raise RuntimeError("Worker must not have provider credentials.")
    return execute_prepared(artifact, location="modal")


def run_modal(artifact, ledger, output):
    validate_prepared(artifact)
    profile = Path.home() / ".modal.toml"
    if not profile.is_file() and not (os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET")):
        raise BudgetBlocked("Modal cloud execution blocked: no existing local CLI/API profile. Signed-in browser access is separate; no token was created.")
    # The proof must include the actual grant/expiry, not an authentication token.
    with ledger.transaction() as db:
        proof = ledger.require_funding(db, "modal")
        if "unverified" in proof["expiration_note"].lower() or "unknown" in proof["expiration_note"].lower():
            raise BudgetBlocked("Modal grant expiration is unverified; no cloud invocation.")
        reservations = ledger.setting(db, "modal_reservations") or []
        if "salahelouahid" not in proof["account_applicability"]:
            raise BudgetBlocked("Modal proof must identify the existing authorized salahelouahid workspace.")
        # Reserve both containers for the full timeout + scaledown interval,
        # plus an explicitly verified build/setup allowance. No guessed rates.
        build = Decimal(proof["image_build_reservation_usd"])
        if build <= 0:
            raise BudgetBlocked("A conservative verified image-build/setup allowance is required.")
        reserve = build + Decimal(2 * 62) * (Decimal(proof["cpu_per_core_second"]) + Decimal("0.5") * Decimal(proof["memory_per_gib_second"]))
        if len(reservations) >= 40 or sum((Decimal(x["reserved_usd"]) for x in reservations),Decimal(0)) + reserve > min(Decimal(5), Decimal(proof["balance_usd"])):
            raise BudgetBlocked("Modal conservative credit/usage envelope exhausted.")
        reservation = {"invocation_id": uuid4().hex, "experiment_id": artifact["experiment_id"], "reserved_usd": str(reserve), "status": "reserved_unknown"}
        reservations.append(reservation)
        db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("modal_reservations", json.dumps(reservations)))
        ledger.event(db, "modal_reserved", reservation)
    try:
        import modal
    except ImportError:
        raise BudgetBlocked("Optional Modal SDK is not installed. Use requirements-modal.txt in a separate environment; reservation remains conservative.") from None
    from intent_replay.benchmark_service import write_new
    with tempfile.TemporaryDirectory(prefix="intent-replay-modal-source-") as directory:
        source_hashes = stage_worker(directory)
        image = modal.Image.debian_slim(python_version="3.13").pip_install(*WORKER_PACKAGES).add_local_dir(directory, remote_path="/opt/intent-replay")
        application = modal.App("intent-replay-private-execution")
        function = application.function(image=image, cpu=1, memory=512, timeout=60, startup_timeout=60, retries=0, min_containers=0, max_containers=2,
            buffer_containers=0, scaledown_window=2, secrets=[], env={"PYTHONPATH": "/opt/intent-replay"},
            include_source=False, block_network=True, single_use_containers=True)(cloud_pair)
        # app.run is ephemeral Function execution, not deploy or a public web endpoint.
        with application.run():
            report = function.remote(artifact)
        if report["prepared"] != artifact or report["runtime"]["location"] != "modal":
            raise ValueError("Modal returned evidence for a different prepared execution.")
        from intent_replay.benchmark_cases import check_seal
        check_seal(report)
        duplicate = ledger.record_compute(report)
        write_new(Path(output) / (report["execution_id"] + ".json"), report)
        write_new(Path(output) / (report["execution_id"] + "-modal-source.json"), {"allowlist_sha256": source_hashes, "reservation": reservation})
        return {"report": report, "repeated_experiment": duplicate, "new_model_requests": 0}
