# Intent Replay — QA Room

**Submission materials updated 7 November 2026 UTC. The new Flip video is uploaded and unlisted; final organizer submission is pending the entrant's own action and receipt.**

## Submission preparation checkpoint — 7 November 2026

Track: **Best Business Workflow**. The [official cohost requirements](https://www.devtoolsacademy.com/hackathons/flip-the-switch) call for a public repository, a short workflow video, and a README explaining the connected agents, channel setup and reproduction. The authenticated [submission form](https://www.wemakedevs.org/hackathons/switch/submit), inspected on 7 November, explicitly requires a video **under 3 minutes**, hosted on YouTube or Loom and public or unlisted. The approved final video is **174.788 seconds (2:55)** and meets that length requirement. The [official schedule](https://www.wemakedevs.org/hackathons/switch/schedule) gives **7 November 2026, 11:59 PM IST (18:29 UTC)** as the submission deadline.

The entrant signed in and the actual seven required fields were inspected: title, track, description, GitHub source, demo video, how Switch was used, and feedback about Switch. No `maxlength` attributes were present on the observed text fields; server-side limits are not inferred. The person should enter and submit their own final form: [official rule 3](https://www.wemakedevs.org/hackathons/switch/rules) prohibits automated registration/submission while permitting AI tools for development.

The prepared public source URL is https://github.com/elouahid/intent-replay/tree/flip-qa-room; publication must preserve `main` at the Meta baseline. The new Flip video is https://youtu.be/sPFCppd1n1A, uploaded to the existing lotis7 channel, saved as unlisted, with HD processing complete. The user watched the assembled video and confirmed its audio. The room's completed C checkpoint remains preserved. Loopback room/evidence URLs are local recording surfaces, not judge-accessible URLs.

## Copyable text for the person

Use these values for the observed form fields. The entrant should read and personally submit them; the feedback paragraph is suggested wording for the entrant to confirm.

Project title:

```text
Intent Replay — QA Room
```

Track:

```text
Best Business Workflow
```

Short pitch:

```text
A Switch QA room that replays an agent execution regression, exposes its evidence, and binds human review to the exact run so an older approval cannot complete a newer verification.
```

Video title:

```text
Intent Replay — QA Room | Flip the Switch Demo
```

Published video description (followed by chapter timestamps in YouTube):

```text
Intent Replay connects a managed Codex QA agent to a Mattermost room through Switch. This video walks through the preserved real workflow: saved-case replay, evidence inspection, human approval of B, a newer run C, refusal of stale B completion, and fresh human approval and completion of C.

Flip source and setup: https://github.com/elouahid/intent-replay/tree/flip-qa-room

The Switch room, original-event adapter and exact-run review workflow were added for Flip. The earlier Intent Replay runner, evaluator, saved captures and frozen expectations are preserved.

All four frozen regression expectations match. The deliberately faulty withdrawal execution fails as expected; the guarded execution and control pass. Factual accuracy remains inconclusive. Human completion covers checked local execution behavior only. Saved replay makes zero new model requests; managed-agent inference is separate and unmeasured.
```

Project description:

```text
Intent Replay helps developers and QA teams review agent-driven changes without letting an old approval authorize a newer result. In a Switch-connected Mattermost room, a person requests a supported replay, inspects its evidence, and approves the exact run.

The demo checks a booking change after the customer withdraws consent, alongside a no-withdrawal control. It preserves the earlier Meta runner and evaluator while adding the Switch room workflow, evidence validation, and exact-run human review. All four frozen expectations match, including the deliberately faulty execution's expected failure. Review covers checked local behavior only; factual accuracy remains INCONCLUSIVE.
```

GitHub Repository or contribution:

```text
https://github.com/elouahid/intent-replay/tree/flip-qa-room
```

Demo video:

```text
https://youtu.be/sPFCppd1n1A
```

How did you use Switch in your project?

```text
I worked solo with a managed Codex QA agent connected to Mattermost through Switch. A narrow MCP tool dispatches original room messages; the server verifies their source and binds human review to the exact run and evidence.

In the recorded workflow, I personally approved B, authorized the assistant to request C and attempt completion of old B, and observed that stale completion being refused. I then personally approved and completed C. Saved replay uses no new model inference; the Switch agent's inference is separate.
```

What did you like about Switch, and what would you improve?

```text
I liked having human requests, the managed agent, evidence links, and review confirmations together in one room. It made the workflow visible and reviewable.

I would improve diagnostics for MCP project trust and tool availability, room membership permissions, and service recovery after restart. Clearer Windows setup guidance and Mattermost memory requirements would also help. These were concrete setup issues I encountered while getting the real workflow running.
```

Leave live deployment and the optional track-detail fields blank: this demonstration has no public live service, Core Contribution PR, published build blog, Wispr usage card, or social-post entry. The demonstrated team is one person and a managed agent; do not imply additional human teammates.

## Short description

A Switch QA room that replays a supported agent execution regression, exposes the original evidence, and ties review to the exact run so an older approval cannot complete a newer verification.

## Problem and approach

An agent can propose the intended change while a worker later executes an outdated instruction. After a rerun, a previously granted approval can also become obsolete. QA needs observable execution evidence and an explicit connection between that evidence and the review.

One Console-managed agent accepts fixed verification commands in a personal Mattermost room. A narrow MCP tool passes only the original message ID to the local adapter. The adapter retrieves the authenticated room event; it never accepts an agent's assertion that a person approved. Every accepted request atomically becomes current before execution. Evidence is retained per run, and completion checks the current run, artifact identities, execution contract and exact human approval in one transaction.

## What existed before Flip

The submitted Meta version already provided saved model captures, sealed prepared inputs, a local SQLite booking runner, faulty and guarded workers, independent final booking reads, frozen regression expectations and HTML/ZIP evidence exports. Submitted baseline: `d074b160d7af890ce7d8d99c2f580c597684a95c`. Those sources and captures remain preserved.

Flip adds the persistent room/task/run workflow, original-event Switch adapter, exact-run review binding, evidence server, constrained MCP transport and focused review-safety tests. Runner/evaluator semantics and frozen expectations are unchanged.

## Demonstrated results and scope

The complete real-room sequence is verified: **human approval B → request C → stale completion B refused → human approval C → human completion C**. Three actual Mattermost verification requests automatically produced agent results. A and B are historical; C (`5aa6bb5509734cb388537a63007d3087`) is current, evidence-valid and has completed human review.

The person approved B (`a9ce6b8d4b9f4c1eb6d8cab94d24cd67`) through an exact original room command. Codex requested C and attempted the negative old-B completion probe under the user's authorization. The real room refused that probe with `stale_run`; B's approval remained historical and no completion was granted by that attempt. The person then personally approved C and, after confirmation, sent its separate completion command. The managed agent handled dispatch and result posting. B/C approvals and C completion were actual human actions, distinct from the authorized assistant checks.

B and C's exact pages and both original HTML reports were opened in the browser. The earlier independent A/B audit passed 56 checks; the pre-completion B/C audit passed **76 checks** of original events, bound B approval, stale refusal, seals and evidence artifacts, including all six C artifacts returning HTTP 200. A separate final **C completion audit passed 76/76 checks** of the actual human commands, managed dispatches, receipts, timestamps and unchanged artifact hashes. The refreshed C page visibly confirms completed review; the earlier proofs remain preserved.

The matched pair demonstrates:

- Withdrawal: faulty worker commits 15:00, an expected execution FAIL; guarded worker suppresses the change and retains 14:00, execution PASS.
- No-withdrawal control: both workers commit 15:00, execution PASS.
- All four frozen regression expectations match. Factual accuracy remains INCONCLUSIVE/unassessed; overall task is FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control.

**C's human review completed at 2026-11-07 00:02:10.716142 UTC**, with approval and completion bound to the same C evidence. Completion means only: “Human review completed for the checked local execution behavior, using run 5aa6bb5509734cb388537a63007d3087.” Separately, three isolated tests passed stale completion, historical duplicate approval and concurrent-rerun checks using simulated reviewers and temporary databases. Those tests remain distinct from the completed real-room walkthrough.

Prior verification passed 143 Python tests and eight focused MCP tests. The later three-test selection passed in 4.165 seconds. See [FLIP_VERIFICATION.json](../FLIP_VERIFICATION.json) for precise evidence and [the implementation report](../FLIP_IMPLEMENTATION_REPORT.md) for scope and limitations.

## Technology and usage

Python, SQLite, FastAPI, the existing Intent Replay engine/exporter, Switch Console 0.40.1, native Core 0.31.0, Mattermost, and official MCP SDK 1.28.1. The managed agent uses the existing official Codex CLI 0.166.0 login/model. Saved replay adds zero model requests; managed-agent inference is separate and its exact usage is unmeasured. The local workflow does not establish production booking success or production readiness.

## Materials and publication status

- [README and reproduction](../README.md), [demo script](FLIP_DEMO_SCRIPT.md), [room setup](QA_ROOM_SETUP.md), [human commands](QA_ROOM_COMMANDS.md).
- [Original submitted Meta source](https://github.com/elouahid/intent-replay/tree/d074b160d7af890ce7d8d99c2f580c597684a95c) and [prior Meta video](https://youtu.be/irrL2Acrs6E): historical baseline, not the Flip submission/demo.
- [Flip source branch](https://github.com/elouahid/intent-replay/tree/flip-qa-room) and [new Flip video](https://youtu.be/sPFCppd1n1A). The source branch preserves the original `main`; publication does not establish that the final hackathon form was submitted.

Use the committed-source archive recipe in [the implementation report](../FLIP_IMPLEMENTATION_REPORT.md) when preparing the package. Exclude `.local/`, credentials, dispatch tokens, provider logins and runtime databases. The demonstration's loopback evidence URLs work on that computer only; they are not public judge links. Document machine-specific MCP path adaptation for a fresh checkout.

The actual form and its under-three-minute video requirement were verified. Before the entrant submits, confirm that the Flip branch opens publicly and the video is accessible without the owner's login. Retain the local-behavior and factual-uncertainty limits. Save the organizer's actual receipt before recording final acceptance; these materials make no eligibility or acceptance guarantee.
