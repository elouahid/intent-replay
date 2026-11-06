# Intent Replay — QA Room demo script

Draft for review; not a published video. Show the real room and retained evidence. Actual human review remains incomplete; the assistant's authorized technical inspection and simulated tests must stay labeled separately.

## Prepare

Use the existing room/agent and startup steps in [QA_ROOM_SETUP.md](QA_ROOM_SETUP.md). Reuse the evidence listener on port 8054. Open the room, A and B in separate tabs. Keep credential files, dispatch tokens, provider logins and runtime databases off screen. Do not send approval/completion messages on the person's behalf.

## Show and say

| Screen/action | Suggested narration |
|---|---|
| Actual Mattermost QA room | “Intent Replay helps a QA reviewer reproduce an agent execution defect and review the exact result. One managed agent handles a fixed supported replay request.” |
| A's original request and deterministic result | “This real room request reached the existing runner through the managed MCP tool. The server returned the run ID and accessible evidence.” |
| A's withdrawal report, then control report | “The faulty worker commits 15:00 after withdrawal. The guarded worker retains 14:00. Without withdrawal, both commit 15:00. The deliberately faulty FAIL is expected, so all frozen regression expectations match.” |
| B's fresh request/result, then refreshed A and B pages | “A new accepted request makes B current. A is historical. B is ready but unreviewed, and completion is unavailable.” |
| Clearly labeled isolated test result | “Three tests with simulated reviewers and temporary databases passed stale completion, historical duplicate approval, and concurrent rerun checks. These are automated tests, not a completed human review in this room.” |
| B's evidence and unreviewed status | “The assistant inspected the technical evidence with the user's permission. Actual human approval and completion remain outstanding. Factual accuracy stays inconclusive; this is local execution evidence, not production readiness.” |

Do not call the A-to-B room sequence a demonstrated stale-*approval* refusal: neither live run has a human approval. That behavior is covered by the isolated simulated tests. A full human demonstration still needs an actual approval, a later rerun, stale completion refusal, then review and completion of the newer run.

## Exact retained evidence

| Item | Identity |
|---|---|
| A | `dd19c14126444bb79ef57882bfa48602` |
| A request/result | `sw_b116d44a4e801a59d8f3cd30e64372dc` / `sw_22b4f2385c01448297121bd1d46314ec` — sequences 11/12 |
| B | `a9ce6b8d4b9f4c1eb6d8cab94d24cd67` |
| B request/result | `sw_2038d700ac6120ad2ddd84c04b7139ca` / `sw_1a434e896a694e1db3d5ae3399453cdd` — sequences 15/16 |

[Open A](http://127.0.0.1:8054/qa/runs/dd19c14126444bb79ef57882bfa48602) · [Open B](http://127.0.0.1:8054/qa/runs/a9ce6b8d4b9f4c1eb6d8cab94d24cd67). Both report interfaces were opened in the demonstrated environment. A read-only audit passed 56 checks, including original-event provenance, report seals and all six B artifact hashes. The room requests were sent by Codex under user authorization; the managed agent dispatched and posted results automatically. They were verification requests, not human approval actions.

The separately labeled test selection passed **3 tests in 4.165 seconds**:

- `SwitchDispatcherTests.test_simulated_walkthrough_stale_A_then_review_and_complete_B`
- `QaRoomTests.test_duplicate_historical_approval_and_completion_do_not_affect_new_run`
- `QaRoomTests.test_atomic_completion_followed_by_concurrent_rerun_is_unreviewed`

Private local log: `.local/qa-room-assistant-review/simulated-review-tests-20261106T231812Z.log`; SHA-256 `a65d372104960ed2bb0db151b881ff1230240f03bd37c5b27002436bc15ab93c`. It used temporary databases and simulated reviewers, with no live dispatch. Display a sanitized result excerpt rather than private runtime state.

Replay uses zero new model requests. Switch-agent inference is separate and exact usage was not measured. The [prior Meta video](https://youtu.be/irrL2Acrs6E) is historical background, not this demo. No recording duration or submission-rule compliance is claimed by this script.
