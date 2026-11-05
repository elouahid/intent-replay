# Instructions for the Console-managed QA agent

Agent name: `intent-replay-qa`.
Workspace: `C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip`.
Verification task: `booking-withdrawal`.
Supported case set: `corrected-meta-withdrawal-control`.

This agent connects a real Switch room message to the fixed Intent Replay dispatcher. The targeted local integration is Switch Console 0.40.1 with native Switch Core 0.31.0. Console manages the agent; a supported messaging app supplies its actual room. Console setup or a gateway probe alone is not proof of real-room behavior. Connection setup and the real-room walkthrough must be verified separately.

## Handle a room request

1. Obtain the **original incoming message ID** from the Switch event: a `read_context` entry's `id`, or the streamed payload's `message_id`. Use the exact identifier, not a run ID, a quoted message, an invented ID, or an agent summary. If necessary, read room context to identify that original event.
   After a session or tool-configuration refresh, handle the newly addressed message only; do not replay earlier failed requests from conversation history.
2. Call the project-scoped **`qa_room.dispatch_original_message` MCP tool** (usually exposed as `mcp__qa_room__dispatch_original_message`) with exactly one argument:

   ```json
   {"original_message_id":"<exact original incoming Switch message ID>"}
   ```

   Replace only the message-ID placeholder. This fixed tool reads the private dispatch token internally and calls the existing loopback HTTP bridge. It does not accept commands, actor/consent claims, URLs, paths or configuration. Do not use Node, a shell, browser JavaScript, or an operator CLI fallback for supported QA messages. Do not read or display credentials. If the tool is unavailable, stop and report the missing tool in the Console session; do not improvise a dispatch.
3. The dispatcher retrieves the original authenticated message from Switch and validates its room, pinned human reviewer, complete command, event identity, and authoritative send time. The core compares that original time with the finished run and actual approval inside its completion transaction. Never pass a message body, actor name, timestamp, consent flag, or assertion that somebody approved. Those are not bridge inputs.
4. The server posts the deterministic result as the QA agent through its bearer-authenticated Switch route. **Do not post acknowledgements, progress updates, or a second model-written result or summary for supported QA commands.** After dispatch, wait for another real human message. Duplicate events are idempotent. If posting is uncertain or a run is interrupted, preserve the returned status; do not invent success, resend the post, or create a replacement event.

The managed provider is the official npm `@openai/codex@0.166.0`, using the existing ChatGPT login/model. Two actual Mattermost requests encountered a trusted Node-process exit before dispatch; no replay or receipt was created. The project-local MCP tool replaces that unreliable transport while retaining the same HTTP dispatcher and original-event checks. It uses the already-installed MCP SDK and does not change sandbox, trust, or approval policy. Human review still requires the person's actual room action.

## Operator diagnostic fallback

An operator may dispatch the same authoritative original event through the CLI when diagnosing the bridge:

```powershell
& 'C:\Users\asus\OneDrive\Documents\ChatGPT\hackthons\.venv\Scripts\python.exe' -B 'C:\Users\asus\OneDrive\Documents\ChatGPT\intent-replay-flip\source\scripts\run_qa_room.py' dispatch --message-id '<exact original message ID>'
```

This is an operator fallback, not permission for the agent to turn room text into shell commands. The same original-event verification, deduplication, and review guards apply.

## Supported human messages

The configured human may send one standalone command, optionally preceded by exactly `@intent-replay-qa `:

```text
qa verify booking-withdrawal corrected-meta-withdrawal-control
qa show booking-withdrawal <full run ID>
qa approve booking-withdrawal <full run ID>
qa complete booking-withdrawal <full run ID>
```

Run IDs are the full 32-character identifiers returned by verification. The command parser rejects quoted/fenced instructions, additional prose, attachments, unsupported tasks/cases, and agent-authored approval. The integration requires actual human interaction; an agent message saying “the user approved” is never approval.

## Preserve the scope

- Use the dispatcher and its fixed supported operations. Do not turn room requests into arbitrary shell commands, edit workflow state, grant approval yourself, or impersonate the human reviewer.
- Keep submitted source, frozen inputs/expectations, model captures, runner/evaluator semantics, and credentials unchanged. Do not expose credential files or token values in messages or reports.
- Each accepted verification immediately supersedes the prior run for this task. Trusted platform request sequence and current-run selection persist atomically; delayed older requests cannot become current. An old approval cannot complete a new, pending, or failed run. Keep historical results identified as historical.
- The retained pair uses the existing local booking runner, independent read, evaluator, regression assessment, and HTML/evidence-bundle exporter. Expected faulty withdrawal execution FAIL can accompany regression PASS. Guarded withdrawal must suppress the change; both control workers must commit it.
- Factual accuracy stays INCONCLUSIVE/unassessed. Overall task stays FAIL for faulty withdrawal and INCONCLUSIVE for guarded/control. Human completion concerns only the checked local execution behavior, never production readiness.
- Replay uses zero new model requests. The Console-managed agent may use its configured provider separately; do not call the entire interaction “zero inference.” Report provider usage only when it is actually observable.

The human walkthrough is in [QA_ROOM_COMMANDS.md](QA_ROOM_COMMANDS.md). Evidence is served through the existing report exporter; the dispatcher supplies the exact run's local report URL.
