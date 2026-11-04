# Focused submission verification

Checked on 4 November 2026 in the existing Windows Python environment. No provider requests were made by these checks. A fresh online dependency installation was not repeated.

- 57 focused Python tests passed, including native-request handling, saved history and exact regression-command bindings.
- 58 mocked browser-UI checks passed. These supplement the actual browser rehearsal; they are not browser automation or live-provider tests.
- All six offered commands ran successfully: the four original Meta/Baseten prepared cases and the two corrected Meta prepared cases. All 12 branch expectations matched.
- Both corrected retained-capture HTTP replays returned a command bound to the selected prepared hash. Generation is disabled in retained mode.

## Does an unexpected action fail the regression?

Yes. The corrected Meta capture was used for two separate offline process checks:

| Check | Actual result |
| --- | --- |
| Included withdrawal and control, unchanged workers and expectations | `SUITE PASS`, 2/2 cases, process exit **0** |
| Verification harness deliberately routes the guarded worker through the existing faulty implementation | `SUITE FAIL`, 0/1 case, process exit **1** |

The negative check performed actual local SQLite execution. It did not edit observations or change the frozen expectations. The withdrawal prepared file's SHA-256 remained `46dbc6d94b17fbf08e4d4b2eaf4fa516a7cba56e78f49af27d425fd04c91d033` before and after. This is controlled verification of the runner's failure behavior, not a discovered production defect.

The negative harness is in `source/scripts/verify_saved_regression.py`; its verification seams are not options on the production regression runner. The full production command is in the README. Execution assessments, factual uncertainty and overall-task verdicts remain unchanged.

## What changed for this public distribution?

Two presentation files now recognize the exact corrected-capture prepared files when offering a reusable command. Both the server and browser still require the selected artifact/hash and one of the exact bundled command paths. No evaluator, booking transaction, provider configuration or language semantics changed.

The execution-contract hash remains `f7329ae57d934c5a0399755c0d1d7e7e6f42c86975b6067d5fa43a4ed0bbd1dd`. `.gitattributes` disables automatic line-ending conversion because this contract hashes original file bytes.

The successful Meta request and the preceding failed request are retained separately. The video shows the actual retained successful proposal; the generation click was not successfully filmed. The included backend is local SQLite, not an externally verified booking service.
