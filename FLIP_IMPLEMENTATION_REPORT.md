# Intent Replay — QA Room implementation checkpoint

2026-11-05 · branch `flip-qa-room` · submitted baseline `d074b160d7af890ce7d8d99c2f580c597684a95c` · isolation/setup commit `15a3839933d7add8500fdbefd1c70a009e50f772`.

## Result and current limit

The persistent QA workflow, authenticated Switch adapter and evidence server are implemented. **143 Python tests pass**, including the existing tests, and the retained corrected Meta regression matches **2 cases / 4 branch expectations**. A real Console direct-chat request was handled automatically by the managed QA agent through the bounded local HTTP bridge, executed by the existing replay runner, and answered through the agent's authenticated relay. Its exact-run page opened in the local browser; all six downloadable artifacts returned HTTP 200. Both original HTML reports were also browser-checked on the earlier transport run.

This checkpoint does **not** establish the requested Mattermost-backed room demonstration or actual human approval. The final room and human A → B review walkthrough remain outstanding. Verification messages were sent by Codex on the user's authorized testing task; approval/completion messages must be sent by the person. No approval or completion was fabricated.

## What existed before Flip

The submitted project already supplied sealed prepared cases, recorded Meta/Baseten model captures, the local SQLite booking runner, independent final reads, faulty/guarded workers, frozen regression expectations, evidence validation and HTML/ZIP exports. Those sources, captures and expectations remain unchanged. The original submitted checkout is clean on `main` at the exact submitted commit. All ten execution-contract files byte-match that commit; contract SHA-256 remains `f7329ae57d934c5a0399755c0d1d7e7e6f42c86975b6067d5fa43a4ed0bbd1dd`.

Baseline preparation evidence is retained in `FLIP_BASELINE_VERIFICATION.json`; its original full preservation inventory was reused instead of regenerating it.

## Added for Flip

- `source/intent_replay/qa_room.py`: a SQLite workflow store, server-owned run IDs/revisions, immutable per-run evidence and an exact-result human review binding.
- `source/intent_replay/qa_room_switch.py`: pinned local Switch Core 0.31.0 authentication, original message lookup, exact command parsing, delivery receipts and deterministic agent result posts.
- `source/intent_replay/qa_room_http.py`: a loopback evidence index, original exporter artifact delivery, and an opt-in authenticated dispatch bridge. Its only mutation input is an original Switch message ID; it rejects browser-origin requests, oversized/extra fields and caller-supplied review claims. It has no browser approval action.
- `source/scripts/run_qa_room.py`: fixed `configure`, `probe`, `serve`, `show` and original-message `dispatch` operations.
- Three focused test modules and the setup, agent-instruction and human-walkthrough documents under `docs/QA_ROOM_*.md`.

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

Replays made **zero new model requests**. Four verification requests were sent during provider/transport integration; managed-agent inference occurred. Gateway activity exposes turns/tools, not exact provider model-call or token totals, so those totals remain unmeasured and are not claimed to be zero. Meta/Baseten credentials and balances were not accessed for these replays.

## Installed integration and remaining work

Installed official Switch Console **0.40.1**, native Core **0.31.0**, PostgreSQL **16.14**, and one managed agent `intent-replay-qa`, rooted in this worktree. The personal native server is `http://127.0.0.1:56741`. The current connection targets its automatically created **direct chat**, not a completed shared-room setup.

Docker Desktop **4.98.0** was installed from Docker's signed official installer with the existing Hyper-V backend, using the user's permission. Its current startup reports a `docker-users` membership check failure. The account is now a member, but the active Windows login token predates that membership; signing out and back in is the remaining prerequisite before enabling Switch's bundled Mattermost. Do not reset Switch or create replacement server/agent state.

The desktop-packaged Codex alpha initially lacked companion executables through the discovery bridge and then hung on a tool read. The bridge links were removed, leaving the original desktop installation intact. The official standalone `@openai/codex@0.166.0` was installed in the existing user npm prefix; the existing ChatGPT login and model configuration are retained. Shell dispatch remained denied/unreliable in the managed session. The fixed HTTP operation now works automatically through Node `http.request`, with no sandbox or approval-policy changes. Node `fetch` is intentionally avoided because it adds a browser-style `Sec-Fetch` header rejected by the bridge.

Follow [QA_ROOM_SETUP.md](docs/QA_ROOM_SETUP.md) for exact startup/configuration and [QA_ROOM_COMMANDS.md](docs/QA_ROOM_COMMANDS.md) for the human A → review A → B → stale A refused → review/complete B walkthrough. After the final room is connected, verify its own request/result/evidence path before claiming the milestone complete.

Official sources used: [Switch resources](https://www.wemakedevs.org/hackathons/switch/resources), [getting started](https://docs.switchagents.ai/switch-rooms/getting-started), [managed agents](https://docs.switchagents.ai/switch-rooms/getting-started/add-a-second-agent), the released Switch Console/Core sources, [Docker Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/), and [Codex CLI](https://learn.chatgpt.com/docs/codex/cli). Released source and observed server metadata take precedence over assumptions about an SDK.

## Reproduce the source package

After the implementation commit, run from this worktree:

```powershell
git archive --format=zip --prefix=intent-replay-flip/ --output=.local/intent-replay-flip-checkpoint.zip HEAD
Get-FileHash -Algorithm SHA256 -LiteralPath .local/intent-replay-flip-checkpoint.zip
```

This creates a reproducible source checkpoint from the committed tree. It excludes `.local/`, credentials, provider logins and runtime databases. It is not evidence that the outstanding room/human walkthrough has completed.
