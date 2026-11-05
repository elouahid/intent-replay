# Intent Replay — QA Room commands

One personal/local Switch room, agent `intent-replay-qa`, task `booking-withdrawal`, and case set `corrected-meta-withdrawal-control`, on Switch Console 0.40.1 / native Core 0.31.0. Agent revision 6 automatically processed a real request in the [Intent Replay QA Mattermost channel](http://localhost:56742/switch/channels/intent-replay-qa) through the managed MCP tool and returned run A, `dd19c14126444bb79ef57882bfa48602`, on 2026-11-05. Its exact-run page and both HTML reports opened successfully; all six artifacts returned HTTP 200. A is ready/current with valid evidence and no approval or completion at this checkpoint. The actual human A/B review and stale-completion demonstration remain pending.

Request: `sw_b116d44a4e801a59d8f3cd30e64372dc` (sequence 11). Automatic result: `sw_22b4f2385c01448297121bd1d46314ec` (sequence 12). Local proof: `.local/qa-room/mattermost-run-a-verification.json`.

## Start the configured local workflow

After reboot, start Docker and use Console's native server **Start** button if needed. Select the existing server `b82ac60d-6645-491f-aafa-21de5f2e6ee9` at `http://127.0.0.1:56741` and the existing Mattermost room; see [QA_ROOM_SETUP.md](QA_ROOM_SETUP.md). With the preserved private connection references:

```powershell
Set-Location 'C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip'
$qaPython = 'C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.venv\Scripts\python.exe'
& $qaPython -B .\source\scripts\run_qa_room.py probe
```

`probe` verifies the configured gateway connection and identity, not the complete real-room flow. The evidence listener is already running at this checkpoint; reuse it at `http://127.0.0.1:8054/qa/current`. Only if the listener is absent after reboot, start one instance:

```powershell
& $qaPython -B .\source\scripts\run_qa_room.py serve
```

Do not start a duplicate while port 8054 is listening. Keep the existing instance running: it serves evidence and the bounded dispatch bridge, creating the private `.local/qa-room/dispatch-token` if absent. Do not print that token. Open the evidence on this same computer, confirm its room/task and exact run ID, and inspect both reports and bundles before reviewing.

The Console-managed agent uses [QA_ROOM_AGENT_INSTRUCTIONS.md](QA_ROOM_AGENT_INSTRUCTIONS.md). Its sole `qa_room.dispatch_original_message` MCP tool accepts `{"original_message_id":"<exact original incoming ID>"}`. The wrapper reads the local token internally and forwards only that ID to authenticated `POST /api/qa/dispatch`; the server fetches the original human event and posts its own deterministic result. No shell command, message body, actor, or human-approval assertion is accepted. The agent must not duplicate the server's result or improvise a Node/shell fallback. The fixed CLI dispatch remains an operator diagnostic fallback.

The official SDK `mcp==1.28.1` is already installed in the native Switch environment; no install is needed. The user authorized the exact common-repository trust entry for `C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\intent-replay-public-submission-20261104`; it was appended to the user Codex configuration after a private backup, with no other settings changed. Following the managed-agent refresh, the live SDK catalog returned exactly `dispatch_original_message`. The earlier configuration-only probe had not established runtime availability. On resume, check the live tool catalog before sending another request. Optional dependency pin, exact launcher and trust-resolution details are recorded in [QA_ROOM_SETUP.md](QA_ROOM_SETUP.md), alongside the [official MCP configuration reference](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Human walkthrough

Continue from the observed A checkpoint below. Send commands as **standalone room messages**, without quotation marks or code fences. `RUN_B` remains a placeholder until the new verification returns its full 32-character ID. A person must send the approval/completion messages; the agent must never fabricate them.

1. Run A already exists. Open [A's exact evidence](http://127.0.0.1:8054/qa/runs/dd19c14126444bb79ef57882bfa48602), personally inspect withdrawal and control, then send the next human command:

   ```text
   @intent-replay-qa qa approve booking-withdrawal dd19c14126444bb79ef57882bfa48602
   ```

2. After A's actual approval is recorded, request B:

   ```text
   @intent-replay-qa qa verify booking-withdrawal corrected-meta-withdrawal-control
   ```

   Acceptance immediately makes B current and invalidates A's approval for this task, even while B is pending or if it fails.

3. Demonstrate stale completion refusal:

   ```text
   @intent-replay-qa qa complete booking-withdrawal dd19c14126444bb79ef57882bfa48602
   ```

   Expected: `stale_run`; no completion is granted for B. A's historical review remains attached only to A.

4. Wait for B's result, inspect **B's** report and bundles, then send these as two separate human interactions:

   ```text
   @intent-replay-qa qa approve booking-withdrawal RUN_B
   ```

   Wait for approval confirmation before sending completion; its original send time must follow the recorded approval.

   ```text
   @intent-replay-qa qa complete booking-withdrawal RUN_B
   ```

   Expected scoped statement: “Human review completed for the checked local execution behavior, using run RUN_B.” Completion requires current, valid evidence, the required guarded/control checks, and approval of that exact run.

To reopen any retained result without executing it:

```text
@intent-replay-qa qa show booking-withdrawal dd19c14126444bb79ef57882bfa48602
```

The `@intent-replay-qa ` prefix is optional in the parser; using it addresses the Console agent explicitly. Duplicate platform deliveries do not create duplicate runs, approvals, or result posts. Delayed older verification events cannot supersede a newer platform request. An approval originally sent before the result, or completion sent before its required approval, is refused even if delivery is delayed. Interrupted executions are not automatically retried; a new human `qa verify` request creates a new current run.

## Read the result correctly

For the retained booking on 25 November 2026, Europe/London:

| Case | Faulty worker | Guarded worker |
|---|---|---|
| Withdrawal (`fresh-withdrawal`) | Commits 15:00; execution FAIL | Suppresses; retains 14:00; execution PASS |
| Control (`fresh-control`) | Commits 15:00; execution PASS | Commits 15:00; execution PASS |

Run A matched all four frozen expectations. Regression PASS includes the deliberately faulty branch's expected FAIL. Factual accuracy remains INCONCLUSIVE/unassessed; overall task remains FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Human review status is a separate result.

Reports reuse the existing execution evidence interface and exporter. Saved model captures are recorded evidence, and replay adds zero model requests. Any Switch-agent inference is separate; no production-booking or production-readiness claim follows from completing this review.
