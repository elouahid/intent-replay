# Flip the Switch — Intent Replay handoff

Updated 2026-11-06 UTC. **A and B completed through real Mattermost requests → the existing managed agent → saved replay → room results. B is current, evidence-valid and unreviewed; A is historical. Assistant review is complete for the included local execution evidence. Actual human-room approval/completion remains incomplete.**

Recovery preserved A and its evidence. Docker's 2 GB Hyper-V allocation failure (`0x800705AA`) resolved after the person freed memory. Request sequence 13 then failed before dispatch with expired-token refresh 401; it created no B. The person completed browser sign-in for the existing Mattermost provider home, and supported agent restart succeeded. Fresh sequence 15 produced B automatically. Only the scoped login was refreshed; global authentication and provider credential configuration were unchanged. Baseline files and evaluator semantics were preserved. The user's chat approval authorizes this assistant-reviewed continuation; it is not a Mattermost review record.

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

Request `sw_b116d44a4e801a59d8f3cd30e64372dc` (sequence 11, November 5) produced result `sw_22b4f2385c01448297121bd1d46314ec` (sequence 12). A remains ready/evidence-valid and is now historical. Its original proof and artifacts remain intact.

**Run B: `a9ce6b8d4b9f4c1eb6d8cab94d24cd67`** — [open evidence](http://127.0.0.1:8054/qa/runs/a9ce6b8d4b9f4c1eb6d8cab94d24cd67).

Request `sw_2038d700ac6120ad2ddd84c04b7139ca` (sequence 15, November 6, 23:30:20 UTC) produced result `sw_1a434e896a694e1db3d5ae3399453cdd` (sequence 16). Both requests were sent by Codex through the actual Mattermost UI for authorized verification; the managed agent automatically dispatched them, with no operator dispatch. B is ready/current/evidence-valid. Both HTML reports opened; all six artifacts were checked. [Verification records](FLIP_VERIFICATION.json) and [assistant technical review](docs/QA_ROOM_TECHNICAL_REVIEW.md) retain exact identities and evidence.

**Neither A nor B has human approval or completion.** The live demonstration establishes A historical/B current, not invalidation of an actual prior human approval. Three selected isolated tests passed the stale-review guards using simulated reviewers. To review B, personally inspect both reports, send `@intent-replay-qa qa approve booking-withdrawal a9ce6b8d4b9f4c1eb6d8cab94d24cd67`, wait for confirmation, then personally send the corresponding `qa complete` command. A full actual-human stale-approval demonstration can continue as B → human approval B → new C → stale B refused → human review C. See [commands](docs/QA_ROOM_COMMANDS.md).

Prepared materials: [README](README.md), [concise demo script](docs/FLIP_DEMO_SCRIPT.md), and [submission draft](docs/FLIP_SUBMISSION.md). Nothing has been published or submitted for Flip.

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

Keep `serve` running. [Current evidence](http://127.0.0.1:8054/qa/current) is read-only. A false Console-user comparison in `probe` is expected with the Mattermost client pin; original room identity is checked separately. Never print/package dispatch tokens, credentials or runtime databases. Detailed paths/recovery: [setup](docs/QA_ROOM_SETUP.md). Implementation and limits: [report](FLIP_IMPLEMENTATION_REPORT.md). The remaining milestone is actual human review; preserve its incomplete status until original room actions are observed.
