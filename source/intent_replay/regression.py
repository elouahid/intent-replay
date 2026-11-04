"""Exit-code regression checks around the existing local booking replay engine.

This is not an evaluator or provider adapter. Frozen expectations are read from
the validated prepared artifact; original execution/factual/task verdicts stay
in the engine's unchanged full report. No campaign ledger is opened.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

from intent_replay.benchmark_cases import check_seal, digest, now
from intent_replay.benchmark_execution import execute_prepared
from intent_replay.benchmark_service import write_new

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("final_time", "action_status", "booking_outcome", "instruction_adherence")
DEFAULTS = [ROOT / "fresh_case_evidence/prepared" / (name + "-meta.json")
            for name in ("fresh-withdrawal", "fresh-control")]


def assess(report, prepared):
    """Check completeness and compare existing observations; never set verdicts."""
    check_seal(report)
    if (report.get("schema_version") != 7
            or report.get("report_type") != "proposal_execution_comparison"
            or digest(report.get("prepared")) != digest(prepared)
            or report.get("runtime", {}).get("location") != "local"
            or report.get("runtime", {}).get("model_requests") != 0
            or report.get("runtime", {}).get("separate_sqlite_files") is not True
            or report.get("runtime", {}).get("fresh_temporary_directory") is not True):
        raise ValueError("Report is not bound to this prepared artifact and fresh local replay.")
    branches = report.get("reports")
    if (not isinstance(branches, list) or len(branches) != 2
            or sorted(b.get("implementation", "") for b in branches) != ["corrected", "faulty"]):
        raise ValueError("Exactly one faulty and one corrected branch are required.")
    checks = []
    for branch in branches:
        name = branch["implementation"]
        if (branch.get("status") != "executed" or branch.get("execution_errors") != []
                or branch.get("proposal_binding") != "PASS"):
            raise ValueError(name + ": execution error or rejected proposal; regression incomplete.")
        evidence = branch.get("final_evidence") or {}
        booking, actions, journal = (evidence.get(k) for k in ("booking", "actions", "journal"))
        if (not isinstance(booking, dict) or not isinstance(actions, list) or len(actions) != 1
                or not isinstance(journal, list) or not journal
                or not evidence.get("accepted_instructions")
                or evidence.get("read_source") != "independent read-only SQLite transaction"
                or type(evidence.get("read_after_sequence")) is not int
                or any(type(e.get("sequence")) is not int for e in journal)
                or evidence["read_after_sequence"] < max(e["sequence"] for e in journal)):
            raise ValueError(name + ": required independent booking/action/read evidence is missing.")
        initial = prepared["case"]["initial_booking"]
        if any(booking.get(k) != initial[k] for k in ("reference", "service", "timezone")):
            raise ValueError(name + ": booking read does not identify the included local booking.")
        evaluation = branch.get("evaluation") or {}
        observed = {
            "final_time": booking.get("starts_at"), "action_status": actions[0].get("status"),
            "booking_outcome": evaluation.get("booking_outcome"),
            "instruction_adherence": branch.get("execution_result"),
        }
        if (not isinstance(observed["final_time"], str) or not observed["final_time"]
                or observed["action_status"] not in ("committed", "suppressed", "rejected")
                or observed["booking_outcome"] not in ("fulfilled", "unfulfilled", "unknown")
                or observed["instruction_adherence"] not in ("PASS", "FAIL", "INCONCLUSIVE")
                or observed["instruction_adherence"] != evaluation.get("instruction_adherence")):
            raise ValueError(name + ": required regression observations are missing or inconsistent.")
        factual = branch.get("factual_accuracy") or {}
        if (factual.get("status") != "INCONCLUSIVE" or factual.get("assessed") is not False
                or evaluation.get("task_verdict") not in ("FAIL", "INCONCLUSIVE")):
            raise ValueError(name + ": proposal-only factual/task uncertainty is missing or inconsistent.")
        expected = deepcopy(prepared["case"]["private_expectations"][name])
        if set(expected) != set(FIELDS):
            raise ValueError(name + ": required frozen expectations are incomplete.")
        matches = expected == observed
        comparison = branch.get("private_expectation_comparison") or {}
        if (comparison.get("expected") != expected or comparison.get("observed") != observed
                or comparison.get("matches") is not matches):
            raise ValueError(name + ": existing expectation comparison disagrees with its evidence.")
        checks.append({"implementation": name, "expected": expected, "observed": observed,
                       "matches": matches, "factual_accuracy": deepcopy(factual),
                       "overall_task": evaluation["task_verdict"]})
    return checks


def print_case(row):
    print(f"{row.get('case_id', row['input_file'])}: REGRESSION {row['status']}")
    for branch in row.get("branches", []):
        print(f"  {branch['implementation']}: {'MATCH' if branch['matches'] else 'MISMATCH'} (expected -> observed)")
        values = []
        for field, label in zip(FIELDS, ("time", "action", "booking", "execution")):
            expected, observed = branch["expected"][field], branch["observed"][field]
            values.append(f"{label} {expected} -> {observed}")
        print("    " + " | ".join(values))
        print(f"    factual {branch['factual_accuracy']['status']} (unassessed); overall {branch['overall_task']}")
    if row.get("error"):
        print("  " + row["error"])
    if row.get("report_file"):
        print("  Full report: " + row["report_file"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, action="append",
                        help="Sealed prepared artifact; repeat for a suite. Default: included Meta withdrawal and control.")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/saved-regressions",
                        help="Parent for a new run directory; existing runs are never overwritten.")
    args = parser.parse_args(argv)
    run_id = uuid4().hex
    directory = args.output.resolve() / run_id
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        print(f"REGRESSION ERROR: cannot create output directory ({type(exc).__name__}).")
        return 2
    rows = []
    print("Intent Replay saved regression | included local SQLite booking backend | 0 new model requests")
    print("Regression PASS means frozen expectations match, including expected execution FAIL.\n")
    for index, path in enumerate(args.prepared or DEFAULTS, 1):
        row = {"input_file": str(path.resolve()), "status": "ERROR", "report_file": None}
        try:
            if path.stat().st_size > 2_000_000:
                raise ValueError("Prepared artifact exceeds the existing 2 MB bound.")
            prepared = json.loads(path.read_text(encoding="utf-8"))
            original_digest = digest(prepared)
            # execute_prepared revalidates seals, supported wording, native calls
            # and source compatibility before running separate local SQLite DBs.
            report = execute_prepared(prepared)
            report_file = directory / f"{index:02d}-report.json"
            # Retain the full actual report before deciding the regression result,
            # including mismatches or incomplete observations returned by engine.
            write_new(report_file, report)
            row["report_file"] = str(report_file)
            if digest(prepared) != original_digest:
                raise ValueError("Replay changed its input artifact; no expectation update is allowed.")
            row.update(case_id=prepared["case"]["case_id"], prepared_sha256=prepared["sha256"],
                       provider=prepared["capture"]["target"]["provider"])
            row["branches"] = assess(report, prepared)
            row["status"] = "PASS" if all(b["matches"] for b in row["branches"]) else "FAIL"
        except Exception as exc:
            # File/JSON/validation/execution/observation failures never become a
            # passing regression. No retry, inference fallback or input repair.
            row["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
        rows.append(row)
        print_case(row)
        print()
    code = 2 if any(r["status"] == "ERROR" for r in rows) else 1 if any(r["status"] == "FAIL" for r in rows) else 0
    summary = {"schema_version": "local-booking-regression-v1", "run_id": run_id, "created_at": now(),
               "scope": "Included local SQLite booking backend only; no external agent compatibility claim.",
               "exit_code": code, "status": "PASS" if code == 0 else "FAIL" if code == 1 else "ERROR",
               "new_model_requests": 0, "cases": rows,
               "note": "Regression matching is separate from execution, factual and overall-task verdicts. Frozen expectations were not updated."}
    try:
        write_new(directory / "regression-summary.json", summary)
    except (OSError, ValueError, TypeError) as exc:
        print(f"REGRESSION ERROR: cannot save summary ({type(exc).__name__}).")
        return 2
    print(f"SUITE {summary['status']} | {sum(r['status'] == 'PASS' for r in rows)}/{len(rows)} cases match | exit {code}")
    print("Summary: " + str(directory / "regression-summary.json"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
