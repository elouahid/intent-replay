# Intent Replay — QA Room demo script

Draft for review; not a published video. The real B → C review sequence completed on **7 November 2026 UTC**. The person approved B, then separately approved and completed C after the stale-B completion refusal. Label actual human actions, authorized assistant probes and simulated tests separately.

## Prepare

Use the existing room/agent and startup steps in [QA_ROOM_SETUP.md](QA_ROOM_SETUP.md). Reuse the evidence listener on port 8054. Open the room, B and C in separate tabs. Keep credential files, dispatch tokens, provider logins and runtime databases off screen. Show the retained events rather than replaying commands for the recording; do not fabricate human review.

## Numbered recording plan

Aim for **2:30–2:50** as an editorial target, not an asserted competition limit. The times below allow brief tab changes. Read the quoted narration; keep full run IDs visible without reading them aloud. Begin by opening the room, B and C tabs, then rehearse only segment 1 before recording the remaining segments one at a time. Do not type, stage or send commands.

1. **Introduce the completed workflow — 0:00–0:20.**

   Screen: the existing Mattermost QA room, with B's retained verification request/result visible (sequences 15/16).

   > This is Intent Replay — QA Room, built with Switch. It connects my Codex QA agent to Mattermost, so I can request a replay, inspect the evidence, and approve the exact result. This is a walkthrough of our completed real-room workflow.

2. **Show what the replay proves — 0:20–0:55.**

   Screen: B's evidence page, its withdrawal HTML report, then its control HTML report. Show expected/observed outcomes and the independent booking read.

   > The same saved proposal runs through two local workers. After the customer withdraws the change, the deliberately faulty worker commits three p.m. and fails its execution check. The guarded worker suppresses the change and keeps two p.m. In the no-withdrawal control, both correctly commit three p.m. All four frozen expectations match, including the expected failure. These reports retain the action journal and an independent booking read.

3. **Show the person's B approval — 0:55–1:15.**

   Screen: the exact B approval and the agent's confirmation (sequences 18/19). Keep the B run ID visible.

   > I personally inspected the evidence and approved run B with this exact command. The server retrieved my original message and bound the review to B's run and evidence. An agent's assertion cannot grant that approval.

4. **Show the rerun becoming current — 1:15–1:35.**

   Screen: C's retained request/result (sequences 20/21), then B's historical page. Use the original C result message to show its state at creation; today's C page is already completed.

   > Next, I authorized the assistant to request run C. As soon as C was accepted, it became current. B's approval stayed attached to historical B; it could not carry forward to the new result.

5. **Show the actual stale refusal — 1:35–1:55.**

   Screen: the retained old-B completion probe and the `stale_run` refusal (sequences 22/23). This is an assistant-initiated negative test authorized by the user.

   > I also authorized this negative test: try to complete old B after C exists. The dispatcher refused with stale_run. No completion was granted by that attempt. This is the actual room response.

6. **Show fresh human review and completion — 1:55–2:20.**

   Screen: C approval/confirmation (sequences 24/25), then C completion/confirmation (26/27). Finish on C's completed evidence page.

   > I then personally reviewed C. This is my approval and its confirmation, followed by my separate completion command and the agent's confirmation. Both records bind the same C evidence. The current page shows completed human review, while B remains historical and incomplete.

7. **Close with contribution and scope — 2:20–2:45.**

   Screen: C's completed-review statement and the visible INCONCLUSIVE verdicts. End on the exact run ID.

   > Flip adds the persistent review workflow, original-message verification, and guarded completion around the preserved Meta submission. Replay makes no new model requests; the Switch agent's inference is separate. This completion covers checked local behavior only. Factual accuracy remains inconclusive; it does not establish production readiness.

Keep the simulated tests in the appendix or an optional separately labeled supporting clip. The main video above shows retained real-room evidence only.

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
