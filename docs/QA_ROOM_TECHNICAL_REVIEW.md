# Retained runs — technical review and human-review provenance

Reviewed by Codex on 2026-11-06 at the user's request. **This is an assistant review of retained evidence, not a human approval or completion record.**

Task `booking-withdrawal`; Mattermost room `496e3d1b-8c14-4a6c-9bc5-1e164c0da362`. [A's preserved evidence](http://127.0.0.1:8054/qa/runs/dd19c14126444bb79ef57882bfa48602) and [B's evidence](http://127.0.0.1:8054/qa/runs/a9ce6b8d4b9f4c1eb6d8cab94d24cd67) are historical. C is current. The latest B/C checkpoint supersedes the earlier workflow states without changing retained execution evidence.

## Latest B/C human-review checkpoint

The person posted exact B approval `sw_cc26e2db23c2ff3d98607db46364da83` (18), confirmed by the managed agent at 19. Before C, B was current/approved and eligible to complete, with binding `ba73f978df6da5f22bec1b5a9ee2b55b367a6cc4512e8aebd20bf1e71be79630`. The pre-C proof is preserved as `.local/qa-room-assistant-review/b-actual-approval-before-c.json`.

The authorized assistant request at 20 produced C `5aa6bb5509734cb388537a63007d3087` at 21. After confirming C was current, the assistant sent the user's authorized negative test of old B completion at 22. Actual agent response at 23 and the core receipt both record `stale_run`; no completion was granted. This establishes the real-room guard against B's actual human approval. B approval was the person's action; C verification and the refused negative probe were assistant UI actions, not fresh human review.

The independent read-only audit passed **76/76 checks**, including original-event hashes, the pre-C approval, retained B binding, C's distinct binding, report/prepared seals, all six HTTP artifacts, ZIP manifests and zero completion rows. C's exact page and both original HTML reports opened. All four frozen branch expectations match; factual accuracy remains INCONCLUSIVE/unassessed. Proof: `.local/qa-room-assistant-review/mattermost-b-c-stale-approval-audit.json`; managed tool activity: `b-c-managed-activity.json` in that directory. The approval, C request and stale probe each completed through `qa_room.dispatch_original_message`, with no operator dispatch.

C binding: `89205c76d584013579812ed74a1965e5ac6534c5068ea17e9e29b2b31e085648`. Withdrawal execution `8679096357c94167887d91263db6c57a`, seal `a01431fa8fdfd21d023a62de7df361d6946b3ccf0a0520e7abb805a747f1da9f`; control execution `ba353c29e0fd45d99731d626177f7a7b`, seal `1fa22cc81f2d3e9aa65f61314a110a3f8d33648e28be3bb24277ff9f1ad91589`. Frozen prepared inputs and execution contract are unchanged.

**B is historical/approved; C is current/unreviewed, with no approval or completion.** The person's fresh C review/completion is outstanding. The sections below retain earlier assistant reviews and states at their stated capture times; they are not current human-review records.

## Historical A technical finding

The evidence supports acceptance of the **included local SQLite execution behavior** for this saved withdrawal/control pair. All four branches match the frozen expectations. No material blocker was found within that scope.

| Case / worker | Evidence inspected | Execution assessment |
|---|---|---|
| Withdrawal / guarded | Revision 2 accepted at journal sequence 7; authorization denied at 8; stale action suppressed at 9. Check and suppression share transaction `b35669cc13df4b108d73ca6fe139fd7a`. Independent read after sequence 9 retains 14:00. | PASS |
| Withdrawal / faulty | Revision 2 was accepted before the deliberate stale commit. Independent read contains 15:00; action authorization and requested outcome fail as expected. | Expected FAIL |
| No-withdrawal / guarded | Revision 1 remains applicable. Authorization at sequence 6 and commit at 7 share transaction `14b2be60b31443d7a83d6006baf973eb`. Independent read after sequence 7 contains 15:00. | PASS |
| No-withdrawal / faulty | Revision 1 remains applicable and the independent read contains the authorized 15:00 result. | PASS |

The guarded control is necessary evidence: the implementation does not obtain its withdrawal result by suppressing every action. Both branches reuse the same recorded proposal; they are not independent model trials. The proposal predates withdrawal, so the injected worker defect does not establish that the model ignored an instruction it had received.

## Evidence binding and guard review

- A binding SHA-256: `14e259887a131272446d32aec9216eeadfb889b54a6d765f077bbccd48ec91cb`.
- Withdrawal execution: `1df908f7e9db4136aa0a429457e1a19b`; report seal `9f387d4b35605ef6838065fa1b6e4124dbfcf7c8bbbe6731e34bf4559924a4fb`.
- Control execution: `2e595f2904d842619981bfdf495e6c75`; report seal `19e6c6718c88999f00f79f2078aed49f247be8a4a5b4443fb20d53e13d2e8bf7`.
- The existing independent audit passed 46 checks. The resume check confirmed retained report/prepared seals and all six artifact hashes; live evidence validation remains true. Private audit files: `.local/qa-room/mattermost-run-a-independent-audit.json` and `.local/qa-room/resume-audit-20261106.json`.
- `qa_room.py` makes a new request current and resets task review status in its acceptance transaction. Review/completion recheck current run, exact evidence binding and authoritative event time under the write lock. `qa_room_switch.py` fetches the original room event and requires the pinned human account and exact command.
- Prior isolated tests cover stale A, unapproved B, duplicate historical approvals, races, delayed source timestamps and corrupt evidence. Simulated reviewers in those tests are not real human-room approval evidence. No live A/B human walkthrough is claimed by this review.

## Limits and A state at initial review

Factual accuracy remains **INCONCLUSIVE / unassessed** because this proposal-only profile generated no final assistant reply. Overall task remains FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. This does not establish external booking success or production readiness.

At the initial review, the restored Gateway's latest room sequence was 12. A was ready/current and **unreviewed**, with no approval or completion. That technical inspection did not dispatch a command, rerun evidence, modify workflow state or create a human record. Saved replay made zero new model requests; managed-agent inference is a separate activity.

Platform identity authenticates an account; it does not independently prove that a person inspected the reports. Posting a review through the person's account using automation would not constitute the actual human action requested for this demonstration.

After asking to delegate the review, the user replied “I approve it” to the proposed autonomous assistant-reviewed demonstration. That chat approval is recorded as conversation context only; it is not an original Mattermost approval event. Continue the assistant-reviewed A/B demonstration while reporting actual human review as incomplete. The original human path remains documented in [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md).

The next real verification request reached Mattermost as `sw_ceb8c35e683bc85544b2f490c8ab56dd` (sequence 13), but the managed provider could not refresh its expired ChatGPT token (401). Agent failure `sw_3fc8dcf784aa49608cb0c59e3ce6997c` (sequence 14) occurred before dispatch; that request created no B run or receipt. A remained current until the successful fresh request below. Authentication recovery used the existing session's isolated Codex home and the person's browser sign-in. No human review was fabricated.

Three existing isolated tests were rerun successfully: simulated A/B stale completion, duplicate historical approval/completion against a new run, and atomic completion followed by a concurrent rerun. These use temporary databases and simulated reviewers only. Log: `.local/qa-room-assistant-review/simulated-review-tests-20261106T231812Z.log`; SHA-256 `a65d372104960ed2bb0db151b881ff1230240f03bd37c5b27002436bc15ab93c`. Failed-request proof: `.local/qa-room-assistant-review/failed-b-request-20261106.json`.

## Historical B checkpoint before approval

After the person completed scoped sign-in and the existing agent restarted successfully, Codex sent a fresh verification through the actual Mattermost UI: `sw_2038d700ac6120ad2ddd84c04b7139ca`, sequence 15, 23:30:20 UTC. The managed agent's activity records completed `qa_room.dispatch_original_message` and completed turn `b0294787-bfdf-5039-9362-1a41241514e9`. It returned B `a9ce6b8d4b9f4c1eb6d8cab94d24cd67` in result `sw_1a434e896a694e1db3d5ae3399453cdd`, sequence 16. No operator dispatch was used.

B supports the same scoped acceptance finding as A. The guarded withdrawal accepts revision 2 at journal sequence 7, denies authorization at 8 and suppresses at 9 in shared transaction `70aad15c973a4a0a82bf83591fcd050c`; the independent read after 9 retains 14:00. The guarded control authorizes revision 1 at sequence 6 and commits at 7 in shared transaction `7fadfba6617d4721a796e846608013d3`; its independent read after 7 is 15:00. The faulty withdrawal's expected execution FAIL and the other three execution PASS outcomes all match their frozen expectations.

- B binding SHA-256: `ba73f978df6da5f22bec1b5a9ee2b55b367a6cc4512e8aebd20bf1e71be79630`.
- Withdrawal execution: `1405d7351aca4324b9b837e228c0caff`; report seal `97ffff1b0835bbe6721da7fb75ab7ce9fd04a3b6581242f1b75e6e877bfba180`.
- Control execution: `95cdbdbe24ce4ca28208d952b85347fa`; report seal `7e88f520f0583eb8aa3484e4ace1662eb3c8c71eea6f8ced7b95188446901e68`.
- Both prepared seals, the original capture and execution contract are unchanged. Executions and the run binding are distinct from A.
- The read-only audit passed **56/56 checks** of original events, posted receipt, bindings, seals, six HTTP/disk artifacts and ZIP manifests. Both original HTML reports and B's index opened in the browser. Proof: `.local/qa-room-assistant-review/mattermost-a-b-evidence-audit.json`; managed activity: `.local/qa-room-assistant-review/run-b-managed-activity.json`.

At this pre-approval B capture, A was historical with valid evidence and B was current and eligible for approval, but could not complete. Both then had `approval=null`, `completion=null`, `review_status=unreviewed`; the database had zero review/completion records. That capture demonstrated current-run replacement, not rejection of a historical human approval, because none existed yet. The latest B/C checkpoint above separately records the person's subsequent B approval and the real stale-B refusal. Current C review instructions are in [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md).

Factual accuracy remains INCONCLUSIVE/unassessed and overall task remains FAIL for faulty withdrawal, INCONCLUSIVE for guarded/control. B used zero new replay-model calls; managed-agent inference occurred separately with exact usage unmeasured. The preserved local SQLite evidence establishes neither external booking success nor production readiness.
