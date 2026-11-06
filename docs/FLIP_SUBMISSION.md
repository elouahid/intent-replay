# Intent Replay — QA Room

**Submission draft for user review. Not submitted or published.**

## Short description

A Switch QA room that replays a supported agent execution regression, exposes the original evidence, and ties review to the exact run so an older approval cannot complete a newer verification.

## Problem and approach

An agent can propose the intended change while a worker later executes an outdated instruction. After a rerun, a previously granted approval can also become obsolete. QA needs observable execution evidence and an explicit connection between that evidence and the review.

One Console-managed agent accepts fixed verification commands in a personal Mattermost room. A narrow MCP tool passes only the original message ID to the local adapter. The adapter retrieves the authenticated room event; it never accepts an agent's assertion that a person approved. Every accepted request atomically becomes current before execution. Evidence is retained per run, and completion checks the current run, artifact identities, execution contract and exact human approval in one transaction.

## What existed before Flip

The submitted Meta version already provided saved model captures, sealed prepared inputs, a local SQLite booking runner, faulty and guarded workers, independent final booking reads, frozen regression expectations and HTML/ZIP evidence exports. Submitted baseline: `d074b160d7af890ce7d8d99c2f580c597684a95c`. Those sources and captures remain preserved.

Flip adds the persistent room/task/run workflow, original-event Switch adapter, exact-run review binding, evidence server, constrained MCP transport and focused review-safety tests. Runner/evaluator semantics and frozen expectations are unchanged.

## Demonstrated results and remaining limit

Two actual Mattermost verification requests automatically produced agent results and accessible reports. A (`dd19c14126444bb79ef57882bfa48602`) became historical when B (`a9ce6b8d4b9f4c1eb6d8cab94d24cd67`) was accepted. B is current and ready; its page and both original HTML reports were opened in the browser. The requests were sent by Codex under the user's authorization, and the managed agent handled dispatch and result posting. An independent read-only audit passed 56 checks of original events, run bindings, seals and evidence artifacts, including all six B artifacts served over HTTP.

The matched pair demonstrates:

- Withdrawal: faulty worker commits 15:00, an expected execution FAIL; guarded worker suppresses the change and retains 14:00, execution PASS.
- No-withdrawal control: both workers commit 15:00, execution PASS.
- All four frozen regression expectations match. Factual accuracy remains INCONCLUSIVE/unassessed; overall task is FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control.

**B remains unreviewed and cannot be completed. No actual human approval or completion is recorded.** The user authorized assistant inspection of the technical evidence. Separately, three isolated tests passed stale completion, historical duplicate approval and concurrent-rerun checks using simulated reviewers and temporary databases. This supports the implementation; it is not a real human A/B stale-approval demonstration.

Prior verification passed 143 Python tests and eight focused MCP tests. The later three-test selection passed in 4.165 seconds. See [FLIP_VERIFICATION.json](../FLIP_VERIFICATION.json) for precise evidence and [the implementation report](../FLIP_IMPLEMENTATION_REPORT.md) for scope and limitations.

## Technology and usage

Python, SQLite, FastAPI, the existing Intent Replay engine/exporter, Switch Console 0.40.1, native Core 0.31.0, Mattermost, and official MCP SDK 1.28.1. The managed agent uses the existing official Codex CLI 0.166.0 login/model. Saved replay adds zero model requests; managed-agent inference is separate and its exact usage is unmeasured. The local workflow does not establish production booking success or production readiness.

## Materials and publication status

- [README and reproduction](../README.md), [demo script](FLIP_DEMO_SCRIPT.md), [room setup](QA_ROOM_SETUP.md), [human commands](QA_ROOM_COMMANDS.md).
- [Original submitted Meta source](https://github.com/elouahid/intent-replay/tree/d074b160d7af890ce7d8d99c2f580c597684a95c) and [prior Meta video](https://youtu.be/irrL2Acrs6E): historical baseline, not the Flip submission/demo.
- Flip source currently resides in the isolated `flip-qa-room` branch. This draft provides no new public Flip source URL or published Flip video URL.

Use the committed-source archive recipe in [the implementation report](../FLIP_IMPLEMENTATION_REPORT.md) when preparing the package. Exclude `.local/`, credentials, dispatch tokens, provider logins and runtime databases. The demonstration's loopback evidence URLs work on that computer only; they are not public judge links. Document machine-specific MCP path adaptation for a fresh checkout.

Before publication, confirm the actual submission form and its requirements, select the final source checkpoint and recording, and retain the stated human-review limitation unless the person completes the real walkthrough. This draft makes no claim about eligibility, required video duration, or final submission acceptance.
