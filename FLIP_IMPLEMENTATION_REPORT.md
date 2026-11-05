# Intent Replay — QA Room implementation checkpoint

2026-11-05 · branch `flip-qa-room` · submitted baseline `d074b160d7af890ce7d8d99c2f580c597684a95c` · isolation/setup commit `15a3839933d7add8500fdbefd1c70a009e50f772`.

## Result and current limit

The persistent QA workflow, authenticated Switch adapter and evidence server now handle a **real Mattermost room request automatically through the existing managed agent**. Run A `dd19c14126444bb79ef57882bfa48602` is ready, current and evidence-valid. The exact-run page and both original HTML reports opened in the browser; all six downloads returned HTTP 200. An independent read-only audit passed 46 checks of original message provenance, result delivery, bindings, seals, evaluator results and artifact manifests. Prior checks remain: **143 Python tests pass**, retained corrected Meta regression **2 cases / 4 branch expectations**, and **8 focused MCP tests pass**.

The room request/replay/result milestone is established. **Actual human approval A, followed by B and the stale-A/fresh-B review walkthrough, remains outstanding.** The person has been asked to inspect A's evidence and send its approval in the room. Verification messages were sent by Codex on the user's authorized testing task; approval/completion messages must be sent by the person. No approval or completion was fabricated.

## What existed before Flip

The submitted project already supplied sealed prepared cases, recorded Meta/Baseten model captures, the local SQLite booking runner, independent final reads, faulty/guarded workers, frozen regression expectations, evidence validation and HTML/ZIP exports. Those sources, captures and expectations remain unchanged. The original submitted checkout is clean on `main` at the exact submitted commit. All ten execution-contract files byte-match that commit; contract SHA-256 remains `f7329ae57d934c5a0399755c0d1d7e7e6f42c86975b6067d5fa43a4ed0bbd1dd`.

Baseline preparation evidence is retained in `FLIP_BASELINE_VERIFICATION.json`; its original full preservation inventory was reused instead of regenerating it.

## Added for Flip

- `source/intent_replay/qa_room.py`: a SQLite workflow store, server-owned run IDs/revisions, immutable per-run evidence and an exact-result human review binding.
- `source/intent_replay/qa_room_switch.py`: pinned local Switch Core 0.31.0 authentication, original message lookup, exact command parsing, delivery receipts and deterministic agent result posts.
- `source/intent_replay/qa_room_http.py`: a loopback evidence index, original exporter artifact delivery, and an opt-in authenticated dispatch bridge. Its only mutation input is an original Switch message ID; it rejects browser-origin requests, oversized/extra fields and caller-supplied review claims. It has no browser approval action.
- `source/scripts/run_qa_room.py`: fixed `configure`, `probe`, `serve`, `show` and original-message `dispatch` operations.
- Three focused test modules and the setup, agent-instruction and human-walkthrough documents under `docs/QA_ROOM_*.md`.
- `qa_room_mcp.py`, `run_qa_room_mcp.py` and project `.codex/config.toml`: a single strict original-message-ID MCP transport to the existing authenticated HTTP bridge. Optional dependency pin: `source/requirements-qa-mcp.txt`. No evaluator or workflow semantics change.

Supported task: `booking-withdrawal`. Supported case set: `corrected-meta-withdrawal-control`, using only the two retained corrected Meta prepared files. Room text is never interpreted as a shell command.

## Exact-result review behavior

A verification request makes its new pending run current in the same transaction that records the platform sequence, before execution starts. An old request cannot take over after a newer request, including receipt-recovery after a crash. Pending, failed and late older executions cannot restore an old approval.

Review binds the room/task, run/revision, request sequence, prepared identities, both execution/report identities and execution-contract hash. The adapter fetches the original server-authenticated human event, checks its exact standalone command and pinned identity, and rejects agent messages or quoted approval text. Under the core write lock, approval must follow the finished result, and completion must follow the actual committed approval. Freshness, evidence and completion are checked atomically. Duplicate events remain attached to their original result across restart.

The result-post claim is durable. Ambiguous network posting failures are not automatically resent, because the released agent posting endpoint has no client idempotency key. An interrupted running replay also remains interrupted; a fresh verification can supersede it. This favors an honest unresolved delivery over duplicate side effects.

This local application trusts the installed Switch server and the machine owner. Its hashes detect evidence changes; they do not defend against an owner rewriting all code and storage.

## Verdicts retained

| Case | Faulty worker | Guarded worker |
|---|---|---|
| Withdrawal | Commits 15:00; execution FAIL; expected | Suppresses; retains 14:00; execution PASS |
| No-withdrawal control | Commits 15:00; execution PASS | Commits 15:00; execution PASS |

All four expected branches match. Factual accuracy remains INCONCLUSIVE/unassessed. Overall task is FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Human review is separate and currently unreviewed. Completion only means: “Human review completed for the checked local execution behavior, using run <ID>.”

## Verified checks

- Python discovery from `source`: 143 tests, PASS, exit 0; log `.local/qa-room-development/final-tests.log`.
- Existing saved regression, run once after implementation: 2 cases / 4 branch expectations, PASS; `.local/qa-room-regression/3de3be8198fe409a9fe56e67b51bf141/regression-summary.json`.
- Focused cases include approval, immediate invalidation, stale/wrong-task/unapproved completion, pending/failed reruns, older late results, restart, duplicate delivery, original-human checks, corrupt/missing evidence, source-time ordering and concurrency. Reviewers in these tests are explicitly simulated.
- Live direct transport check: request `sw_182b6aedd9604666bce2f0b20aef387c`, run `702b015c613b4c3c8fdf2511d1876ac1`, one agent result post `sw_236672f42e334a978d937348807e0061`. Dispatch was manually invoked against the actual Switch event. Evidence: `.local/qa-room/direct-smoke-verification.json`.
- Automatic managed-agent check: request `sw_f36a2b41b84b4269a0cf9ba88ed728c2`, run **`50ed6e0dcc144da0adc9409cf9ada895`**, one result post `sw_aa5cd7832a05446d979efcd678bc8925`. Gateway activity confirms the agent's Node tool call and completed turn; no operator dispatch was used for this event. Evidence: `.local/qa-room/automatic-direct-verification.json` and [FLIP_VERIFICATION.json](FLIP_VERIFICATION.json).
- Browser inspection verified the current automatic run and the earlier withdrawal/control reports. Both ZIP bundles contain the original exporter five-file handoff. Human review remains unreviewed. Re-delivering the earlier event through the authenticated HTTP bridge returned its original posted receipt without rerunning or reposting.

The real Mattermost request `sw_b116d44a4e801a59d8f3cd30e64372dc` (sequence 11, source `mattermost`) was automatically dispatched by managed agent revision 6 through `qa_room.dispatch_original_message`. Result `sw_22b4f2385c01448297121bd1d46314ec` (sequence 12) was posted once as the QA agent. Run A's binding is `14e259887a131272446d32aec9216eeadfb889b54a6d765f077bbccd48ec91cb`. Live evidence: [run A](http://127.0.0.1:8054/qa/runs/dd19c14126444bb79ef57882bfa48602). Private proof: `.local/qa-room/mattermost-run-a-verification.json`; independent audit: `.local/qa-room/mattermost-run-a-independent-audit.json`. Read-only SQLite and HTTP checks confirm no actual review/completion records yet.

Replays made **zero new model requests**. The earlier direct-chat integration sent four verification requests; Mattermost integration retained three failed attempts and the successful A request. Managed-agent inference occurred separately. Gateway activity exposes turns/tools, not exact provider model-call or token totals, so those totals remain unmeasured and are not claimed to be zero. Meta/Baseten credentials and balances were not accessed for these replays.

## Installed integration and remaining work

Installed official Switch Console **0.40.1**, native Core **0.31.0**, PostgreSQL **16.14**, and the original managed agent `intent-replay-qa`, rooted in this worktree. The personal native server is `http://127.0.0.1:56741`. After the Windows restart, the connection was backed up and moved to the real private [Mattermost QA room](http://localhost:56742/switch/channels/intent-replay-qa), ID `496e3d1b-8c14-4a6c-9bc5-1e164c0da362`. The adapter administrator joined using the supported membership API; actual Mattermost human client `f97780ca-7e77-4573-902d-e66eb59e9fe7` is pinned.

Docker Desktop **4.98.0**, Engine **29.9.2**, and the dedicated Mattermost container now run successfully. The restart refreshed group membership. A transient Hyper-V memory-allocation error recovered. Exact stale Switch runtime ownership records were preserved and quarantined after their saved PID was confirmed to belong to a different post-reboot Windows process; supported restart recovered the existing agent without deleting session history. Details are in the setup document.

The official standalone `@openai/codex@0.166.0` retains the existing ChatGPT login/model; the prior temporary alpha executable bridges remain removed. Node HTTP dispatch succeeded earlier in direct chat, but two fresh Mattermost requests after reboot both failed with a trusted Node-process exit before reaching the bridge. Read-only database checks confirmed zero final-room runs and receipts. No unsupported fatal cause was inferred from those errors.

The replacement stdio MCP tool forwards only the original event ID to that same HTTP bridge. **Eight focused tests pass** with installed SDK 1.28.1, including stdio initialization, exact single-tool schema, extra-field rejection, bounded transport, safe errors and receipt binding. Baseline Python ran six transport checks and skipped the two optional-SDK tests; no baseline dependency environment was modified. Logs: `.local/qa-room-mcp-tests/`.

The third real-room request correctly stopped because the tool was unavailable: Codex disabled project tools until the worktree's common Git repository was explicitly trusted. The user then approved exactly `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-public-submission-20261104`. Only that project trust entry was added to `C:\Users\asus\.codex\config.toml`, with a private backup; no submitted files or other configuration settings changed. Managed MCP startup succeeded at 22:26:05 UTC. Agent instructions revision 6 preserve model, sandbox and approval settings and tell the agent to handle newly addressed messages without replaying failed history. The next real request produced A successfully. The three earlier attempts remain preserved as failures; none is human review.

Follow [QA_ROOM_SETUP.md](docs/QA_ROOM_SETUP.md) for exact startup/configuration and [QA_ROOM_COMMANDS.md](docs/QA_ROOM_COMMANDS.md) for the human A → review A → B → stale A refused → review/complete B walkthrough. The room path is verified; do not claim the complete human milestone until those actual room actions and bound records are observed.

Official sources used: [Switch resources](https://www.wemakedevs.org/hackathons/switch/resources), [getting started](https://docs.switchagents.ai/switch-rooms/getting-started), [managed agents](https://docs.switchagents.ai/switch-rooms/getting-started/add-a-second-agent), the released Switch Console/Core sources, [Docker Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/), and [Codex CLI](https://learn.chatgpt.com/docs/codex/cli). Released source and observed server metadata take precedence over assumptions about an SDK.

## Reproduce the source package

After the implementation commit, run from this worktree:

```powershell
$qaCommit = git rev-parse --short HEAD
$qaArchive = ".local/intent-replay-flip-$qaCommit.zip"
if (Test-Path -LiteralPath $qaArchive) { throw 'Checkpoint already exists; preserve it.' }
git archive --format=zip --prefix=intent-replay-flip/ --output=$qaArchive HEAD
Get-FileHash -Algorithm SHA256 -LiteralPath $qaArchive
```

This creates a reproducible source checkpoint from the committed tree without overwriting earlier checkpoints. It excludes `.local/`, credentials, provider logins and runtime databases. It is not evidence that the outstanding human walkthrough has completed.
