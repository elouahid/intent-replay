# Intent Replay — QA Room implementation checkpoint

2026-11-05 · branch `flip-qa-room` · submitted baseline `d074b160d7af890ce7d8d99c2f580c597684a95c` · isolation/setup commit `15a3839933d7add8500fdbefd1c70a009e50f772`.

## Result and current limit

Latest 2026-11-07 UTC checkpoint: **the full real-room B/C walkthrough is complete: actual human approval B → fresh C → stale-B refusal → actual human approval and completion C.** B approval `sw_cc26e2db23c2ff3d98607db46364da83` (18) stayed bound to B. Authorized assistant verification at 20 produced C `5aa6bb5509734cb388537a63007d3087` at 21. The assistant's explicitly authorized negative completion probe against old B at 22 received `stale_run` refusal `sw_15092d01154649cb9e4c1c8ab8528fef` (23), with no completion granted by that probe.

The person then approved C with `sw_64e554b42f2ff28f01d8822989a8d8c6` (24), confirmed at 25, and completed C with `sw_cc40b260975f872a9d47d332973d82f2` (26), confirmed by `sw_4f9e4a8c72d74c6996eb12d27c05a456` (27). Approval was recorded at `2026-11-06T23:59:34.550545Z`; completion followed at `2026-11-07T00:02:10.716142Z`. Both bind C's evidence SHA-256 `89205c76d584013579812ed74a1965e5ac6534c5068ea17e9e29b2b31e085648`. C is current/evidence-valid and its human review is completed. B remains historically approved and incomplete. The final database has two approvals and one completion.

The earlier stale-approval audit passed 76 checks before C review; the separate final completion audit also passed **76/76 checks**, including original C events and receipts, timestamps, managed MCP dispatches, exact bindings, retained B history and six unchanged artifact hashes. Final proof: `.local/qa-room-assistant-review/c-human-completion-audit.json`, SHA-256 `f49dd7ecd13ae256ec0ae8d8f7b21bbd4c459f1ac74cc844bd401451863407e6`. The original `mattermost-b-c-stale-approval-audit.json` remains preserved. C's completed status was verified in the browser.

The original human A/B sequence was not performed; the completed demonstration used B/C. B/C approvals and C completion were actual human actions. Verification requests and the refused stale-B probe were authorized assistant actions. No further room command is needed. Application code, evaluator semantics and frozen expectations remain unchanged. Completion concerns the checked local execution behavior; factual accuracy remains INCONCLUSIVE and no production-booking claim follows.

### Preserved A/B checkpoint before the actual B approval

2026-11-06 UTC continuation: the user delegated technical review and approved an assistant-reviewed continuation in this chat. Following the person's scoped browser sign-in and supported agent restart, fresh Mattermost request sequence 15 produced **B `a9ce6b8d4b9f4c1eb6d8cab94d24cd67`** automatically through the existing managed MCP tool. Result sequence 16 was bound to B. B was then current/ready/evidence-valid; A was historical. Both were unreviewed at that capture. A read-only audit passed 56 checks, all six B artifacts returned HTTP 200, and both HTML reports opened in the browser. [The assistant review](docs/QA_ROOM_TECHNICAL_REVIEW.md) supports the included local execution behavior; three isolated simulated stale-review tests passed. The failed sequence-13 request remains recorded separately as an authentication failure that created no run.

The persistent QA workflow, authenticated Switch adapter and evidence server handle **real Mattermost room requests automatically through the existing managed agent**. Original run A `dd19c14126444bb79ef57882bfa48602` remains preserved, ready and evidence-valid; its original audit passed 46 checks. Prior checks remain: **143 Python tests pass**, retained corrected Meta regression **2 cases / 4 branch expectations**, and **8 focused MCP tests pass**. No application code or evaluator semantics changed during this continuation.

At that checkpoint, room request/replay/result and A → B replacement were established, while actual human approval/completion and the live stale-approval walkthrough were incomplete. There was no human approval of A to invalidate. Chat approval and assistant review created no Mattermost human record. The person subsequently approved B and C and completed C, as recorded above; A was never retroactively approved.

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

All four expected branches match. Factual accuracy remains INCONCLUSIVE/unassessed. Overall task is FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. C's human review is separately completed. Completion only means: “Human review completed for the checked local execution behavior, using run <ID>.”

## Verified checks

- Python discovery from `source`: 143 tests, PASS, exit 0; log `.local/qa-room-development/final-tests.log`.
- Existing saved regression, run once after implementation: 2 cases / 4 branch expectations, PASS; `.local/qa-room-regression/3de3be8198fe409a9fe56e67b51bf141/regression-summary.json`.
- Focused cases include approval, immediate invalidation, stale/wrong-task/unapproved completion, pending/failed reruns, older late results, restart, duplicate delivery, original-human checks, corrupt/missing evidence, source-time ordering and concurrency. Reviewers in these tests are explicitly simulated.
- Live direct transport check: request `sw_182b6aedd9604666bce2f0b20aef387c`, run `702b015c613b4c3c8fdf2511d1876ac1`, one agent result post `sw_236672f42e334a978d937348807e0061`. Dispatch was manually invoked against the actual Switch event. Evidence: `.local/qa-room/direct-smoke-verification.json`.
- Automatic managed-agent check: request `sw_f36a2b41b84b4269a0cf9ba88ed728c2`, run **`50ed6e0dcc144da0adc9409cf9ada895`**, one result post `sw_aa5cd7832a05446d979efcd678bc8925`. Gateway activity confirms the agent's Node tool call and completed turn; no operator dispatch was used for this event. Evidence: `.local/qa-room/automatic-direct-verification.json` and [FLIP_VERIFICATION.json](FLIP_VERIFICATION.json).
- Historical direct-run browser inspection verified that automatic run and the earlier withdrawal/control reports. Both ZIP bundles contain the original exporter five-file handoff. Those direct runs remained unreviewed. Re-delivering the earlier event through the authenticated HTTP bridge returned its original posted receipt without rerunning or reposting.

The real Mattermost request `sw_b116d44a4e801a59d8f3cd30e64372dc` (sequence 11, source `mattermost`) was automatically dispatched by managed agent revision 6 through `qa_room.dispatch_original_message`. Result `sw_22b4f2385c01448297121bd1d46314ec` (sequence 12) was posted once as the QA agent. Run A's binding is `14e259887a131272446d32aec9216eeadfb889b54a6d765f077bbccd48ec91cb`. Live evidence: [run A](http://127.0.0.1:8054/qa/runs/dd19c14126444bb79ef57882bfa48602). Private proof: `.local/qa-room/mattermost-run-a-verification.json`; independent audit: `.local/qa-room/mattermost-run-a-independent-audit.json`. At A's original capture, read-only SQLite and HTTP checks found no review/completion records; the later actual B/C approvals and C completion are recorded in the latest checkpoint above.

Fresh B request `sw_2038d700ac6120ad2ddd84c04b7139ca` (sequence 15) produced `sw_1a434e896a694e1db3d5ae3399453cdd` (sequence 16). Gateway activity records completed `qa_room.dispatch_original_message` and the completed managed turn. B binding: `ba73f978df6da5f22bec1b5a9ee2b55b367a6cc4512e8aebd20bf1e71be79630`. A/B proof: `.local/qa-room-assistant-review/mattermost-a-b-evidence-audit.json`; managed activity: `.local/qa-room-assistant-review/run-b-managed-activity.json`. The two runs retain distinct executions and identical frozen prepared inputs. This pre-approval B capture had no human review/completion rows. The subsequent stale-approval audit found one actual B approval and zero completion rows at its capture; the final C completion audit records two approvals and one completion.

Replays made **zero new model requests**. Earlier failed requests remain preserved alongside successful A, B and C; the sequence-13 authentication failure created no run. Managed-agent inference occurred separately. Gateway activity exposes turns/tools, not exact provider model-call or token totals, so those totals remain unmeasured and are not claimed to be zero. Meta/Baseten credentials and balances were not accessed for these replays.

## Installed integration and remaining work

Installed official Switch Console **0.40.1**, native Core **0.31.0**, PostgreSQL **16.14**, and the original managed agent `intent-replay-qa`, rooted in this worktree. The personal native server is `http://127.0.0.1:56741`. After the Windows restart, the connection was backed up and moved to the real private [Mattermost QA room](http://localhost:56742/switch/channels/intent-replay-qa), ID `496e3d1b-8c14-4a6c-9bc5-1e164c0da362`. The adapter administrator joined using the supported membership API; actual Mattermost human client `f97780ca-7e77-4573-902d-e66eb59e9fe7` is pinned.

Docker Desktop **4.98.0**, Engine **29.9.2**, and the dedicated Mattermost container now run successfully. The restart refreshed group membership. A transient Hyper-V memory-allocation error recovered. Exact stale Switch runtime ownership records were preserved and quarantined after their saved PID was confirmed to belong to a different post-reboot Windows process; supported restart recovered the existing agent without deleting session history. Details are in the setup document.

The official standalone `@openai/codex@0.166.0` retains the existing ChatGPT login/model; the prior temporary alpha executable bridges remain removed. Node HTTP dispatch succeeded earlier in direct chat, but two fresh Mattermost requests after reboot both failed with a trusted Node-process exit before reaching the bridge. Read-only database checks confirmed zero final-room runs and receipts. No unsupported fatal cause was inferred from those errors.

The replacement stdio MCP tool forwards only the original event ID to that same HTTP bridge. **Eight focused tests pass** with installed SDK 1.28.1, including stdio initialization, exact single-tool schema, extra-field rejection, bounded transport, safe errors and receipt binding. Baseline Python ran six transport checks and skipped the two optional-SDK tests; no baseline dependency environment was modified. Logs: `.local/qa-room-mcp-tests/`.

The third real-room request correctly stopped because the tool was unavailable: Codex disabled project tools until the worktree's common Git repository was explicitly trusted. The user then approved exactly `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-public-submission-20261104`. Only that project trust entry was added to `C:\Users\asus\.codex\config.toml`, with a private backup; no submitted files or other configuration settings changed. Managed MCP startup succeeded at 22:26:05 UTC. Agent instructions revision 6 preserve model, sandbox and approval settings and tell the agent to handle newly addressed messages without replaying failed history. The next real request produced A successfully. The three earlier attempts remain preserved as failures; none is human review.

Follow [QA_ROOM_SETUP.md](docs/QA_ROOM_SETUP.md) for exact startup/configuration and [QA_ROOM_COMMANDS.md](docs/QA_ROOM_COMMANDS.md) to reopen completed C read-only or intentionally start a future manual run. The real B approval, stale-B refusal and fresh C approval/completion are verified; no further review action is required. [Demo script](docs/FLIP_DEMO_SCRIPT.md), [README](README.md), and [submission draft](docs/FLIP_SUBMISSION.md) are prepared; no Flip publication/submission is claimed.

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

This creates a reproducible source checkpoint from the committed tree without overwriting earlier checkpoints. It excludes `.local/`, credentials, provider logins and runtime databases. The archive excludes private live records; the committed verification document references the retained audit proofs for the completed B/C walkthrough.
