# Flip the Switch — Intent Replay handoff

Updated 2026-11-05. The QA workflow is implemented and tested; the actual messaging-room/human-review demonstration is still pending. Continue in this worktree, not the original `hackthons` folder.

## Baseline and preservation

- Submitted baseline: **`d074b160d7af890ce7d8d99c2f580c597684a95c`**; setup commit: `15a3839933d7add8500fdbefd1c70a009e50f772`.
- Worktree: **`C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip`**, branch **`flip-qa-room`**. Application: its `source` directory.
- Shared Git/submitted checkout: `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-public-submission-20261104`. Keep it: this worktree uses its Git metadata. Its `main` remains clean at the submitted commit.
- Submission confirmation, verification and archive files established this baseline, rather than the earlier review commit `17743c7` or the uncommitted outer repository.
- Submitted archive: `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-submitted-source-20261104.zip`; SHA-256 `675c58efe37004833d99f051512dabe44209e8e89481303f9c9e469139732292`.
- Reused [FLIP_BASELINE_VERIFICATION.json](FLIP_BASELINE_VERIFICATION.json): 107 archive/Git matches, 106 manifest payload hashes and 28,486 original files preserved. Do not repeat the giant inventory without a new reason.
- All ten runner/evaluator contract files still byte-match baseline. Contract SHA-256: `f7329ae57d934c5a0399755c0d1d7e7e6f42c86975b6067d5fa43a4ed0bbd1dd`. Saved cases, expectations, captures and submitted reports are unchanged.

## Added scope

One person, one Console-managed QA agent, one personal Switch messaging room and the retained local booking workflow. Operations: verify, show, approve an exact run, complete review of that exact run. Task `booking-withdrawal`; case set `corrected-meta-withdrawal-control`.

`qa_room.py` persists immutable run evidence and review bindings. Acceptance makes the new pending run current before execution, atomically with platform sequence ordering. Failed/pending reruns and late older results cannot restore old approval. Completion checks current run, evidence, human identity and original event time under the same transaction. Duplicate events are durable and idempotent.

`qa_room_switch.py` retrieves the original authenticated Gateway event and posts deterministic results as the QA agent. `qa_room_http.py` serves the existing exports plus an opt-in, bearer-authenticated local bridge that accepts **only an original message ID**. The managed agent uses Node `http.request`, not shell commands or browser JavaScript. CLI dispatch remains an operator diagnostic.

Regression PASS includes expected faulty withdrawal execution FAIL. Guarded withdrawal suppresses the change and retains 14:00; both no-withdrawal control workers commit 15:00. Factual accuracy remains INCONCLUSIVE/unassessed; overall task remains FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Human review is separate and has not been fabricated.

## Current integration

- Installed Switch Console **0.40.1**, native Core **0.31.0**, gateway `http://127.0.0.1:56741`.
- Agent `intent-replay-qa`, ID `e9d69e59-a025-4e2d-abea-ce114dc448f8`, correct worktree, official standalone Codex **0.166.0** through npm. Existing ChatGPT login/model retained; temporary alpha executable bridges removed, original desktop installation intact.
- Default `.local/qa-room/connection.json` currently targets Console **direct chat** `95574125-421c-4810-bdc2-d47822117d2b`. This is not the final Mattermost-backed room.
- Private references resolve into the Codex MSIX `LocalCache\Roaming\switchdash` profile. After sign-out, resume this Codex chat and launch/check the same existing server/agent; do not assume an ordinary Start-menu launch or generic `--user-data-dir` selects that profile. Exact paths and checks are in [QA_ROOM_SETUP.md](docs/QA_ROOM_SETUP.md).
- Docker Desktop **4.98.0** installed with existing Hyper-V. `asus` is in `docker-users`, but its old login token caused Docker's membership check to fail. **Save open work, sign out of Windows, then sign back in** before rechecking Docker. No automatic sign-out/restart was performed.
- Then enable Switch **Admin → Status → Run Mattermost**, create one personal **Intent Replay QA** room using the existing agent, back up/update the verified room ID in connection configuration, and restart the evidence listener. Prefer Console messages inside that actual room so the existing human user-ID pin remains valid.

## Evidence and continuation

- **143 Python tests pass.** The existing corrected-pair regression was run once: 2 cases / 4 matched expectations. Logs: `.local/qa-room-development/`; saved regression: `.local/qa-room-regression/3de3be8198fe409a9fe56e67b51bf141/`.
- Live direct-chat transport check: authentic event → manually invoked dispatcher → existing replay → one authenticated result post. Run `702b015c613b4c3c8fdf2511d1876ac1`; both original reports opened in the browser and all six artifacts returned HTTP 200. Still unreviewed. Evidence: `.local/qa-room/direct-smoke-verification.json`.
- Automatic managed-agent HTTP dispatch **passed** in the direct chat: event `sw_f36a2b41b84b4269a0cf9ba88ed728c2` produced current run `50ed6e0dcc144da0adc9409cf9ada895` and one agent post, with no operator dispatch. Browser/HTTP evidence access verified. See [FLIP_VERIFICATION.json](FLIP_VERIFICATION.json). The final messaging-room walkthrough and actual human approval/completion remain pending.
- Replay uses zero new model requests. Switch-agent inference is separate and occurred during integration; do not describe the entire flow as zero inference. Meta/Baseten tokens/free credits remain permitted for future work; keep their existing configuration in place and never copy values into source or reports.

Start the configured service from this worktree:

```powershell
$qaPython = 'C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.venv\Scripts\python.exe'
& $qaPython -B .\source\scripts\run_qa_room.py probe
& $qaPython -B .\source\scripts\run_qa_room.py serve
```

The local evidence index is `http://127.0.0.1:8054/qa/current`. `serve` creates the private `.local/qa-room/dispatch-token`; do not print or package it. State/runs stay under ignored `.local/qa-room/state`.

Continue with [QA_ROOM_SETUP.md](docs/QA_ROOM_SETUP.md), [agent instructions](docs/QA_ROOM_AGENT_INSTRUCTIONS.md) and the exact [human A/B walkthrough](docs/QA_ROOM_COMMANDS.md). Implementation, limitations and source-package commands are in [FLIP_IMPLEMENTATION_REPORT.md](FLIP_IMPLEMENTATION_REPORT.md). Finish the real room interaction and human review before adding features or visual polish.
