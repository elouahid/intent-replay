# Flip the Switch — Intent Replay handoff

Updated 2026-11-06. **Run A's real Mattermost request → managed agent → saved replay → result is verified. The user now authorizes an assistant-reviewed continuation; actual human-room review remains incomplete. The next request stopped before dispatch because the managed Codex login expired.**

2026-11-06 resume: Docker's 2 GB Hyper-V allocation initially failed with `0x800705AA`; after the person closed unused applications, Docker, the existing Switch server/Mattermost room and the evidence listener were restored. Run A and its evidence remained intact. [Codex's technical review](docs/QA_ROOM_TECHNICAL_REVIEW.md) supports the scoped local execution findings but creates no human review. The user's chat approval is separate from Mattermost review. New request `sw_ceb8c35e683bc85544b2f490c8ab56dd` (sequence 13) failed before dispatch with expired-token refresh 401; B does not exist and A remains current/unreviewed. A browser login has been launched for only the existing Mattermost provider home; await the person's successful sign-in, then resume the managed request path without claiming a completed human walkthrough.

## Baseline and isolation

- Submitted baseline: **`d074b160d7af890ce7d8d99c2f580c597684a95c`**, identified from submission/review evidence, not assumed from HEAD.
- Worktree: **`C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip`**, branch **`flip-qa-room`**. Application: `source`. Setup commit: `15a3839933d7add8500fdbefd1c70a009e50f772`.
- Keep shared Git/submitted checkout `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-public-submission-20261104`; its `main` is the submitted baseline and this worktree uses its Git metadata.
- Submitted archive `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-submitted-source-20261104.zip`; SHA-256 `675c58efe37004833d99f051512dabe44209e8e89481303f9c9e469139732292`.
- [Baseline verification](FLIP_BASELINE_VERIFICATION.json): 107 archive/Git matches, 106 manifest payload hashes and 28,486 original files preserved. All ten runner/evaluator contract files remain unchanged; contract SHA-256 `f7329ae57d934c5a0399755c0d1d7e7e6f42c86975b6067d5fa43a4ed0bbd1dd`. Preserve submitted source, reports, captures, configuration and frozen expectations.

## Scope and operating room

One human, the existing managed Switch agent and one Mattermost QA room. Supported task `booking-withdrawal`; saved case set `corrected-meta-withdrawal-control`. Request, inspect, approve an exact run and complete its review. Reuse existing runner/evaluator/exporter semantics.

- [Intent Replay QA room](http://localhost:56742/switch/channels/intent-replay-qa): `496e3d1b-8c14-4a6c-9bc5-1e164c0da362`.
- Agent `intent-replay-qa`: `e9d69e59-a025-4e2d-abea-ce114dc448f8`, revision **6**, correct worktree, existing login/model and sandbox/approval settings.
- Switch Console 0.40.1 / Core 0.31.0; gateway `http://127.0.0.1:56741`; existing server `b82ac60d-6645-491f-aafa-21de5f2e6ee9`.
- Docker Desktop 4.98.0 / Engine 29.9.2 and dedicated Mattermost container are healthy after restart. Exact stale owner records were preserved before supported Switch restart; see [setup](docs/QA_ROOM_SETUP.md).
- `.local/qa-room/connection.json` pins actual Mattermost human client `f97780ca-7e77-4573-902d-e66eb59e9fe7`. Previous direct-room configuration/history is retained.
- The user approved the exact common Git project trust entry in `C:\Users\asus\.codex\config.toml`; it was added with a private backup and no other settings changed. Managed MCP startup and actual dispatch now succeed.

The single project MCP tool `qa_room.dispatch_original_message` forwards only an original event ID to the existing HTTP bridge. The adapter fetches original authenticated author/body/time. New requests become current before execution; approval/completion bind exact run, evidence, sequence and contract, with atomic freshness checks.

## Current evidence and next action

**Run A: `dd19c14126444bb79ef57882bfa48602`** — [open evidence](http://127.0.0.1:8054/qa/runs/dd19c14126444bb79ef57882bfa48602).

Actual Mattermost request `sw_b116d44a4e801a59d8f3cd30e64372dc` (sequence 11, 22:30:05 UTC) was sent by Codex for the authorized verification. The managed agent dispatched automatically and posted result `sw_22b4f2385c01448297121bd1d46314ec` (sequence 12); no operator dispatch. A is ready/current/evidence-valid; regression and guarded/control checks PASS. Exact page and both original HTML reports opened in the browser; all six artifacts returned HTTP 200. Proof: `.local/qa-room/mattermost-run-a-verification.json` and [FLIP_VERIFICATION.json](FLIP_VERIFICATION.json).

**Human review remains unreviewed.** The user delegated the technical review and approved continuing with an assistant-reviewed demo in this chat. This does not create a Mattermost human record. After the scoped sign-in succeeds, request a new verification through the real room and managed agent, inspect B, and show A historical/B current with human review still unreviewed. Preserve the failed sequence-13 request as an authentication failure, not a completed B.

The original actual-human A/B walkthrough remains incomplete. Its stale-approval guard passed three selected isolated tests using explicitly simulated reviewers; logs are under `.local/qa-room-assistant-review/`. Never send human review commands on the person's behalf. [The human walkthrough](docs/QA_ROOM_COMMANDS.md) remains available for a later actual-person demonstration. Prepare concise demo/README/submission materials after the autonomous real-room continuation, clearly labeling the remaining human-review limitation.

## Result distinctions

Withdrawal: faulty commits 15:00 (expected execution FAIL), guarded suppresses and retains 14:00 (PASS). Control: both commit 15:00 (PASS). All four frozen expectations match. Factual accuracy remains INCONCLUSIVE/unassessed; overall task is FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Human review concerns checked local behavior only.

Prior checks: **143 Python tests PASS**, corrected regression 2 cases / 4 matched expectations, **8 focused MCP tests PASS** including real SDK stdio initialization. Historical direct-chat runs and three failed Mattermost attempts remain separate. Saved replay makes zero new model requests; managed-agent inference is separate and exact usage unmeasured. Meta/Baseten tokens/free credits remain permitted; preserve their configuration.

## Exact startup

Open Docker Desktop and check `docker info`. From this resumed Codex environment, focus the preserved Console/profile:

```powershell
Start-Process -FilePath 'C:\Users\asus\AppData\Local\Programs\Switch Console\Switch Console.exe' -ArgumentList 'switchdash://focus'
```

Start the existing native server/Mattermost only if stopped. Open **Your Rooms → Intent Replay QA** for the signed-in room. Start the evidence listener only if this QA service is not already listening on 8054:

```powershell
Set-Location 'C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip'
$qaPython = 'C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.venv\Scripts\python.exe'
& $qaPython -B .\source\scripts\run_qa_room.py probe
& $qaPython -B .\source\scripts\run_qa_room.py serve
```

Keep `serve` running. [Current evidence](http://127.0.0.1:8054/qa/current) is read-only. A false Console-user comparison in `probe` is expected with the Mattermost client pin; original room identity is checked separately. Never print/package dispatch tokens, credentials or runtime databases. Detailed paths/recovery: [setup](docs/QA_ROOM_SETUP.md). Implementation and limits: [report](FLIP_IMPLEMENTATION_REPORT.md). Finish actual human A/B review before adding features or visual polish.
