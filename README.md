# Intent Replay — QA Room

A replay can pass its checks while its human approval belongs to an older run. Intent Replay brings a supported execution regression into a Switch room, exposes its original evidence, and binds review to the exact result. Accepting a rerun immediately makes the new run current, including while it is pending or fails.

One person, one Console-managed QA agent, and one local Mattermost room use the retained booking withdrawal/control pair. The existing runner, evaluator, saved model captures and report exporter are reused unchanged.

## Verified checkpoint

Three real Mattermost verification requests were automatically handled by the managed agent through `qa_room.dispatch_original_message`. The verification requests were sent by Codex under the user's authorization. The person sent the exact approval command for B before C was requested; that actual human review is recorded separately.

| Run | ID | Observed state |
|---|---|---|
| A | `dd19c14126444bb79ef57882bfa48602` | Historical after B was accepted |
| B | `a9ce6b8d4b9f4c1eb6d8cab94d24cd67` | Historical; actual human approval retained only for B |
| C | `5aa6bb5509734cb388537a63007d3087` | Current, ready, unreviewed; completion unavailable |

B and C's exact pages and both original HTML reports opened in the browser. The earlier A/B audit passed 56 checks; the final read-only B/C audit passed **76 checks**, including the actual B approval, stale refusal and all six sealed C artifacts served over HTTP. The person's exact B approval was recorded from the original Mattermost event and confirmed by the agent. Accepting C made B historical without transferring its approval. A user-authorized assistant attempt to complete old B was refused with **`stale_run` in the real room**. **C still requires fresh human review; no completion was granted.** Three separate tests with simulated reviewers cover stale approval, historical duplicates and concurrent reruns.

| Case | Faulty worker | Guarded worker |
|---|---|---|
| Withdrawal | Commits 15:00; expected execution FAIL | Suppresses; retains 14:00; execution PASS |
| No-withdrawal control | Commits 15:00; execution PASS | Commits 15:00; execution PASS |

All four frozen expectations match. Factual accuracy remains **INCONCLUSIVE / unassessed**; overall task remains FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Any eventual completion means only: “Human review completed for the checked local execution behavior, using run <ID>.”

## Resume the demonstrated Windows setup

The installed setup uses Switch Console **0.40.1**, native Core **0.31.0**, Docker-backed Mattermost, and the existing managed agent `intent-replay-qa`. Start Docker and the existing native server/Mattermost only if stopped. Use the preserved Console profile:

```powershell
Start-Process -FilePath 'C:\Users\asus\AppData\Local\Programs\Switch Console\Switch Console.exe' -ArgumentList 'switchdash://focus'
Set-Location 'C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip'
$qaPython = 'C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.venv\Scripts\python.exe'
& $qaPython -B .\source\scripts\run_qa_room.py probe
```

Reuse the evidence listener on port 8054. **Only if it is absent**, start one instance and keep it running:

```powershell
& $qaPython -B .\source\scripts\run_qa_room.py serve
```

Open the [QA room](http://localhost:56742/switch/channels/intent-replay-qa) and [current evidence](http://127.0.0.1:8054/qa/current) on this computer. Confirm the native server and live single-tool MCP catalog before sending a fresh standalone room request:

```text
@intent-replay-qa qa verify booking-withdrawal corrected-meta-withdrawal-control
```

This requests a new current run. To inspect C without rerunning it, open [C's retained evidence](http://127.0.0.1:8054/qa/runs/5aa6bb5509734cb388537a63007d3087). The full startup, private identity-reference setup and recovery record are in [QA_ROOM_SETUP.md](docs/QA_ROOM_SETUP.md); review commands are in [QA_ROOM_COMMANDS.md](docs/QA_ROOM_COMMANDS.md).

## Reproduce in a fresh checkout

Create an isolated Python environment; do not reinstall into the preserved submitted environment:

```powershell
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r .\source\requirements.txt
```

The saved replay needs no provider key. Run the same two prepared cases from the repository root:

```powershell
& .\.venv\Scripts\python.exe -B .\source\scripts\run_saved_regression.py --prepared .\source\repaired_live_proposal_evidence\prepared\fresh-withdrawal-meta.json --prepared .\source\repaired_live_proposal_evidence\prepared\fresh-control-meta.json --output .\.local\flip-regression
```

Exit 0 means frozen expectations matched, including the deliberately faulty withdrawal's expected FAIL. Exit 1 means a mismatch; exit 2 means invalid evidence or an execution error.

The Switch integration also needs a locally configured supported Switch/Mattermost installation, authenticated room membership, a pinned reviewer identity and an agent provider login. These private settings are not bundled. The tracked `.codex/config.toml` contains **demonstration-machine absolute paths**: adapt its Python command, script argument and working directory to your checkout. Its optional SDK pin is `source/requirements-qa-mcp.txt` (`mcp==1.28.1`); install it only into an isolated MCP environment if needed. The demonstrated host already had that SDK. Authorize project trust explicitly and verify the live tool catalog; a configuration-only read is insufficient. Follow [setup](docs/QA_ROOM_SETUP.md) and [agent instructions](docs/QA_ROOM_AGENT_INSTRUCTIONS.md), using your own verified identities and credential-file references.

## Evidence, demo and limits

- [Verification record](FLIP_VERIFICATION.json) and [implementation report](FLIP_IMPLEMENTATION_REPORT.md): actual events, tested behavior and outstanding human review.
- [Demo script](docs/FLIP_DEMO_SCRIPT.md) and [submission draft](docs/FLIP_SUBMISSION.md): prepared materials, not a published Flip video or submitted entry.
- [Handoff](FLIP_HANDOFF.md): continuation and exact current evidence.

Prior implementation verification passed 143 Python tests and eight focused MCP tests. A later isolated selection passed three review-safety tests in 4.165 seconds. Replay makes zero new model requests; the managed Switch agent uses its provider separately, with exact usage unmeasured. The backend is fictional local SQLite booking behavior, not a production booking system. Evidence hashes establish consistency, not independent provider attestation.

## Preserved Meta submission

Flip starts from submitted commit `d074b160d7af890ce7d8d99c2f580c597684a95c`. The separate submitted checkout, archive, model captures, configuration and runner/evaluator contract remain preserved; see [baseline verification](FLIP_BASELINE_VERIFICATION.json).

The [original submitted README](https://github.com/elouahid/intent-replay/blob/d074b160d7af890ce7d8d99c2f580c597684a95c/README.md), [original verification notes](docs/VERIFICATION.md), and [prior Meta demonstration video](https://youtu.be/irrL2Acrs6E) describe the earlier submission. That video is not the Flip room demonstration. `PUBLIC_SOURCE_MANIFEST.json` describes the original submitted snapshot, not the extended Flip tree.

First-party code and documentation remain under the [MIT License](LICENSE). Third-party dependencies, fonts and provider captures retain their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
