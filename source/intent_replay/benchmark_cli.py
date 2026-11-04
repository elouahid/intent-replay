"""Explicit controller commands. Default application/recorded replay is no-key."""
import argparse
import json
from pathlib import Path

from intent_replay.benchmark_budget import BudgetBlocked, Ledger
from intent_replay.benchmark_cases import CaseSpec, digest, now
from intent_replay.benchmark_service import BenchmarkController, write_new
from intent_replay.benchmark_targets import TargetConfig
from intent_replay.meta_client import PROJECT_ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    funding = sub.add_parser("funding", help="Record a verified account/rate attestation, never a key.")
    funding.add_argument("--provider", choices=("meta", "baseten", "modal"), required=True)
    funding.add_argument("--proof", type=Path, required=True)
    sub.add_parser("capability", help="At most one of the two allowed explicit Baseten capability requests; no retry.")
    pilot = sub.add_parser("pilot", help="Run/resume only the two approved fixed pilot cases; preserves failures.")
    pilot.add_argument("--provider", choices=("meta", "baseten"), required=True)
    expansion = sub.add_parser("expansion", help="Only the gated six-case, two-target, three-repetition campaign; no repair loop.")
    expansion.add_argument("--integrity", type=Path, required=True)
    expansion.add_argument("--pilot-directory", type=Path, required=True)
    replay = sub.add_parser("replay", help="Revalidate prepared artifact and execute pair, zero inference.")
    replay.add_argument("--prepared", type=Path, required=True)
    replay.add_argument("--modal", action="store_true")
    args = parser.parse_args(argv)
    ctl = BenchmarkController(args.output)
    if args.command == "funding":
        result = ctl.ledger.funding(args.provider, json.loads(args.proof.read_text()))
        print(json.dumps({"provider":args.provider,"funding_attestation_recorded":True,"source":result["source"]}))
        return 0
    if args.command == "status":
        value = ctl.readiness()
    elif args.command == "capability":
        value = ctl.capability()
    elif args.command == "replay":
        prepared = json.loads(args.prepared.read_text())
        if args.modal:
            from intent_replay.benchmark_modal import run_modal
            value = run_modal(prepared, ctl.ledger, ctl.output)
        else:
            value = ctl.replay(prepared)
    elif args.command == "expansion":
        manifest = json.loads((PROJECT_ROOT / "fixtures/benchmark_cases.v1.json").read_text())
        cases = [CaseSpec.model_validate(data) for data in manifest["cases"]]
        integrity = json.loads(args.integrity.read_text())
        offline = json.loads((PROJECT_ROOT / integrity["offline_verification"]).read_text())
        if not offline.get("passed") or offline.get("new_model_requests") != 0 or any(offline["external_http_blocked_attempts"].values()) or not offline["staged_cpu_worker"]["passed"]:
            raise BudgetBlocked("Recorded offline regression/worker verification did not pass.")
        pilots = [json.loads(p.read_text()) for p in args.pilot_directory.glob("*.json") if len(p.stem) == 32]
        ctl.authorize_expansion_preparation(cases,pilots,integrity=integrity["checks"])
        freeze_rows = []
        for case in cases:
            result = ctl.freeze(case,phase="expansion")
            record = result.get("record",result)
            freeze_rows.append({"case_id":case.case_id,"status":record["status"],"reused":result.get("reused",False)})
        from uuid import uuid4
        write_new(ctl.output / ("expansion-freezes-"+uuid4().hex+".json"),{"cases":freeze_rows})
        if any(r["status"] != "valid" for r in freeze_rows):
            raise BudgetBlocked("At least one of the six freezes is invalid/incomplete. No expansion actor campaign was started; no repair request is authorized.")
        ctl.expansion_gate(cases)
        rows = []
        for case in cases:
            for provider in ("meta","baseten"):
                for repetition in (1,2,3):
                    config = TargetConfig(provider=provider)
                    result = ctl.capture(case,config,phase="expansion",repetition=repetition)
                    row = {"case_id":case.case_id,"provider":provider,"repetition":repetition,"capture_status":result["status"],"capture_reused":result["reused"]}
                    if result["prepared"]:
                        execution = ctl.replay(result["prepared"])
                        row.update(execution_id=execution["report"]["execution_id"],repeated_experiment=execution["repeated_experiment"],execution_results=[b["execution_result"] for b in execution["report"]["reports"]])
                    else:
                        row["errors"] = result["capture"]["errors"]
                    rows.append(row)
                    print(json.dumps(row),flush=True)
        value = {"version":"benchmark-expansion-summary-v1","created_at":now(),"rows":rows,"accounting":ctl.ledger.export(),
                 "paired_outcomes_are_correlated":True,"independent_human_pilot":False}
        write_new(ctl.output / ("expansion-summary-"+uuid4().hex+".json"),value)
    else:
        manifest = json.loads((PROJECT_ROOT / "fixtures/benchmark_cases.v1.json").read_text())
        config = TargetConfig(provider=args.provider)
        rows = []
        for data in manifest["cases"][:2]:
            case = CaseSpec.model_validate(data)
            row = {"case_id":case.case_id,"case_sha256":digest(data),"provider":args.provider}
            try:
                frozen = ctl.freeze(case)
                row["freeze_reused"] = frozen.get("reused",False)
                record = frozen.get("record",frozen)
                row["freeze_status"] = record["status"]
                if record["status"] != "valid":
                    row["errors"] = record.get("errors",[])
                else:
                    captured = ctl.capture(case,config)
                    row["capture_status"] = captured["status"]
                    row["capture_reused"] = captured["reused"]
                    if captured["prepared"]:
                        # A restart reuses inference; repeated compute is labeled separately.
                        executed = ctl.replay(captured["prepared"])
                        row["execution_id"] = executed["report"]["execution_id"]
                        row["repeated_experiment"] = executed["repeated_experiment"]
                        row["branch_execution_results"] = [b["execution_result"] for b in executed["report"]["reports"]]
                    else:
                        row["errors"] = captured["capture"]["errors"]
            except (BudgetBlocked, ValueError, RuntimeError) as exc:
                row["status"] = "blocked_or_incomplete"
                row["errors"] = [str(exc)]
            rows.append(row)
        value = {"version":"benchmark-pilot-summary-v1","created_at":now(),"rows":rows,"accounting":ctl.ledger.export(),
                 "expansion":"Not automatic. Requires both native targets and recorded integrity gate; failures are not repair authorizations."}
        from uuid import uuid4
        write_new(ctl.output / ("pilot-"+args.provider+"-"+uuid4().hex+".json"),value)
    print(json.dumps(value,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
