# Maintained main promotion — 15 November 2026

**Publication completed and verified, 15 November 2026:** after explicit user authorization, an atomic non-force push published maintained `main` at `fa5ef91159d2783813caf2043dd57542afbcfc94` and the two annotated submission tags below. Remote `flip-qa-room` remained at `79fa75e10bf06ad6dd44acc3836e97ea71cd94f4`. This records that publication checkpoint; subsequent maintenance may advance `main`.

The user requested that `main` become the maintained Intent Replay version, incorporating the stable Flip QA room while preserving both submissions. The following preparation and verification record preceded that authorized push. Public documentation omits personal machine paths and deployment identities; the original records remain private and in the preserved submission snapshots.

## Branch comparison and integration

After a fresh fetch, `origin/main` and local `main` were both `d074b160d7af890ce7d8d99c2f580c597684a95c`. Remote `flip-qa-room` was `79fa75e10bf06ad6dd44acc3836e97ea71cd94f4`; local `flip-qa-room` was its direct child `c58d563d18544b579d26d4a3ea5285ad186f9cc8`, a three-document receipt closeout. Both working trees were clean, including untracked source files. Private ignored runtime/evidence directories were preserved in place.

`main...flip-qa-room` had **0 main-only and 12 Flip-only commits**. Main was fast-forwarded normally with `git merge --ff-only flip-qa-room`, retaining every commit. A subsequent maintenance commit updates navigation/setup documentation and replaces the automatically loaded, machine-bound MCP configuration with an explicit template. There is no application, runner, evaluator, frozen-expectation or model-capture change in that maintenance commit.

The promoted code adds the persistent QA workflow, original authenticated room-message dispatch, guarded evidence delivery and optional MCP transport. A new verification becomes current immediately; approval and completion stay bound to the exact run and evidence. The original saved-replay UI, reports, exporter and local execution behavior remain available.

## Verified submitted versions

| Submission | Exact commit | Annotated tag | Archive verification |
|---|---|---|---|
| Meta, 4 November | `d074b160d7af890ce7d8d99c2f580c597684a95c` | `meta-submitted-2026-11-04` | 107/107 archived files match Git; 106/106 manifest payload hashes match |
| Flip, 7 November | `79fa75e10bf06ad6dd44acc3836e97ea71cd94f4` | `flip-submitted-2026-11-07` | ZIP comment names this commit; 129/129 archived files match Git |

No tags existed locally or remotely before this preparation. These two annotated tags were created locally at the verified commits and then published in the authorized atomic push; neither points at the later receipt closeout or maintained HEAD.

Meta archive SHA-256: `675c58efe37004833d99f051512dabe44209e8e89481303f9c9e469139732292`.

Flip source archive SHA-256: `37a07a3ddcdf5e42f08f2e02d25bfe7d57a189cbda48286e78a8e959c07c082d`. All nine Flip receipt-manifest payloads and all ten receipt ZIP members match their retained files.

The original ten execution-contract files remain byte-identical to Meta. Contract SHA-256: `f7329ae57d934c5a0399755c0d1d7e7e6f42c86975b6067d5fa43a4ed0bbd1dd`. `PUBLIC_SOURCE_MANIFEST.json` remains the **historical Meta manifest**, not an inventory of the extended current tree. Original archive/receipt artifacts and unredacted verification records remain preserved privately and in unchanged submission history. Current-tree `FLIP_BASELINE_VERIFICATION.json` and `FLIP_VERIFICATION.json` are explicitly marked public redacted summaries; historical hashes identify the original evidence, not those edited summaries.

## Submitted links and freeze scope

Meta actually submitted `https://github.com/elouahid/intent-replay`, a mutable default-branch URL. Publishing maintained `main` changed the version displayed at that original link. The README prominently links Meta's immutable submitted commit and names its submission tag.

Flip actually submitted `https://github.com/elouahid/intent-replay/tree/flip-qa-room`. **Keep that remote branch at `79fa75e`.** The recorded closeout instructions explicitly preserved the remote checkpoints and kept later receipt documentation local. Those are project safeguards; the inspected saved organizer confirmation does not establish a permanent organizer rule freezing every branch. The user's later instruction authorizes preparing maintained `main`, with the original source preserved by commit, tag, archive and checkout. It does not require moving the submitted Flip branch.

The older documentation statements that `main` remains at Meta and receipt closeout stays local describe the November 7 state. Their dated maintenance notes explain the new branch purpose without changing the submission fields or historical proof.

## Local worktrees and runtime

- Maintained `main`: a separate development worktree, named `intent-replay-main` in the original installation.
- Meta submitted checkout: the original shared-repository worktree, detached at `d074b16`, with submitted files unchanged. It still holds the common Git metadata; retain it. Use `git worktree list` to find its local location.
- Existing Flip worktree: the preserved `intent-replay-flip` deployment, local branch `flip-qa-room` at `c58d563` at promotion. Its private configuration, retained runs, human-review records and submitted receipt remain in place.

Main's former auto-loaded `.codex/config.toml` pointed to the historical Flip worktree and installed Switch interpreter. Maintained main instead provides `docs/QA_ROOM_CODEX.example.toml` with placeholder paths and ignores the local configured copy. Configure it explicitly for this checkout before managed dispatch. The preserved Flip configuration and installed agent are unchanged; there is no live deployment migration as part of this source promotion.

## Verification

The bounded checks ran **once** in a new isolated Python 3.13 environment, including the optional pinned MCP SDK 1.28.1. Application source was unchanged from `c58d563`; the subsequent maintenance edits are documentation and configuration-template changes.

| Check | Result |
|---|---|
| Full Python discovery, including MCP SDK integration | 151 passed, zero skipped, exit 0 |
| Existing UI verification | 58 passed, exit 0 |
| One saved-regression invocation covering all six prepared inputs | 6/6 cases and 12/12 frozen branch expectations match, exit 0 |
| Actual retained-demo and isolated QA-listener startup | 7/7 read-only HTTP checks pass; both owned processes stopped and ports released |

The six-case regression separately records nine execution PASS and three expected execution FAIL outcomes. All twelve factual assessments remain INCONCLUSIVE; overall-task outcomes are three FAIL and nine INCONCLUSIVE. The synthetic QA store retained zero runs, reviews, completions or events. Startup made no dispatch/POST request, and the retained demo's generation control stayed disabled. No real room command, approval or completion was sent; existing services and environments were not modified.

Local audit material is in `.local/main-promotion-20261115/`: `submission-preservation.json` (archive, tag and contract checks), `checks-summary.json` (exact commands and installed versions), `verification-summary.json` (consolidated results), and `startup/startup-smoke-summary.json` (HTTP evidence and cleanup). Consolidated verification SHA-256: `15d9f56eb9659cf0b98df2060e7f5f874e1d7b6bf4b09a6e54706f79f0bf7dc3`. Runtime output and private historical evidence stay ignored by Git.

Saved replay makes no new model request. Regression matching, execution PASS/FAIL, factual uncertainty and human review remain separate. The intentionally faulty withdrawal is an expected execution FAIL; factual accuracy remains INCONCLUSIVE/unassessed. Automated test reviewers are simulated. The retained actual B/C walkthrough remains historical evidence, not a fresh integration test of the maintained checkout.

## Completed remote update

The authorized publication included **only** maintained `main` and the two submission tags together. The equivalent command from the maintained repository root was:

```powershell
git push --atomic origin main:main refs/tags/meta-submitted-2026-11-04:refs/tags/meta-submitted-2026-11-04 refs/tags/flip-submitted-2026-11-07:refs/tags/flip-submitted-2026-11-07
```

Post-push verification confirmed `main` at `fa5ef91159d2783813caf2043dd57542afbcfc94`, both annotated tags peeling to their exact submitted commits, and the unchanged remote Flip branch. No Flip branch ref was included. This is a completed publication record, not a request to repeat the push. Future maintenance must preserve the submitted branch and tags without forcing or replacing them.
