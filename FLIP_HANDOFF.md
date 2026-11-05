# Flip the Switch — Intent Replay handoff

Updated 2026-11-05. The QA workflow is implemented and tested; the actual messaging-room/human-review demonstration is still pending. Continue in this worktree, not the original `hackthons` folder.

## Latest resume checkpoint — real room running, tool trust pending

The full Windows restart resolved `docker-users` token membership. Docker Desktop 4.98.0 / Engine 29.9.2 now responds, native Switch is healthy, and dedicated container `switchdash-local-mattermost-mattermost-1` is healthy. A transient Hyper-V 2 GB allocation failure recovered; no reinstall or security-policy change was made.

The real private [Intent Replay QA room](http://localhost:56742/switch/channels/intent-replay-qa) exists: room `496e3d1b-8c14-4a6c-9bc5-1e164c0da362`, bridge `7b6daa01-6bf8-43e0-b4f2-71d30a21e9e3`. The original agent is connected, revision 5. Its actual Mattermost human sender is pinned as client `f97780ca-7e77-4573-902d-e66eb59e9fe7`. The adapter's administrator joined through the supported chat-membership API so original events are readable. Direct-room history/configuration was preserved before updating `.local/qa-room/connection.json`.

The reboot exposed stale Switch owner files naming a PID now assigned to `svchost`. Four exact obsolete runtime files were hash-checked and renamed with `.preboot-20261105-preserved`; no unrelated process or session history was removed. Supported agent restart succeeded. See the incident record in [QA_ROOM_SETUP.md](docs/QA_ROOM_SETUP.md).

Two real Mattermost requests (`sw_bb01ce3f665773f8056b904782f5ce97`, `sw_9a3d735148603160b10808e8c9f4be5a`) encountered `trusted Node process exited unexpectedly; kernel reset, rerun your request`. Neither reached the dispatcher: no new room run or receipt. A transport-only MCP wrapper now forwards one original message ID to the **same** HTTP bridge; eight focused tests pass, including the official SDK stdio handshake. It uses installed SDK 1.28.1 and leaves sandbox/approval settings unchanged.

The third request (`sw_2f02f3788ff4138862893e26454e6900`) could not discover that tool. Actual managed Codex startup logs and a no-inference MCP catalog probe establish that the project's `.codex/config.toml` is **disabled pending explicit trust of the common Git repository**: `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-public-submission-20261104`. An earlier configuration-only probe appeared enabled; actual startup/catalog evidence supersedes it. The user has been asked to approve that exact project-trust entry. **Do not change trust or repeat a room request before that answer and a successful MCP catalog preflight.** No real Mattermost replay or human approval/completion is claimed yet.

After trust is resolved: verify `qa_room` exposes `dispatch_original_message` in the managed provider's MCP catalog; make one real room request; verify its evidence; guide actual human approval A, then request B and observe stale A refusal before the person's fresh B review. Never send review commands on the person's behalf.

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
- Default `.local/qa-room/connection.json` now targets the verified Mattermost room above; previous direct-chat configuration is backed up beside it.
- Private references resolve into the Codex MSIX `LocalCache\Roaming\switchdash` profile. After sign-out, resume this Codex chat and launch/check the same existing server/agent; do not assume an ordinary Start-menu launch or generic `--user-data-dir` selects that profile. Exact paths and checks are in [QA_ROOM_SETUP.md](docs/QA_ROOM_SETUP.md).
- Docker/Mattermost are running. The embedded Mattermost UI uses source `mattermost` and the verified client pin, not the former Console user-ID pin. The evidence listener was restarted with that scope.

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
