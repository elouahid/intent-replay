# Flip the Switch — Intent Replay handoff

Updated 2026-11-07 UTC. **The real B/C walkthrough is complete: actual human B approval → fresh C → refused stale-B completion → actual human C approval and completion. C is current, evidence-valid and completed for the checked local execution behavior. No further review command is needed.**

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

## Current evidence and completed walkthrough

**Run A: `dd19c14126444bb79ef57882bfa48602`** — [open evidence](http://127.0.0.1:8054/qa/runs/dd19c14126444bb79ef57882bfa48602).

Request `sw_b116d44a4e801a59d8f3cd30e64372dc` (sequence 11, November 5) produced result `sw_22b4f2385c01448297121bd1d46314ec` (sequence 12). A remains ready/evidence-valid and is now historical. Its original proof and artifacts remain intact.

**Run B: `a9ce6b8d4b9f4c1eb6d8cab94d24cd67`** — [open evidence](http://127.0.0.1:8054/qa/runs/a9ce6b8d4b9f4c1eb6d8cab94d24cd67).

Request `sw_2038d700ac6120ad2ddd84c04b7139ca` (sequence 15) produced result `sw_1a434e896a694e1db3d5ae3399453cdd` (16). The person then posted exact approval `sw_cc26e2db23c2ff3d98607db46364da83` (18), confirmed by the agent at sequence 19. Its pinned human identity, exact B run and evidence binding were verified before requesting C. B is now historical, with its original approval retained and completion unavailable. The earlier plain-text message at sequence 17 did not create approval.

**Run C: `5aa6bb5509734cb388537a63007d3087`** — [open evidence](http://127.0.0.1:8054/qa/runs/5aa6bb5509734cb388537a63007d3087).

Request `sw_1a5b66cff69446d841a207e674ac70de` (20) produced result `sw_46977430bfda4b8c8984486c32e0d397` (21). After confirming C was current, Codex sent the user-authorized negative test `qa complete ... <B>` as `sw_1e409655fe38cff2539ead5969f4ab89` (22). Agent refusal `sw_15092d01154649cb9e4c1c8ab8528fef` (23) returned **`stale_run`** and “No review completion was granted.” This is a real-room refusal against an actual prior human approval; C verification and the negative test were assistant-operated, not human review actions.

The read-only B/C stale-approval audit passed **76/76 checks** before C's review. All six C artifacts and both HTML reports were verified. At that capture, B's approval remained bound only to B, C had no approval/completion and no completion rows existed. That proof is preserved as `.local/qa-room-assistant-review/mattermost-b-c-stale-approval-audit.json`; the pre-C proof is `b-actual-approval-before-c.json` in that directory.

The person then posted exact C approval `sw_64e554b42f2ff28f01d8822989a8d8c6` (24), confirmed at 25, and exact completion `sw_cc40b260975f872a9d47d332973d82f2` (26), confirmed by `sw_4f9e4a8c72d74c6996eb12d27c05a456` (27). C completed at **2026-11-07 00:02:10.716142 UTC**. Both records bind C's evidence SHA-256 `89205c76d584013579812ed74a1965e5ac6534c5068ea17e9e29b2b31e085648`. Proofs: `c-actual-approval-before-completion.json` and `c-actual-completion.json` in the same private directory. [Verification records](FLIP_VERIFICATION.json) retain exact provenance.

The separate final completion audit passed **76/76 checks** and the browser showed C completed. Proof: `.local/qa-room-assistant-review/c-human-completion-audit.json`, SHA-256 `f49dd7ecd13ae256ec0ae8d8f7b21bbd4c459f1ac74cc844bd401451863407e6`. It confirms two approvals, one completion and unchanged artifact hashes.

The completed demonstration used B/C; the original human A/B sequence was not performed. Human approvals of B and C and completion of C came from the person's actual room actions. Verification requests and the refused stale-B probe were authorized assistant actions. Reopen [C's evidence](http://127.0.0.1:8054/qa/runs/5aa6bb5509734cb388537a63007d3087) read-only; no further command is required. See [commands](docs/QA_ROOM_COMMANDS.md) for future manual runs.

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

Keep `serve` running. [Current evidence](http://127.0.0.1:8054/qa/current) is read-only. A false Console-user comparison in `probe` is expected with the Mattermost client pin; original room identity is checked separately. Never print/package dispatch tokens, credentials or runtime databases. Detailed paths/recovery: [setup](docs/QA_ROOM_SETUP.md). Implementation and limits: [report](FLIP_IMPLEMENTATION_REPORT.md). Preserve this completed C checkpoint; another accepted verification would require a fresh review.
