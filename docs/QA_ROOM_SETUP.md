# QA Room setup and resume

## Completed B/C review checkpoint — 2026-11-07 UTC

The person's exact B approval was recorded at sequence 18 and confirmed at 19. An authorized assistant verification produced C `5aa6bb5509734cb388537a63007d3087` at 20/21. The authorized assistant negative test of completing old B at 22 was refused with `stale_run` at 23. The person then posted exact C approval `sw_64e554b42f2ff28f01d8822989a8d8c6` (24), confirmed at 25, followed by exact completion `sw_cc40b260975f872a9d47d332973d82f2` (26), confirmed at 27. C is current, evidence-valid and human-review completed; B remains historically approved and incomplete. No further review command is needed.

The earlier stale-approval audit and the separate final completion audit each passed 76 checks. Final proof: `.local/qa-room-assistant-review/c-human-completion-audit.json`; SHA-256 `f49dd7ecd13ae256ec0ae8d8f7b21bbd4c459f1ac74cc844bd401451863407e6`. The full B/C walkthrough is complete; the original human A/B sequence was not performed. Use [the command guide](QA_ROOM_COMMANDS.md) to reopen C read-only or intentionally start a future manual run. The following recovery details preserve earlier checkpoints.

## 2026-11-06 recovery history

The stopped services were restored. Docker initially failed to allocate its configured 2048 MB Hyper-V memory (`0x800705AA`); after the person freed memory, Engine 29.9.2 and the existing Mattermost container became healthy. A and all retained evidence were preserved.

The next real verification request reached the room (sequence 13) but the managed Codex session returned expired-token refresh **401** before dispatch. That failed attempt created no B. Console's cached “Signed in” status did not establish usable runtime authentication.

Recovery succeeded with installed Codex 0.166.0 `login` and child-process-only `CODEX_HOME` set to the existing Mattermost SDK provider home. The person completed the browser sign-in, and the private process log confirmed successful login. Global authentication/configuration was not changed, and credentials were not copied. Private login-process metadata is in `.local/qa-room/scoped-login-session.json`; never print its referenced OAuth logs or authentication file. [Official authentication documentation](https://learn.chatgpt.com/docs/auth) documents browser login and scoped credential storage.

After login, supported `agent.restart` operation `4cf44b5d-c553-4544-ae57-4e9c7defb9cc` succeeded at 23:26:49 UTC, preserving the existing agent and conversations. Fresh original request `sw_2038d700ac6120ad2ddd84c04b7139ca` (sequence 15) then automatically invoked `qa_room.dispatch_original_message` and produced **B `a9ce6b8d4b9f4c1eb6d8cab94d24cd67`**, result `sw_1a434e896a694e1db3d5ae3399453cdd` (sequence 16). B was then current/ready/unreviewed with valid evidence; A was historical/unreviewed. All 56 independent audit checks passed. Both HTML reports opened and all six artifacts returned HTTP 200.

If the same authentication error recurs, diagnose the exact managed provider home and let the person complete its browser login before supported restart. Do not copy credentials, delete sessions, create a replacement agent, switch providers, or describe manual dispatch as managed delivery. A successful new request/result is the runtime authentication check; a cached provider badge is insufficient.

The user authorized an assistant-reviewed continuation; actual human approval/completion still must not be fabricated. The following dated setup checkpoint describes the established run-A configuration.

At the 2026-11-05 checkpoint, agent revision 6 dispatched the original room request through its managed MCP tool and returned run A, `dd19c14126444bb79ef57882bfa48602`, at 22:30:14 UTC. A was ready with valid evidence and matching frozen expectations. Human review was unreviewed; the approval and stale-completion demonstration were pending at that capture. The later B/C completion is recorded above.

## Installed components and current scope

| Component | Current configuration |
|---|---|
| Switch Console | 0.40.1; `C:\Users\asus\AppData\Local\Programs\Switch Console\Switch Console.exe` |
| Native Switch Core | 0.31.0; gateway `http://127.0.0.1:56741` |
| Existing native server | `b82ac60d-6645-491f-aafa-21de5f2e6ee9` |
| Existing QA agent | `intent-replay-qa`; ID `e9d69e59-a025-4e2d-abea-ce114dc448f8` |
| Agent transport | Revision 6; project-local `qa_room.dispatch_original_message` MCP tool |
| Agent workspace | `C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip` — verified |
| Verification task | `booking-withdrawal` |
| Supported case set | `corrected-meta-withdrawal-control` |
| Current connection target | Mattermost-backed room `496e3d1b-8c14-4a6c-9bc5-1e164c0da362` |
| Mattermost channel | [Intent Replay QA](http://localhost:56742/switch/channels/intent-replay-qa) |
| Mattermost bridge | `7b6daa01-6bf8-43e0-b4f2-71d30a21e9e3` |
| Verified human client | `f97780ca-7e77-4573-902d-e66eb59e9fe7` |
| Evidence listener | `http://127.0.0.1:8054` on this computer |
| Docker Desktop | 4.98.0 with Hyper-V backend; engine healthy after the restart |

Historical Console direct chat `95574125-421c-4810-bdc2-d47822117d2b` and its runs remain preserved under their original room scope. They do not count as the Mattermost demonstration. A successful gateway probe, running agent, or local test is not a substitute for a verified request and result in the current room.

## Historical run A checkpoint (November 5)

| Evidence | Verified value |
|---|---|
| Original Mattermost request | `sw_b116d44a4e801a59d8f3cd30e64372dc`, room sequence 11 |
| Automatic agent result | `sw_22b4f2385c01448297121bd1d46314ec`, room sequence 12 |
| Exact run | `dd19c14126444bb79ef57882bfa48602` |
| Workflow state at capture | Ready, current, evidence valid; approval and completion both absent |
| Checks | Regression PASS; required guarded/control checks PASS; factual accuracy INCONCLUSIVE |
| Local evidence record | `.local/qa-room/mattermost-run-a-verification.json` |

The [exact run A page](http://127.0.0.1:8054/qa/runs/dd19c14126444bb79ef57882bfa48602) and both HTML reports were opened successfully in the browser. HTTP checks returned 200 for that page and all six artifacts, including both evidence bundles. The captured room events, managed-agent activity and workflow snapshot establish automatic request-to-result delivery; they do not constitute human approval. Replay used zero new model requests.

This table records A's state at its original capture. A is historical and cannot be approved for the current task. The completed B/C walkthrough is recorded above; [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md) reopens C without rerunning it. The original human A/B sequence was not performed.

## Start after reboot

The old-session `docker-users` token blocker is resolved. No further reinstall or sign-out is required on the evidence currently available.

1. Open Docker Desktop if needed and confirm `docker info` reaches its working server.
2. Resume this **Codex chat** and launch/focus the installed Console from the same environment:

   ```powershell
   Start-Process -FilePath 'C:\Users\asus\AppData\Local\Programs\Switch Console\Switch Console.exe' -ArgumentList 'switchdash://focus'
   ```

   The URI requests focus; verify the visible server and existing agent IDs match the table. The preserved profile resolves under Codex MSIX `LocalCache\Roaming\switchdash`. Do not use a generic `--user-data-dir` workaround: the app overrides that setting. Do not initialize a replacement server/profile if the expected records are absent.
3. In Console, use the native server **Start** button if the native service is stopped; focusing the UI alone does not start it. Wait for it to become healthy, then select the existing native server `b82ac60d-6645-491f-aafa-21de5f2e6ee9` at `http://127.0.0.1:56741`. Route the existing agent/room through that server. On **Server → Mattermost**, use **Run Mattermost** only if the existing messaging service is stopped. Preserve native server data and the existing agent/session.
4. Open the existing [Intent Replay QA channel](http://localhost:56742/switch/channels/intent-replay-qa). Keep the single room and agent identified above; do not recreate them.
5. Run `probe` using the commands below and reuse the existing evidence listener on port 8054. Start `serve` only when that listener is absent; do not launch a duplicate. Restart its owning process deliberately after a connection-scope change because it holds the configured room in memory.
6. Confirm the managed session exposes `qa_room.dispatch_original_message` from the existing project configuration. Inspect original request/delivery state before retrying an uncertain dispatch. Preserve the failed Node events listed below; do not claim a result without its receipt or invent an event to recover it.
7. Open the exact current run and its evidence on this computer. C is the completed checkpoint; no fresh review command is needed. [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md) distinguishes read-only reopening from an intentional future rerun, which would require new review.

Current log contents and listener ownership are better startup evidence than an old file modification timestamp: during recovery, native log tails showed fresh Gateway HTTP 200 entries while their reported modification times still reflected shutdown.

## Preserved connection and room membership

The default file is `.local/qa-room/connection.json`; workflow/delivery state is under `.local/qa-room/state`. Configuration contains identity and credential-file **references**, not copied credential values. `run_qa_room.py configure` intentionally refuses to overwrite an existing file.

The connection is already bound to the Mattermost room in the table. Back up the file before any future deliberate change, and retain prior direct-chat configuration/history. Keep the current gateway, agent, task, report origin, credential references and verified reviewer pin. Room/task scope separates the new runs from historical direct-chat evidence.

Gateway administrator authentication alone did not grant read access to this Mattermost room. The administrator was added through the supported membership operation:

```text
POST /gateway/chats/496e3d1b-8c14-4a6c-9bc5-1e164c0da362/members
{"userId":"df84bac8-667e-4cec-aef3-317c016ccdf5"}
```

This membership has been confirmed; it is not a command to repeat on every startup. It lets the adapter's authenticated Gateway client retrieve original room messages. It does not grant human approval or substitute for the pinned Mattermost sender identity.

The current private references, to be read in place without printing their contents, are:

- Native login environment: `C:\Users\asus\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Roaming\switchdash\local-switch-server\native\run\switch-core.env`
- Agent credentials: `C:\Users\asus\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Roaming\switchdash\agent-controller\servers\b82ac60d-6645-491f-aafa-21de5f2e6ee9\agents\e9d69e59-a025-4e2d-abea-ce114dc448f8\credentials.json`

## Verified human identity

The current demonstrated interaction path is the Mattermost web UI. The original room event verified source `mattermost`, a human sender, and linked `sender.clientId = f97780ca-7e77-4573-902d-e66eb59e9fe7`. The configuration deliberately has `reviewer_client_ids` containing that one value and `reviewer_user_ids=[]`; Mattermost events can have a null Gateway `sender.userId`.

Do not remove this pin to accommodate a failing message. Check the authoritative original event and room membership. A display name, agent assertion, quoted command, or existing admin login is not human approval. Any future switch to Console-authored commands requires explicit verification of that source's identity and a backed-up configuration change.

With this client-only pin, `probe`'s Console-user identity comparison can be false even when Gateway authentication works. The actual command actor is checked against the pinned Mattermost client ID, independently of the adapter's administrator session.

The dispatcher reads original event identity, sequence, command, and send time from the authenticated Gateway. The core checks source time and current run/review atomically; an agent cannot supply substitute consent, actor, or timestamp through the bridge or CLI.

## Targeted stale-owner recovery on 2026-11-05

After reboot, old runtime records still named PID 15348, which Windows had reassigned to `svchost`. Switch's ownership check called `process.kill(pid, 0)` and propagated `EPERM`; retries could not restore the agent. No unrelated process was terminated.

The following exact preboot metadata was hash-checked and preserved with the suffix `.preboot-20261105-preserved` before supported agent restart:

- Watcher root: `C:\Users\asus\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Roaming\switchdash\agent-controller\servers\b82ac60d-6645-491f-aafa-21de5f2e6ee9\watchers\e9d69e59-a025-4e2d-abea-ce114dc448f8`; records `shared-owner.lock` and `health.json`.
- Existing SDK session root: `C:\Users\asus\.local\state\switch\sdk-sessions\0a9ca3facc5180822c6500dda36dc5489b1fef8cd5ff65026f0c41eb00a9b30b`; records `supervisor\owner.json` and `shared-owner.lock`. The supervisor record named reused PID 15348. The worker lock named absent PID 36212; preserving that stale worker lock was optional cleanup.

The SDK session's `supervisor\owner.json` was the remaining directly evidenced blocker after watcher-record quarantine. Restarting Console or the agent without addressing that specific on-disk record retained the same error. All configuration, events, queues, provider-home content, session history and QA run evidence were retained; the existing agent recovered.

This is an incident record, **not an automatic lock-deletion procedure**. If it recurs, inspect the exact stored PID, current process identity, file timestamp and owning session first. Preserve only conclusively stale ownership metadata before a supported restart. Do not clear session directories, remove locks by wildcard, kill a reused Windows process, or recreate the agent to bypass ownership checks.

## Start evidence and check the configured gateway

With native Switch running and the intended room configured:

```powershell
Set-Location 'C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip'
$qaPython = 'C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.venv\Scripts\python.exe'
& $qaPython -B .\source\scripts\run_qa_room.py probe
```

The evidence listener is already running at this checkpoint. Open [current C](http://127.0.0.1:8054/qa/runs/5aa6bb5509734cb388537a63007d3087), or `http://127.0.0.1:8054/qa/current`, and reuse that listener. If it is absent after reboot, start one instance:

```powershell
& $qaPython -B .\source\scripts\run_qa_room.py serve
```

Do not run a second `serve` while port 8054 is already listening. Confirm the existing page belongs to the configured room/task before continuing. Keep the existing instance running: it serves evidence and authenticated `POST http://127.0.0.1:8054/api/qa/dispatch`, and generates `.local/qa-room/dispatch-token` if absent. The MCP wrapper reads that local bearer token internally and submits only `{"message_id":"<original ID>"}`. The agent does not read or display the token. The bridge rejects extra fields and browser `Origin`/`Sec-Fetch-*` headers, then applies the same original-Gateway-event and workflow guards as the CLI.

`probe` checks Gateway authentication/identity; it does not prove the full room interaction. The report URL is loopback and must be opened on this same computer. The exact supported room commands and A/B review walkthrough are in [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md); the agent MCP call and operator-only CLI fallback are in [QA_ROOM_AGENT_INSTRUCTIONS.md](QA_ROOM_AGENT_INSTRUCTIONS.md).

## Project-local MCP transport

The existing `.codex/config.toml` registers one stdio server, `qa_room`, with only `dispatch_original_message` enabled. Agent revision 6 instructs it to pass only the authoritative original message ID; sandbox and automatic-approval settings were not changed.

**Resolved project-trust blocker:** the user explicitly authorized the `trust_level = "trusted"` entry for `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-public-submission-20261104` in the user Codex configuration, `C:\Users\asus\.codex\config.toml`. This is the common Git repository verified by `git rev-parse --git-common-dir`, not a drive-wide trust change. The prior private configuration was backed up before appending this exact entry; no other user-configuration settings changed. Submitted repository files, credentials, sandbox and automatic-approval policy were unchanged.

Before that approval, actual managed startup at 22:02:40 UTC disabled the project layer despite an earlier configuration-only probe appearing enabled. The inherited drive-root trust did not satisfy the worktree check. Preserve that distinction: `config/read` alone was insufficient evidence of tool availability.

After applying the approved entry and refreshing the existing managed agent, the actual managed MCP handshake succeeded at **22:26:05 UTC on 2026-11-05**. The official SDK tool listing returned exactly `dispatch_original_message`. On future resume, confirm `qa_room` and that sole tool in the live catalog before sending a new room request. This preflight established transport availability; A established automatic room delivery, and the later B/C checkpoint established the complete human-review workflow.

The configured executable uses the resolved physical path to the already-installed native Switch environment:

```text
C:\Users\asus\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Roaming\switchdash\local-switch-server\native\switch-core\0.31.0\venv\Scripts\python.exe
```

Its arguments are `-B` and `C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip\source\scripts\run_qa_room_mcp.py`; its working directory is the Flip worktree. The managed runtime starts this stdio process. Do not start a second interactive copy to submit room events.

The wrapper uses the official Python MCP SDK already installed there, version `1.28.1`, and fixes its HTTP target to loopback port 8054. Input accepts only `original_message_id`; extra properties are rejected before token access or HTTP. Redirects and environment proxies are disabled, HTTP timeout is 60 seconds, and returned receipts are bounded and sanitized. The project config allows 30 seconds for startup and 90 seconds for the tool call. The wrapper makes no workflow decisions or human consent assertions.

Eight focused tests passed in the native environment, including the official SDK stdio initialization, tool listing, strict input rejection and mock transport failures. The baseline interpreter passed six transport tests and skipped the two optional SDK tests. No dependencies were installed. `source/requirements-qa-mcp.txt` records `mcp==1.28.1` for an optional separately isolated environment; leave the existing replay environment and dependencies unchanged.

OpenAI documents project-scoped `.codex/config.toml`, stdio `command`/`args`/`cwd`, and `enabled_tools` in its [official MCP configuration guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli). Those transport settings do not replace this project's original-event and review guards.

The two failed Node attempts are retained as diagnostic evidence:

| Original Mattermost event | Room sequence | Observed result |
|---|---|---|
| `sw_bb01ce3f665773f8056b904782f5ce97` | 6 | Trusted Node process exited/reset; zero QA runs or receipts |
| `sw_9a3d735148603160b10808e8c9f4be5a` | 9 | Trusted Node process exited/reset; zero QA runs or receipts |

Third request `sw_2f02f3788ff4138862893e26454e6900` stopped because the MCP tool was unavailable under the disabled project layer; it also created no run or receipt.

Use the MCP tool for subsequent managed-agent dispatch. Do not fall back to Node, browser JavaScript or shell execution from room text. An operator can use the fixed CLI solely for diagnosis; a manually dispatched event does not prove managed-agent delivery.

## Existing agent provider

The Console-managed agent now uses official npm **`@openai/codex@0.166.0`** with the existing ChatGPT login/model. Its watcher `binaryPath` is `C:\Users\asus\AppData\Roaming\npm\codex.CMD`.

The four temporary alpha executable hardlinks (`codex.exe`, `codex-code-mode-host.exe`, `codex-command-runner.exe`, `codex-windows-sandbox-setup.exe`) were removed from the npm PATH directory after stopping the managed agent. The original desktop installation under `C:\Users\asus\AppData\Local\OpenAI\Codex\bin\a159911ff70742e9` remains unchanged. Do not restore those temporary hardlinks or copy credentials to fix PATH.

Python shell execution in the managed agent was denied or unreliable, and both actual Node dispatch attempts exited before reaching the bridge. The default is now the single project-local MCP tool, launched by the managed runtime and forwarding to the existing HTTP bridge. A verified automatic request-to-result delivery; the later B/C walkthrough verified actual human approvals, stale-B refusal and C completion while retaining the original-event and review guards.

This provider setup is independent of the retained Meta proposal captures. Replay adds zero model requests; any inference by the Console-managed Codex agent is separate, and its usage is reported only where observable.
