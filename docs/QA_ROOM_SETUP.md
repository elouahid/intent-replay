# QA Room setup and resume

Updated on 2026-11-05 after the Windows restart and MCP transport setup. Docker, native Switch, the Mattermost room and linked human identity are available. The QA agent recovered after targeted stale-owner metadata repair. Two actual Mattermost Node invocations exited before dispatch, producing zero QA runs or delivery receipts. Agent revision 5 targets the project-local MCP transport; its eight focused tests pass. The third request could not discover the tool because actual managed startup disables project configuration pending trust of the common Git repository. User approval of that exact trust entry is pending. No real room replay or human review completion is claimed here.

## Installed components and current scope

| Component | Current configuration |
|---|---|
| Switch Console | 0.40.1; `C:\Users\asus\AppData\Local\Programs\Switch Console\Switch Console.exe` |
| Native Switch Core | 0.31.0; gateway `http://127.0.0.1:56741` |
| Existing native server | `b82ac60d-6645-491f-aafa-21de5f2e6ee9` |
| Existing QA agent | `intent-replay-qa`; ID `e9d69e59-a025-4e2d-abea-ce114dc448f8` |
| Agent transport | Revision 5; project-local `qa_room.dispatch_original_message` MCP tool |
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
5. Run `probe` and `serve` using the commands below. Restart `serve` after any deliberate connection-scope change because it holds the configured room in memory.
6. Confirm the managed session exposes `qa_room.dispatch_original_message` from the existing project configuration. Inspect original request/delivery state before retrying an uncertain dispatch. Preserve the failed Node events listed below; do not claim a result without its receipt or invent an event to recover it.
7. Verify returned exact-run evidence, both HTML reports and bundles open on this computer. Then perform [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md). Only the person sends approval/completion messages; these steps remain pending.

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
& $qaPython -B .\source\scripts\run_qa_room.py serve
```

Keep `serve` running. It serves evidence and authenticated `POST http://127.0.0.1:8054/api/qa/dispatch`, and generates `.local/qa-room/dispatch-token` if absent. The MCP wrapper reads that local bearer token internally and submits only `{"message_id":"<original ID>"}`. The agent does not read or display the token. The bridge rejects extra fields and browser `Origin`/`Sec-Fetch-*` headers, then applies the same original-Gateway-event and workflow guards as the CLI.

`probe` checks Gateway authentication/identity; it does not prove the full room interaction. The report URL is loopback and must be opened on this same computer. The exact supported room commands and A/B review walkthrough are in [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md); the agent MCP call and operator-only CLI fallback are in [QA_ROOM_AGENT_INSTRUCTIONS.md](QA_ROOM_AGENT_INSTRUCTIONS.md).

## Project-local MCP transport

The existing `.codex/config.toml` registers one stdio server, `qa_room`, with only `dispatch_original_message` enabled. Agent revision 5 instructs it to pass only the authoritative original message ID; sandbox and automatic-approval settings were not changed.

**Current blocker:** actual managed startup logs at 22:02:40 UTC and a no-inference MCP catalog probe show that this project layer is disabled until Codex explicitly trusts the common Git repository `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-public-submission-20261104`. An earlier configuration-only probe appeared enabled; actual startup/catalog evidence supersedes that result. The inherited drive-root trust does not satisfy this worktree check. The user has been asked to approve this specific project-trust entry; no trust change has been made. After approval and supported session refresh, verify `qa_room` and `dispatch_original_message` appear in `mcpServerStatus/list` before sending another room request.

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

Python shell execution in the managed agent was denied or unreliable, and both actual Node dispatch attempts exited before reaching the bridge. The default is now the single project-local MCP tool, launched by the managed runtime and forwarding to the existing HTTP bridge. The same local event verification and human-review rules apply; passing transport tests and loading configuration do not establish successful end-to-end room behavior.

This provider setup is independent of the retained Meta proposal captures. Replay adds zero model requests; any inference by the Console-managed Codex agent is separate, and its usage is reported only where observable.
