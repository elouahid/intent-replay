# QA Room setup and resume

Recorded setup state on 2026-11-05. These facts describe the installed components and configuration; they do **not** establish a completed real-room replay or human-review demonstration.

## Installed components and current scope

| Component | Current configuration |
|---|---|
| Switch Console | 0.40.1; `C:\Users\asus\AppData\Local\Programs\Switch Console\Switch Console.exe` |
| Native Switch Core | 0.31.0; gateway `http://127.0.0.1:56741` |
| Existing QA agent | `intent-replay-qa`; ID `e9d69e59-a025-4e2d-abea-ce114dc448f8` |
| Agent workspace | `C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip` — verified |
| Verification task | `booking-withdrawal` |
| Supported case set | `corrected-meta-withdrawal-control` |
| Current connection target | Temporary Console **DIRECT chat** `95574125-421c-4810-bdc2-d47822117d2b` |
| Evidence listener | `http://127.0.0.1:8054` on this computer |
| Docker Desktop | 4.98.0 installed with Hyper-V backend; engine blocked by the old Windows login token |

The temporary direct chat is **not the final messaging-app room**. Console manages the agent, but its actual rooms require a supported messaging app. Keep direct-chat evidence identified as direct-chat evidence. A successful gateway probe, running agent, or local test is not a substitute for a verified request and result in the final room.

## Resume after Windows sign-out

1. Save open work, then **sign out of Windows and sign back in as `asus`**. The account is already a member of `docker-users`; the existing login session predates that membership. Starting another terminal in that old session does not refresh its access token. This is the remaining user action before engine readiness can be rechecked.
2. Open Docker Desktop and wait for its engine to start. Confirm `docker info` reaches a working server. Do not reinstall it merely because the pre-sign-out process was blocked.
3. Resume this **Codex chat** and launch the existing Switch Console from the same environment. The current profile resolves under the Codex MSIX `LocalCache\Roaming\switchdash` paths listed below. Verify the existing agent ID and native gateway server match the table before proceeding; preserve their records, credentials, and data. Do not use a generic `--user-data-dir` workaround: this app overrides that setting. In **Admin → Status**, use **Run Mattermost** once Docker is ready.
4. Complete the personal/local messaging setup, then create **one** room named **Intent Replay QA** with the **existing** `intent-replay-qa` agent. Do not replace the agent or create an employer-workspace integration.
5. Obtain the new room's actual ID from Console/the authenticated Gateway. Update the existing connection file as described below; retain the direct-chat history. Restart the evidence listener so its server-held scope uses the new room.
6. Verify the agent can receive the real room request and that its returned exact-run evidence page, both reports, and bundles open on this computer. Then perform the manual walkthrough in [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md). Only the person sends approval/completion messages.

If Docker or Mattermost remains unavailable after sign-in, record that actual result. Do not relabel the temporary direct chat as the completed Mattermost room.

## Preserve and update the connection reference

The default file is `.local/qa-room/connection.json`; workflow/delivery state is under `.local/qa-room/state`. Configuration contains identity and credential-file **references**, not copied credential values. `run_qa_room.py configure` intentionally refuses to overwrite an existing file.

After verifying the new room ID, back up the existing configuration and explicitly update only the room reference. From the Flip workspace:

```powershell
$qaConfigPath = Join-Path (Get-Location) '.local\qa-room\connection.json'
$qaBackupPath = Join-Path (Split-Path $qaConfigPath) ('connection-before-room-change-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff') + '.json')
Copy-Item -LiteralPath $qaConfigPath -Destination $qaBackupPath -ErrorAction Stop
$qaConnection = Get-Content -Raw -LiteralPath $qaConfigPath | ConvertFrom-Json
$qaConnection.room_id = '<verified new Intent Replay QA room ID>'
$qaConnection | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $qaConfigPath -Encoding utf8
```

Replace the placeholder with the verified ID **before** running the update. Keep the existing gateway, agent ID/name, task, report URL, credential references, and reviewer pins unless an independently verified setup change requires otherwise. Do not delete or rewrite stored runs. Room/task scope separates new room runs from retained direct-chat evidence.

The current private references, to be read in place without printing their contents, are:

- Native login environment: `C:\Users\asus\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Roaming\switchdash\local-switch-server\native\run\switch-core.env`
- Agent credentials: `C:\Users\asus\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Roaming\switchdash\agent-controller\servers\b82ac60d-6645-491f-aafa-21de5f2e6ee9\agents\e9d69e59-a025-4e2d-abea-ce114dc448f8\credentials.json`

## Human identity in the final room

The simplest path is to send commands through the **Console UI inside the actual Mattermost-backed room**. Those authenticated Gateway events use source `console` and the Console administrator's `sender.userId`; retain the existing `reviewer_user_ids` pin. A new Console direct chat is not equivalent to that room.

If the person instead uses the **Mattermost web UI**, its Gateway events may have `sender.userId = null`. Raw Mattermost messages are deliberately rejected while the configuration requires the Console user ID. Before changing that policy:

1. Have the person send a non-approval setup message from their actual Mattermost account in the final room.
2. Retrieve the authoritative original Gateway event and verify its room ID, source `mattermost`, human sender kind, and exact `sender.clientId`. A display name or text claiming an identity is insufficient.
3. Back up the connection file again. Pin that verified value in `reviewer_client_ids`; clear `reviewer_user_ids` **only for this explicitly verified Mattermost interaction path**. Do not clear both reviewer identity lists.
4. Recheck command acceptance from the intended human and rejection of agent-generated or quoted approval. Do not fabricate a review as part of setup.

The dispatcher reads original event identity, sequence, command, and send time from the authenticated Gateway. The core checks source time and current run/review atomically; an agent cannot supply substitute consent, actor, or timestamp through the bridge or CLI.

## Start evidence and check the configured gateway

With native Switch running and the intended room configured:

```powershell
Set-Location 'C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip'
$qaPython = 'C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.venv\Scripts\python.exe'
& $qaPython -B .\source\scripts\run_qa_room.py probe
& $qaPython -B .\source\scripts\run_qa_room.py serve
```

Keep `serve` running. It serves evidence and authenticated `POST http://127.0.0.1:8054/api/qa/dispatch`, and generates `.local/qa-room/dispatch-token` if absent. The agent reads this local bearer token without displaying it and submits JSON containing only `{"message_id":"<original ID>"}` through its Node tool. The bridge rejects extra fields and browser `Origin`/`Sec-Fetch-*` headers, then applies the same original-Gateway-event and workflow guards as the CLI. Use the documented `node:http.request` example: built-in Node `fetch` adds a rejected `Sec-Fetch-Mode` header.

`probe` checks Gateway authentication/identity; it does not prove the full room interaction. The report URL is loopback and must be opened on this same computer. The exact supported room commands and A/B review walkthrough are in [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md); the agent HTTP example and operator-only CLI fallback are in [QA_ROOM_AGENT_INSTRUCTIONS.md](QA_ROOM_AGENT_INSTRUCTIONS.md).

## Existing agent provider

The Console-managed agent now uses official npm **`@openai/codex@0.166.0`** with the existing ChatGPT login/model. Its watcher `binaryPath` is `C:\Users\asus\AppData\Roaming\npm\codex.CMD`.

The four temporary alpha executable hardlinks (`codex.exe`, `codex-code-mode-host.exe`, `codex-command-runner.exe`, `codex-windows-sandbox-setup.exe`) were removed from the npm PATH directory after stopping the managed agent. The original desktop installation under `C:\Users\asus\AppData\Local\OpenAI\Codex\bin\a159911ff70742e9` remains unchanged. Do not restore those temporary hardlinks or copy credentials to fix PATH.

Stable-provider tools work, but Python shell execution in the managed agent was denied or unreliable. Its default operation is therefore the fixed Node HTTP bridge, not a Python subprocess. The same local event verification and human-review rules apply; bridge installation alone does not establish successful end-to-end room behavior.

This provider setup is independent of the retained Meta proposal captures. Replay adds zero model requests; any inference by the Console-managed Codex agent is separate, and its usage is reported only where observable.
