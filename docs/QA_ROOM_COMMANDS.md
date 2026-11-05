# Intent Replay — QA Room commands

One personal/local Switch room, agent `intent-replay-qa`, task `booking-withdrawal`, and case set `corrected-meta-withdrawal-control`. The integration targets Switch Console 0.40.1 / native Core 0.31.0, using the existing [Intent Replay QA Mattermost channel](http://localhost:56742/switch/channels/intent-replay-qa). Agent revision 5 uses the project-local MCP transport. Its eight focused tests pass; real room result return and the human A/B review walkthrough remain pending in the 2026-11-05 setup snapshot.

## Start the configured local workflow

After reboot, start Docker and use Console's native server **Start** button if needed. Select the existing server `b82ac60d-6645-491f-aafa-21de5f2e6ee9` at `http://127.0.0.1:56741` and the existing Mattermost room; see [QA_ROOM_SETUP.md](QA_ROOM_SETUP.md). With the preserved private connection references:

```powershell
Set-Location 'C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip'
$qaPython = 'C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.venv\Scripts\python.exe'
& $qaPython -B .\source\scripts\run_qa_room.py probe
& $qaPython -B .\source\scripts\run_qa_room.py serve
```

`probe` verifies the configured gateway connection and identity, not the complete real-room flow. Keep `serve` running: it serves evidence and the bounded dispatch bridge, creating the private `.local/qa-room/dispatch-token` if absent. Do not print that token. The default evidence address is `http://127.0.0.1:8054/qa/current`. The configured report origin is loopback: open it on the same computer as the demonstrated room. Before review, confirm the exact-run page, both HTML reports, and evidence bundles open successfully. A printed filesystem path alone is not verified reviewer access.

The Console-managed agent uses [QA_ROOM_AGENT_INSTRUCTIONS.md](QA_ROOM_AGENT_INSTRUCTIONS.md). Its sole `qa_room.dispatch_original_message` MCP tool accepts `{"original_message_id":"<exact original incoming ID>"}`. The wrapper reads the local token internally and forwards only that ID to authenticated `POST /api/qa/dispatch`; the server fetches the original human event and posts its own deterministic result. No shell command, message body, actor, or human-approval assertion is accepted. The agent must not duplicate the server's result or improvise a Node/shell fallback. The fixed CLI dispatch remains an operator diagnostic fallback.

The official SDK `mcp==1.28.1` is already installed in the native Switch environment; no install is needed. Actual managed startup currently disables the project layer pending explicit trust of the shared Git repository; the requested user approval and MCP catalog preflight must precede this live walkthrough. Optional dependency pin, exact launcher details and the observed blocker are recorded in [QA_ROOM_SETUP.md](QA_ROOM_SETUP.md), alongside the [official MCP configuration reference](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Human walkthrough

Send the following as **standalone room messages**, without quotation marks or code fences. Replace `RUN_A` and `RUN_B` with the actual full 32-character IDs returned by the agent. A person must send the approval/completion messages; the agent must never fabricate them.

1. Request run A:

   ```text
   @intent-replay-qa qa verify booking-withdrawal corrected-meta-withdrawal-control
   ```

2. Open A's returned evidence link. Inspect withdrawal and control, then approve A:

   ```text
   @intent-replay-qa qa approve booking-withdrawal RUN_A
   ```

3. Request B with the same `qa verify` command. Acceptance immediately makes B current and invalidates A's approval for this task, even while B is pending or if it fails.

4. Demonstrate stale completion refusal:

   ```text
   @intent-replay-qa qa complete booking-withdrawal RUN_A
   ```

   Expected: `stale_run`; no completion is granted for B. A's historical review remains attached only to A.

5. Wait for B's result, inspect **B's** report and bundles, then send these as two separate human interactions:

   ```text
   @intent-replay-qa qa approve booking-withdrawal RUN_B
   @intent-replay-qa qa complete booking-withdrawal RUN_B
   ```

   Expected scoped statement: “Human review completed for the checked local execution behavior, using run RUN_B.” Completion requires current, valid evidence, the required guarded/control checks, and approval of that exact run.

To reopen any retained result without executing it:

```text
@intent-replay-qa qa show booking-withdrawal RUN_A
```

The `@intent-replay-qa ` prefix is optional in the parser; using it addresses the Console agent explicitly. Duplicate platform deliveries do not create duplicate runs, approvals, or result posts. Delayed older verification events cannot supersede a newer platform request. An approval originally sent before the result, or completion sent before its required approval, is refused even if delivery is delayed. Interrupted executions are not automatically retried; a new human `qa verify` request creates a new current run.

## Read the result correctly

For the retained booking on 25 November 2026, Europe/London:

| Case | Faulty worker | Guarded worker |
|---|---|---|
| Withdrawal (`fresh-withdrawal`) | Commits 15:00; execution FAIL | Suppresses; retains 14:00; execution PASS |
| Control (`fresh-control`) | Commits 15:00; execution PASS | Commits 15:00; execution PASS |

All four frozen expectations should match. Regression PASS includes the deliberately faulty branch's expected FAIL. Factual accuracy remains INCONCLUSIVE/unassessed; overall task remains FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Human review status is a separate result.

Reports reuse the existing execution evidence interface and exporter. Saved model captures are recorded evidence, and replay adds zero model requests. Any Switch-agent inference is separate; no production-booking or production-readiness claim follows from completing this review.
