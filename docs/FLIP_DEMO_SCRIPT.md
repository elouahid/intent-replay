# Intent Replay — QA Room demo script

Draft for review; not a published video. The real B → C review sequence completed on **7 November 2026 UTC**. The person approved B, then separately approved and completed C after the stale-B completion refusal. Label actual human actions, authorized assistant probes and simulated tests separately.

## Prepare

Use the existing room/agent and startup steps in [QA_ROOM_SETUP.md](QA_ROOM_SETUP.md). Reuse the evidence listener on port 8054. Open the room, B and C in separate tabs. Keep credential files, dispatch tokens, provider logins and runtime databases off screen. Show the retained events rather than replaying commands for the recording; do not fabricate human review.

## Show and say

| Screen/action | Suggested narration |
|---|---|
| Actual Mattermost QA room | “Intent Replay helps a QA reviewer reproduce an agent execution defect and review the exact result. One managed agent handles a fixed supported replay request.” |
| B's original request and deterministic result | “This real room request reached the existing runner through the managed MCP tool. The server returned the run ID and accessible evidence.” |
| B's withdrawal report, then control report | “The faulty worker commits 15:00 after withdrawal. The guarded worker retains 14:00. Without withdrawal, both commit 15:00. The deliberately faulty FAIL is expected, so all frozen regression expectations match.” |
| The person's exact B approval and agent confirmation | “The person approved this exact run. The original human event and evidence binding are recorded; a model's assertion would not grant approval.” |
| C's original request/result and B's historical status | “The user authorized the assistant to request another verification. C became current without inheriting B's approval. B's review stayed attached to B.” |
| Authorized stale-B completion probe and agent refusal | “The user authorized the assistant to test completion of old B. The real room returned stale_run: a newer verification was requested. That attempt granted no completion; C was still unreviewed at that point.” |
| The person's C approval, confirmation, completion and confirmation | “The person inspected the new result and approved C. After its confirmation, they sent a separate completion command. Both records bind the same exact C evidence.” |
| Clearly labeled isolated test result | “Three tests with simulated reviewers and temporary databases passed stale completion, historical duplicate approval, and concurrent rerun checks. These are separately labeled automated tests.” |
| C's completed review status | “Human review is complete for this exact local execution. Factual accuracy stays inconclusive; completion does not establish production readiness or external booking success.” |

B and C approvals and C completion were actual human actions. C's verification and the stale-B completion probe were assistant-initiated under authorization; the probe was a negative test, not a new human approval. The earlier natural-language approval message (sequence 17) was not accepted as an exact approval command. The real room refusal verified the stale-B guard; C subsequently received its own fresh approval and scoped completion.

## Exact retained evidence

| Item | Identity |
|---|---|
| A | `dd19c14126444bb79ef57882bfa48602` |
| A request/result | `sw_b116d44a4e801a59d8f3cd30e64372dc` / `sw_22b4f2385c01448297121bd1d46314ec` — sequences 11/12 |
| B | `a9ce6b8d4b9f4c1eb6d8cab94d24cd67` |
| B request/result | `sw_2038d700ac6120ad2ddd84c04b7139ca` / `sw_1a434e896a694e1db3d5ae3399453cdd` — sequences 15/16 |
| Actual human B approval / confirmation | `sw_cc26e2db23c2ff3d98607db46364da83` / `sw_de7b1bbacf2141308561615a0231dd8b` — sequences 18/19 |
| C | `5aa6bb5509734cb388537a63007d3087` |
| C request/result | `sw_1a5b66cff69446d841a207e674ac70de` / `sw_46977430bfda4b8c8984486c32e0d397` — sequences 20/21 |
| Authorized stale-B probe / refusal | `sw_1e409655fe38cff2539ead5969f4ab89` / `sw_15092d01154649cb9e4c1c8ab8528fef` — sequences 22/23 |
| Actual human C approval / confirmation | `sw_64e554b42f2ff28f01d8822989a8d8c6` / `sw_bdae5cc9794f41498544ff0c3841559d` — sequences 24/25 |
| Actual human C completion / confirmation | `sw_cc40b260975f872a9d47d332973d82f2` / `sw_4f9e4a8c72d74c6996eb12d27c05a456` — sequences 26/27 |

[Open B](http://127.0.0.1:8054/qa/runs/a9ce6b8d4b9f4c1eb6d8cab94d24cd67) · [Open C](http://127.0.0.1:8054/qa/runs/5aa6bb5509734cb388537a63007d3087). B and C's exact pages and both original HTML reports were opened in the demonstrated environment. The earlier A/B audit passed 56 checks. The pre-completion read-only B/C audit passed **76 checks**, including original-event provenance, B's bound human approval, the stale refusal, and all six sealed C artifacts returning HTTP 200.

The managed agent dispatched original commands and posted results automatically. Actual human B approval was sent at `2026-11-06T23:44:30.789238Z`; its evidence binding remains attached to historical B. The authorized stale-B probe was sent at `2026-11-06T23:48:25.785334Z` and the agent posted `stale_run` refusal at `23:48:30.766085Z`. At that earlier checkpoint, C remained current, evidence-valid and unreviewed. That private audit is preserved at `.local/qa-room-assistant-review/mattermost-b-c-stale-approval-audit.json`; SHA-256 `8dfe8a8af5d815d8c54161b5a5ae2c8d00dbbdce6fde66b349a6d2b8e0d22c7c`.

The person sent C approval at `2026-11-06T23:59:29.600223Z`, then completion at `2026-11-07T00:02:06.428314Z`. Stored completion time is `2026-11-07T00:02:10.716142Z`. C's approval and completion share evidence binding `89205c76d584013579812ed74a1965e5ac6534c5068ea17e9e29b2b31e085648`. The final statement is: “Human review completed for the checked local execution behavior, using run 5aa6bb5509734cb388537a63007d3087.”

The separate final **C completion audit passed 76/76 checks**, including both original human commands, managed MCP dispatches, receipts, source-time order and unchanged hashes for all six HTTP artifacts. The refreshed C page visibly confirms completed review; B stays historical, approved and incomplete. Private final audit: `.local/qa-room-assistant-review/c-human-completion-audit.json`; SHA-256 `f49dd7ecd13ae256ec0ae8d8f7b21bbd4c459f1ac74cc844bd401451863407e6`. The earlier stale-guard audit remains preserved separately.

The separately labeled test selection passed **3 tests in 4.165 seconds**:

- `SwitchDispatcherTests.test_simulated_walkthrough_stale_A_then_review_and_complete_B`
- `QaRoomTests.test_duplicate_historical_approval_and_completion_do_not_affect_new_run`
- `QaRoomTests.test_atomic_completion_followed_by_concurrent_rerun_is_unreviewed`

Private local log: `.local/qa-room-assistant-review/simulated-review-tests-20261106T231812Z.log`; SHA-256 `a65d372104960ed2bb0db151b881ff1230240f03bd37c5b27002436bc15ab93c`. It used temporary databases and simulated reviewers, with no live dispatch. Display a sanitized result excerpt rather than private runtime state.

Replay uses zero new model requests. Switch-agent inference is separate and exact usage was not measured. The [prior Meta video](https://youtu.be/irrL2Acrs6E) is historical background, not this demo. No recording duration or submission-rule compliance is claimed by this script.
