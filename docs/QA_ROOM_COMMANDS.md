# Intent Replay — QA Room commands

One personal/local Switch room, agent `intent-replay-qa`, task `booking-withdrawal`, and case set `corrected-meta-withdrawal-control`, on Switch Console 0.40.1 / native Core 0.31.0. Agent revision 6 automatically processed A and B in the [Intent Replay QA Mattermost channel](http://localhost:56742/switch/channels/intent-replay-qa). At the 2026-11-06 UTC checkpoint, B `a9ce6b8d4b9f4c1eb6d8cab94d24cd67` is current/ready/evidence-valid; A is historical. Both are unreviewed. Assistant technical review did not create any human approval or completion.

A request/result: sequences 11/12. B request `sw_2038d700ac6120ad2ddd84c04b7139ca` (15); result `sw_1a434e896a694e1db3d5ae3399453cdd` (16). The 56-check read-only A/B audit is `.local/qa-room-assistant-review/mattermost-a-b-evidence-audit.json`. The failed sequence-13 request produced no run.

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

## Review the current B

Send commands as **standalone room messages**, without quotation marks or code fences. A person must perform approval/completion; the assistant must not send them under the person's account. Refresh [current evidence](http://127.0.0.1:8054/qa/current) first: if another run has superseded B, inspect and use that exact new ID.

1. Open [B's exact evidence](http://127.0.0.1:8054/qa/runs/a9ce6b8d4b9f4c1eb6d8cab94d24cd67). In both HTML reports, inspect final booking readback, accepted revisions, authorization/commit journal, and separate factual/overall verdicts. The guarded withdrawal retains 14:00; the control commits 15:00. If satisfied, personally send:

   ```text
   @intent-replay-qa qa approve booking-withdrawal a9ce6b8d4b9f4c1eb6d8cab94d24cd67
   ```

2. Wait for the room's approval confirmation. To complete B's scoped human review, personally send a separate message:

   ```text
   @intent-replay-qa qa complete booking-withdrawal a9ce6b8d4b9f4c1eb6d8cab94d24cd67
   ```

   Its original send time must follow the recorded approval. Expected statement: “Human review completed for the checked local execution behavior, using run a9ce6b8d4b9f4c1eb6d8cab94d24cd67.” This does not resolve factual uncertainty.

## Optional actual-human stale-approval demonstration

The original A → human approval A → B sequence was not performed. A cannot be approved retroactively while B is current. Three isolated simulated tests passed this guard; the real-room demonstration remains incomplete. Continue honestly with **B as the reviewed old run and C as the new run**:

1. Personally review and approve B as above. Completion of B before the rerun is optional.
2. Request a new run through the room:

   ```text
   @intent-replay-qa qa verify booking-withdrawal corrected-meta-withdrawal-control
   ```

   Record its returned full ID as `RUN_C`. Acceptance makes C current before execution; B's approval cannot authorize C, even if C remains pending or fails.
3. Personally attempt completion using B's old ID:

   ```text
   @intent-replay-qa qa complete booking-withdrawal a9ce6b8d4b9f4c1eb6d8cab94d24cd67
   ```

   Expected: `stale_run`; no completion is granted for C. B's review remains historical. Verify original room events and C's JSON record rather than relying on narration.

4. Inspect **C's** new evidence, then personally send approval and, after its confirmation, completion as separate messages:

   ```text
   @intent-replay-qa qa approve booking-withdrawal RUN_C
   ```

   ```text
   @intent-replay-qa qa complete booking-withdrawal RUN_C
   ```

   Completion requires current, valid evidence, the required guarded/control checks, and approval of that exact run. Do not report this walkthrough as completed until those actual events and records exist.

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

A and B each matched all four frozen expectations. Regression PASS includes the deliberately faulty branch's expected FAIL. Factual accuracy remains INCONCLUSIVE/unassessed; overall task remains FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Human review status is a separate result.

Reports reuse the existing execution evidence interface and exporter. Saved model captures are recorded evidence, and replay adds zero model requests. Any Switch-agent inference is separate; no production-booking or production-readiness claim follows from completing this review.
