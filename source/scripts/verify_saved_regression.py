"""Focused, offline process-level verification of the saved regression command.

The worker rerouting and report mutations below are verification-only seams.
They are never options on the production regression runner. Frozen inputs stay
unchanged; actual subprocess exits and full output are retained in --output.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def child(args):
    source = args.source.resolve()
    sys.path.insert(0, str(source))
    args.output.mkdir(parents=True, exist_ok=True)
    blocked = {"http": 0, "async_http": 0, "socket": 0, "inference": 0}

    def deny(kind):
        def stop(*unused, **unused_kw):
            blocked[kind] += 1
            raise AssertionError("Verification prohibits external operation: " + kind)
        return stop

    async def deny_async(*unused, **unused_kw):
        blocked["async_http"] += 1
        raise AssertionError("Verification prohibits external asynchronous HTTP")

    code = 2
    with ExitStack() as stack:
        stack.enter_context(patch("httpx.HTTPTransport.handle_request", side_effect=deny("http")))
        stack.enter_context(patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=deny_async))
        stack.enter_context(patch("socket.create_connection", side_effect=deny("socket")))
        from intent_replay.temporal import RevisionStore
        from intent_replay.benchmark_cases import seal
        import intent_replay.benchmark_execution as engine
        assert Path(engine.__file__).resolve() == source / "intent_replay/benchmark_execution.py"
        for target in ("intent_replay.meta_client.create_client", "intent_replay.meta_client.OpenAI",
                       "intent_replay.benchmark_targets.OpenAI", "intent_replay.benchmark_targets.request_native"):
            stack.enter_context(patch(target, side_effect=deny("inference")))

        if args.child in ("old_mismatch", "unexpected_worker_outcome"):
            original_execute = RevisionStore.execute
            def unexpected_worker(self, implementation, **kwargs):
                return original_execute(self, "faulty" if implementation == "corrected" else implementation, **kwargs)
            stack.enter_context(patch.object(RevisionStore, "execute", new=unexpected_worker))
            print("VERIFICATION ONLY: corrected worker routed through the existing faulty implementation; frozen expectations unchanged.", flush=True)

        try:
            if args.child == "old_mismatch":
                from intent_replay.benchmark_budget import Ledger
                from intent_replay import benchmark_cli
                ledger = Ledger(args.output / "isolated-old-cli-ledger")
                ledger.fix("inference_closed", "Offline regression CLI reproduction only")
                stack.enter_context(patch("intent_replay.benchmark_service.Ledger", return_value=ledger))
                code = benchmark_cli.main(["--output", str(args.output / "reports"), "replay", "--prepared", str(args.prepared)])
                exported = ledger.export()
                assert exported["requests"] == [] and exported["settings"]["inference_closed"]
            else:
                from intent_replay import regression
                assert Path(regression.__file__).resolve() == source / "intent_replay/regression.py"
                mutation_names = {"missing_booking", "missing_action", "missing_read_provenance", "duplicate_branch", "execution_error", "forged_comparison"}
                if args.child in mutation_names:
                    original_run = regression.execute_prepared
                    def altered_result(*values, **kwargs):
                        report = deepcopy(original_run(*values, **kwargs))
                        branch = report["reports"][1]
                        if args.child == "missing_booking":
                            branch["final_evidence"]["booking"] = None
                        elif args.child == "missing_action":
                            branch["final_evidence"]["actions"] = []
                        elif args.child == "missing_read_provenance":
                            branch["final_evidence"].pop("read_source", None)
                        elif args.child == "duplicate_branch":
                            report["reports"].append(deepcopy(branch))
                        elif args.child == "execution_error":
                            branch["execution_errors"] = ["Controlled verifier execution error"]
                        elif args.child == "forged_comparison":
                            branch["private_expectation_comparison"]["observed"]["final_time"] = "2030-01-01T01:00:00+00:00"
                            branch["private_expectation_comparison"]["matches"] = True
                        return seal(report)
                    stack.enter_context(patch.object(regression, "execute_prepared", new=altered_result))
                    print("VERIFICATION ONLY: returned report altered in memory: " + args.child, flush=True)
                if args.child == "engine_exception":
                    stack.enter_context(patch.object(regression, "execute_prepared", side_effect=RuntimeError("Controlled verifier engine error")))
                run_output = args.output / "runs"
                if args.child == "unwritable_output":
                    run_output.write_text("This file deliberately prevents output directory creation.", encoding="utf-8")
                command = ["--output", str(run_output)]
                if args.prepared:
                    command += ["--prepared", str(args.prepared)]
                def invoke_entrypoint():
                    entrypoint = source / "scripts/run_saved_regression.py"
                    with patch.object(sys, "argv", [str(entrypoint), *command]):
                        try:
                            runpy.run_path(str(entrypoint), run_name="__main__")
                        except SystemExit as exc:
                            return exc.code
                    raise AssertionError("Production entrypoint did not exit explicitly")
                code = invoke_entrypoint()
                if args.child == "repeat_output":
                    old = {str(p.relative_to(run_output)): sha(p) for p in run_output.rglob("*") if p.is_file()}
                    again = invoke_entrypoint()
                    assert code == again == 0
                    assert all(sha(run_output / p) == h for p, h in old.items())
                    assert len(reports(run_output)) == 2
        finally:
            write(args.output / "transport-guards.json", {"blocked_attempts": blocked, "new_model_requests": 0, "new_modal_calls": 0})
    if any(blocked.values()):
        raise AssertionError("An external operation was attempted")
    return code


def reports(directory):
    values = []
    for p in directory.rglob("*.json"):
        try:
            value = read(p)
        except (ValueError, OSError):
            continue
        if isinstance(value, dict) and value.get("schema_version") == 7 and value.get("report_type") == "proposal_execution_comparison":
            values.append((p, value))
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--child", help=argparse.SUPPRESS)
    parser.add_argument("--prepared", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        return child(args)

    source, out = args.source.resolve(), args.output.resolve()
    if out.exists():
        raise ValueError("Choose a new --output directory; previous evidence is never overwritten.")
    out.mkdir(parents=True)
    originals = sorted((source / "fresh_case_evidence/prepared").glob("*.json"))
    before = {p.name: sha(p) for p in originals}
    withdrawal = source / "fresh_case_evidence/prepared/fresh-withdrawal-meta.json"
    control = source / "fresh_case_evidence/prepared/fresh-control-meta.json"
    original = read(withdrawal)
    altered = deepcopy(original)
    altered["case"]["description"] += " invalid seal fixture"
    write(out / "inputs/invalid-seal.json", altered)
    write(out / "inputs/malformed.json", "{malformed")
    result = {"passed": False, "verifier_sha256": sha(Path(__file__).resolve()),
              "method": "Actual Python subprocess exits; real local SQLite replay with external transports and provider factories denied. Test-only worker/report seams never alter frozen inputs.",
              "cases": [], "prepared_files_before": before, "new_model_requests": 0, "new_modal_calls": 0}

    def run(name, expected_exit, prepared=withdrawal, expected_reports=None):
        directory = out / name
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", name,
                   "--source", str(source), "--output", str(directory)]
        if prepared is not None:
            command += ["--prepared", str(prepared)]
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
        write(directory / "stdout.txt", done.stdout)
        write(directory / "stderr.txt", done.stderr)
        found = reports(directory)
        row = {"name": name, "exit_code": done.returncode, "expected_exit_code": expected_exit,
               "report_files": [str(p.relative_to(out)) for p, _ in found]}
        result["cases"].append(row)
        write(directory / "process-result.json", row)
        assert done.returncode == expected_exit, (name, done.returncode, done.stdout, done.stderr)
        guard = read(directory / "transport-guards.json")
        assert not any(guard["blocked_attempts"].values())
        if expected_reports is not None:
            assert len(found) == expected_reports, (name, len(found))
        return found

    try:
        # First reproduce the unchanged old CLI's incorrect success status.
        before_reports = run("old_mismatch", 0, expected_reports=1)
        previous = before_reports[0][1]
        assert previous["reports"][1]["private_expectation_comparison"]["matches"] is False
        assert previous["prepared"] == original
        result["old_cli_false_success_reproduced"] = True

        normal = run("included_pair", 0, prepared=None, expected_reports=2)
        assert {r["prepared"]["case"]["timing"] for _, r in normal} == {"precommit_withdrawal", "no_withdrawal"}
        for _, report in normal:
            assert all(b["private_expectation_comparison"]["matches"] for b in report["reports"])
            assert all(b["factual_accuracy"]["assessed"] is False for b in report["reports"])
            if report["prepared"]["case"]["withdrawal"]:
                assert [b["execution_result"] for b in report["reports"]] == ["FAIL", "PASS"]
        result["expected_faulty_execution_fail_is_regression_pass"] = True

        bad = run("unexpected_worker_outcome", 1, expected_reports=1)[0][1]
        assert bad["prepared"] == original
        assert bad["reports"][1]["final_evidence"]["booking"]["starts_at"] == original["case"]["requested_time"]
        assert bad["reports"][1]["private_expectation_comparison"]["matches"] is False
        assert bad["reports"][1]["private_expectation_comparison"]["expected"] == original["case"]["private_expectations"]["corrected"]
        result["unexpected_actual_local_outcome_nonzero_with_unchanged_expectations"] = True

        for name in ("missing_booking", "missing_action", "missing_read_provenance", "duplicate_branch", "execution_error", "forged_comparison"):
            run(name, 2, expected_reports=1)
        run("engine_exception", 2, expected_reports=0)
        run("invalid_seal", 2, out / "inputs/invalid-seal.json", expected_reports=0)
        run("malformed_json", 2, out / "inputs/malformed.json", expected_reports=0)
        run("missing_input", 2, out / "inputs/missing.json", expected_reports=0)
        run("unwritable_output", 2, expected_reports=0)

        # Two ordinary invocations sharing the same parent output must preserve
        # prior runs. The production runner itself generates unique child dirs.
        run("repeat_output", 0, prepared=control, expected_reports=2)
        result["repeated_output_parent_preserves_prior_files"] = True
        result["prepared_files_after"] = {p.name: sha(p) for p in originals}
        assert result["prepared_files_after"] == before
        result["passed"] = True
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)[:4000]}
    write(out / "verification.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
