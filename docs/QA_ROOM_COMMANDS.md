# Intent Replay — QA Room commands

One personal/local Switch room, agent `intent-replay-qa`, task `booking-withdrawal`, and case set `corrected-meta-withdrawal-control`, on Switch Console 0.40.1 / native Core 0.31.0. In the [Intent Replay QA Mattermost channel](http://localhost:56742/switch/channels/intent-replay-qa), current C `5aa6bb5509734cb388537a63007d3087` is ready/evidence-valid/unreviewed. B retains the person's actual approval historically; its old completion command was refused after C became current.

A request/result: sequences 11/12. B request/result: 15/16. Actual human B approval at 18 was confirmed at 19. Authorized assistant C verification at 20 produced result at 21; the authorized assistant negative B-completion probe at 22 was refused with `stale_run` at 23. No completion was granted. The read-only B/C audit passed 76 checks; proof is `.local/qa-room-assistant-review/mattermost-b-c-stale-approval-audit.json`. The earlier A/B audit and failed sequence-13 request are preserved separately.

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

## Review the current C

Send commands as **standalone room messages**, without quotation marks or code fences. A person must perform fresh approval/completion. Refresh [current evidence](http://127.0.0.1:8054/qa/current) first: if another run has superseded C, inspect and use that exact new ID.

1. Open [C's exact evidence](http://127.0.0.1:8054/qa/runs/5aa6bb5509734cb388537a63007d3087). In both HTML reports, inspect final booking readback, accepted revisions, authorization/commit journal, and separate factual/overall verdicts. The guarded withdrawal retains 14:00; the control commits 15:00. If satisfied, personally send:

   ```text
   @intent-replay-qa qa approve booking-withdrawal 5aa6bb5509734cb388537a63007d3087
   ```

2. Wait for the room's approval confirmation. To complete C's scoped human review, personally send a separate message:

   ```text
   @intent-replay-qa qa complete booking-withdrawal 5aa6bb5509734cb388537a63007d3087
   ```

   Its original send time must follow the recorded approval. Expected statement: “Human review completed for the checked local execution behavior, using run 5aa6bb5509734cb388537a63007d3087.” This does not resolve factual uncertainty. These C review actions have not yet occurred.

## Observed stale-approval demonstration

The original human A/B sequence was not performed. The real B/C sequence below is now verified; C's fresh review remains outstanding. The earlier three isolated simulated tests remain separate evidence.

1. The person posted exact B approval `sw_cc26e2db23c2ff3d98607db46364da83` (18), bound to B's sealed evidence. The earlier “I approve it looks good” message did not name a run and created no approval.
2. The assistant sent the user-authorized fresh verification through the real room at sequence 20:

   ```text
   @intent-replay-qa qa verify booking-withdrawal corrected-meta-withdrawal-control
   ```

   C `5aa6bb5509734cb388537a63007d3087` became current and returned its result at 21. B's approval remained historical.
3. After confirming C was current, the assistant sent the explicitly authorized negative test at sequence 22 using B's old ID:

   ```text
   @intent-replay-qa qa complete booking-withdrawal a9ce6b8d4b9f4c1eb6d8cab94d24cd67
   ```

   Actual agent refusal `sw_15092d01154649cb9e4c1c8ab8528fef` (23): **`stale_run`**, “No review completion was granted.” [Open the refusal](http://localhost:56742/switch/pl/5ecqnwd5dbf598ufeb89d9wqxw). The core receipt records the same refusal; no completion rows exist. This was an assistant-operated negative test through the human account under explicit authorization, not an actual human completion or a simulated unit test.

4. Remaining step: the person must freshly inspect and review C using the commands above. Completion requires current, valid evidence, the required guarded/control checks and approval of that exact run. Do not report fresh C review/completion until its actual events and records exist.

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

A, B and C each matched all four frozen expectations. Regression PASS includes the deliberately faulty branch's expected FAIL. Factual accuracy remains INCONCLUSIVE/unassessed; overall task remains FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Human review status is a separate result.

Reports reuse the existing execution evidence interface and exporter. Saved model captures are recorded evidence, and replay adds zero model requests. Any Switch-agent inference is separate; no production-booking or production-readiness claim follows from completing this review.
