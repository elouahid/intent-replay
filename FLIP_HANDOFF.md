# Flip the Switch — Intent Replay handoff

Prepared 2026-11-05. Workspace isolation and baseline verification are complete; the Switch QA room and human-review gate are the next implementation scope.

## Verified submitted baseline

- Repository: `https://github.com/elouahid/intent-replay`.
- Submitted commit: `d074b160d7af890ce7d8d99c2f580c597684a95c`.
- Archive: `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-submitted-source-20261104.zip`.
- Archive SHA-256: `675c58efe37004833d99f051512dabe44209e8e89481303f9c9e469139732292`.
- Evidence: the original `intent-replay-submission-confirmation-20261104.json` names that commit/archive and records “Project Submitted”; the corresponding `.verification.json` and `.sha256` corroborate it. Fresh local checks matched all **107 archive files** to Git blobs and the Flip checkout, plus all **106 manifest payload hashes**.
- The earlier public review archive records `17743c7fc26bc8c00ce8873e2b57a92889f38604`; licensing commit `879238983be3545cd69e9546234971d6fafdab30` and the final demo-link commit followed. Use the submitted commit above, not the older review ZIP or the outer folder's source.
- Execution contract: `f7329ae57d934c5a0399755c0d1d7e7e6f42c86975b6067d5fa43a4ed0bbd1dd`. Preserve `.gitattributes` byte handling and the original public manifest as baseline records.

Full verification: [FLIP_BASELINE_VERIFICATION.json](FLIP_BASELINE_VERIFICATION.json). These are local artifact checks; the completed submission was not edited or resubmitted.

## Working location and preservation

- **Worktree:** `C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip`
- **Branch:** `flip-qa-room`, created explicitly from the submitted commit.
- **Application directory:** `C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip\source`
- **Original submitted checkout / shared Git repository:** `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-public-submission-20261104`. Keep this directory: the worktree uses its Git metadata. Its `main` branch stays at the submission commit.
- The outer `hackthons` repository has no commits or tracked files. It was not made into the Flip baseline. Its submissions, reports, captures, recordings and private configuration remain in place.
- Before/after SHA-256 checks found **28,486 original files unchanged**, with none added or removed (Git metadata, dependencies and caches excluded). Fresh Flip checks passed **57 Python tests, 58 UI scenarios and 6 saved cases / 12 branch expectations**; the execution contract is unchanged.
- Put new runs and local evidence under the Flip worktree's ignored `.local/` directory. Do not write into submitted evidence directories or reuse historical output directories. Setup logs and the private preservation inventory are under `.local/flip-setup/`.
- The user permits continued use of Meta and existing baseline-provider tokens/free credits; the packaged providers include Meta and Baseten. Provider access and remaining balances have not been live-checked. Existing credentials stay in `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.env`; reference that file with supported `--env-file` handling when live work is needed. Never copy its values into source, reports or this handoff. Setup made zero provider requests.

## Switch QA room scope

Build a room that requests a supported replay, exposes its evidence, verifies the guarded implementation and no-withdrawal control, then requires human review of that exact verification.

1. Resolve the supported case/provider/prepared-hash selection server-side. Begin with the two corrected Meta cases in `source/repaired_live_proposal_evidence/prepared/`; keep the four original Meta/Baseten prepared cases available. Arbitrary external agents and production booking systems remain outside this initial scope.
2. Assign each verification a fresh server-owned ID and revision. Reuse `benchmark_execution.execute_prepared` and `regression.assess`; preserve sealed inputs, captures, reports, frozen expectations and separate worker executions. Replays perform local SQLite execution without inference.
3. Show the accepted instruction/revision, proposed action, authorization decision, action journal, independent booking read, execution ID and report/prepared hashes. Retained captures remain labeled recorded evidence.
4. Bind human review to the current verification ID/revision, **both withdrawal and control execution IDs**, both report and prepared hashes, and the execution-contract hash. Record reviewer identity, decision and timestamp. An advisory model response is not human approval.
5. Complete verification only through an atomic server-side check of that exact current binding and successful required checks. A new request or rerun supersedes the prior pending review. Delayed, duplicate, wrong-run or stale-tab approvals cannot complete a newer verification; historical review stays attached to its historical run. An exact duplicate may be idempotent only for its own original verification.
6. Missing control, incomplete/error results, unsupported inputs or changed evidence cannot complete verification. Preserve the existing distinction between regression expectation match, execution verdict, factual accuracy, overall-task verdict and human-review status.

For the corrected retained pair (25 November 2026, Europe/London): withdrawal must reproduce faulty **commit 15:00 / execution FAIL** and guarded **suppression, retain 14:00 / execution PASS**; control must let both workers **commit 15:00 / execution PASS**. Expected faulty FAIL is a matching regression. Factual accuracy remains **INCONCLUSIVE / unassessed**; review must not relabel it as factual success.

Acceptance must exercise a successful reviewed pair, approval of run A after run B starts, approval racing a rerun, a stale browser response, modified evidence, missing/failed control and incomplete/error output. The current verification must never inherit an older approval.

## Existing implementation to reuse

Paths below are relative to `source/`:

- `scripts/serve_live_proposal_demo.py`: retained/live entry point; `scripts/serve_submission_demo.py`: supported replay, history and rerun routes.
- `intent_replay/benchmark_execution.py`: prepared validation, fresh execution IDs and sealed reports; its ten `CONTRACT_FILES` define runner/evaluator compatibility. Add the room around this layer initially.
- `intent_replay/temporal.py` and `temporal_evaluator.py`: transaction-time authorization, guarded execution and independent evidence evaluation.
- `intent_replay/regression.py`: completeness/frozen-expectation assessment; CLI exits **0** match, **1** mismatch, **2** invalid/incomplete/error.
- `intent_replay/replay_history.py`, `evidence_handoff.py`, `static/submission.js`: existing exact-report bindings, export and stale-response handling. They do not yet persist a human-approval gate.

## Continue here

Use the new worktree explicitly in this chat; the original chat working directory was `hackthons`. Existing Python 3.13 dependencies can be reused without modifying them:

```powershell
Set-Location 'C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip\source'
$flipPython = 'C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.venv\Scripts\python.exe'
& $flipPython -B scripts/run_saved_regression.py --prepared repaired_live_proposal_evidence/prepared/fresh-withdrawal-meta.json --prepared repaired_live_proposal_evidence/prepared/fresh-control-meta.json --output ../.local/flip-runs
& $flipPython -B scripts/serve_live_proposal_demo.py --port 8054 --profile auto-direct-v2 --retained-capture repaired_live_proposal_evidence --output ../.local/flip-demo
```

The second command serves the existing retained demo at `http://127.0.0.1:8054/demo`; it is not yet the Switch QA room. Generation is disabled in retained mode. New setup validation results and preservation counts are recorded in `FLIP_BASELINE_VERIFICATION.json`; detailed logs stay in `.local/flip-setup/checks/`.
