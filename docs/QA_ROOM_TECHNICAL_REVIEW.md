# Run A — assistant technical review

Reviewed by Codex on 2026-11-06 at the user's request. **This is an assistant review of retained evidence, not a human approval or completion record.**

Run: `dd19c14126444bb79ef57882bfa48602`; task `booking-withdrawal`; Mattermost room `496e3d1b-8c14-4a6c-9bc5-1e164c0da362`. [Open the exact evidence](http://127.0.0.1:8054/qa/runs/dd19c14126444bb79ef57882bfa48602).

## Technical finding

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

## Limits and live state at review

Factual accuracy remains **INCONCLUSIVE / unassessed** because this proposal-only profile generated no final assistant reply. Overall task remains FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. This does not establish external booking success or production readiness.

The restored Gateway's latest room sequence is 12. A is ready/current and **unreviewed**, with no approval or completion. This review did not dispatch a command, rerun evidence, modify workflow state or create a human record. Saved replay made zero new model requests; managed-agent inference is a separate activity.

Platform identity authenticates an account; it does not independently prove that a person inspected the reports. Posting a review through the person's account using automation would not constitute the actual human action requested for this demonstration.

After asking to delegate the review, the user replied “I approve it” to the proposed autonomous assistant-reviewed demonstration. That chat approval is recorded as conversation context only; it is not an original Mattermost approval event. Continue the assistant-reviewed A/B demonstration while reporting actual human review as incomplete. The original human path remains documented in [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md).

The next real verification request reached Mattermost as `sw_ceb8c35e683bc85544b2f490c8ab56dd` (sequence 13), but the managed provider could not refresh its expired ChatGPT token (401). Agent failure `sw_3fc8dcf784aa49608cb0c59e3ce6997c` (sequence 14) occurred before dispatch; no B run or receipt was created. A remains current. Authentication recovery uses the existing session's isolated Codex home and requires the person's browser sign-in. No human review was fabricated.

Three existing isolated tests were rerun successfully: simulated A/B stale completion, duplicate historical approval/completion against a new run, and atomic completion followed by a concurrent rerun. These use temporary databases and simulated reviewers only. Log: `.local/qa-room-assistant-review/simulated-review-tests-20261106T231812Z.log`; SHA-256 `a65d372104960ed2bb0db151b881ff1230240f03bd37c5b27002436bc15ab93c`. Failed-request proof: `.local/qa-room-assistant-review/failed-b-request-20261106.json`.
