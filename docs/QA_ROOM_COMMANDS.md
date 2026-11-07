# Intent Replay — QA Room commands

One personal/local Switch room, agent `intent-replay-qa`, task `booking-withdrawal`, and case set `corrected-meta-withdrawal-control`, on Switch Console 0.40.1 / native Core 0.31.0. In the [Intent Replay QA Mattermost channel](http://localhost:56742/switch/channels/intent-replay-qa), C `5aa6bb5509734cb388537a63007d3087` is current, evidence-valid and **human-review completed**. No further review command is needed.

Actual human B approval was followed by fresh C and a real `stale_run` refusal of the authorized assistant's old-B completion probe. The person then approved C and completed its review through separate original room messages. A and B remain historical. All execution evidence and the earlier unreviewed checkpoints are preserved.

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

## Reopen the completed result

Open [C's exact evidence](http://127.0.0.1:8054/qa/runs/5aa6bb5509734cb388537a63007d3087) to inspect the reports and bound review record without executing anything. No room message is required. An optional read-only room command is:

```text
@intent-replay-qa qa show booking-withdrawal 5aa6bb5509734cb388537a63007d3087
```

## Observed human-review walkthrough

The full demonstration used **B/C**; the original human A/B sequence was not performed. Actual human actions and authorized assistant actions remain distinct:

| Room sequence | Observed action |
|---|---|
| 18 / 19 | The person approved B with exact original event `sw_cc26e2db23c2ff3d98607db46364da83`; the agent confirmed it. The earlier natural-language message at 17 created no approval. |
| 20 / 21 | The assistant's authorized verification created C and the agent returned its result. B's approval stayed historical. |
| 22 / 23 | The assistant's explicitly authorized negative probe attempted completion of old B. The agent returned `stale_run`; no completion was granted by that probe. |
| 24 / 25 | The person approved C with exact original event `sw_64e554b42f2ff28f01d8822989a8d8c6`; the agent confirmed it. |
| 26 / 27 | The person completed C with exact original event `sw_cc40b260975f872a9d47d332973d82f2`; the agent confirmed completion. |

[Open the stale refusal](http://localhost:56742/switch/pl/5ecqnwd5dbf598ufeb89d9wqxw). The 76-check B/C audit captured C unreviewed immediately after that refusal. The later actual C approval was recorded at `2026-11-06T23:59:34.550545Z`; completion followed at `2026-11-07T00:02:10.716142Z`. Both records bind C's evidence SHA-256 `89205c76d584013579812ed74a1965e5ac6534c5068ea17e9e29b2b31e085648`.

The final scoped result is: “Human review completed for the checked local execution behavior, using run 5aa6bb5509734cb388537a63007d3087.” It does not resolve factual uncertainty or establish production readiness. Private proofs are `.local/qa-room-assistant-review/mattermost-b-c-stale-approval-audit.json`, `c-actual-approval-before-completion.json` and `c-actual-completion.json` in the same directory. The three isolated simulated-review tests remain separate evidence.

The separate final `c-human-completion-audit.json` in that directory passed 76/76 checks, confirming both C original events and receipts, their exact evidence binding, two approvals, one completion and unchanged artifacts. C's completed status was also verified in the browser.

## Future manual verification

These steps are for an intentional **new** run, not required for completed C. Send each message separately as a standalone room message without quotation marks or code fences. A new accepted verification immediately supersedes C, including while pending or failed, and requires its own human review.

1. Request a new verification:

   ```text
   @intent-replay-qa qa verify booking-withdrawal corrected-meta-withdrawal-control
   ```

2. Wait for the result, open its exact evidence and inspect both withdrawal and control reports. Replace `RUN_ID` below with the returned full run ID. If satisfied, personally send:

   ```text
   @intent-replay-qa qa approve booking-withdrawal RUN_ID
   ```

3. Wait for the room's approval confirmation, then personally send a separate message:

   ```text
   @intent-replay-qa qa complete booking-withdrawal RUN_ID
   ```

The person must perform approval and completion; an assistant must not create those records on their behalf. Completion requires the exact current run, valid evidence, the required guarded/control checks and its recorded approval. Its original send time must follow approval.

The `@intent-replay-qa ` prefix is optional in the parser; using it addresses the Console agent explicitly. Duplicate deliveries do not create duplicate runs, approvals or result posts. Delayed older verification events cannot supersede a newer platform request. Approval sent before the result, or completion sent before its required approval, is refused even if delivery is delayed. Interrupted executions are not automatically retried; an intentional new `qa verify` request creates a new current run.

## Read the result correctly

For the retained booking on 25 November 2026, Europe/London:

| Case | Faulty worker | Guarded worker |
|---|---|---|
| Withdrawal (`fresh-withdrawal`) | Commits 15:00; execution FAIL | Suppresses; retains 14:00; execution PASS |
| Control (`fresh-control`) | Commits 15:00; execution PASS | Commits 15:00; execution PASS |

A, B and C each matched all four frozen expectations. Regression PASS includes the deliberately faulty branch's expected FAIL. Factual accuracy remains INCONCLUSIVE/unassessed; overall task remains FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Human review status is a separate result.

Reports reuse the existing execution evidence interface and exporter. Saved model captures are recorded evidence, and replay adds zero model requests. Any Switch-agent inference is separate; no production-booking or production-readiness claim follows from completing this review.
