/* Read-only presentation of existing local booking evidence; no new verdicts. */
'use strict';
(function expose(root) {
  const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const integer = value => Number.isSafeInteger(value) && value > 0;
  const text = value => typeof value === 'string' && value.trim().length > 0;
  const timestamp = value => text(value) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(value);
  class EvidenceUnavailable extends Error {}
  const require = (condition, reason) => { if (!condition) throw new EvidenceUnavailable(reason); };
  const same = (first, second, fields) => fields.every(field => first[field] === second[field]);
  const single = (items, reason) => { require(items.length === 1, reason); return items[0]; };
  const bookingFields = ['reference', 'service', 'starts_at', 'timezone'];
  const actionFields = ['action_id', 'booking_reference', 'operation', 'target_time', 'accepted_revision'];
  const acceptedFields = ['revision', 'operation', 'target_time', 'booking_reference', 'timezone', 'turn_id', 'interpretation_id'];

  function read(branch) {
    try {
      require(record(branch) && branch.status === 'executed' && branch.proposal_binding === 'PASS'
        && Array.isArray(branch.execution_errors) && branch.execution_errors.length === 0,
      'The executed branch and proposal binding are incomplete.');
      const evidence = branch.final_evidence;
      require(record(evidence) && Array.isArray(evidence.actions) && Array.isArray(branch.action_assessments),
        'The recorded action or its existing assessment is missing.');
      const action = single(evidence.actions, 'Exactly one recorded action is needed for this compact view.');
      const assessment = single(branch.action_assessments, 'Exactly one existing action assessment is needed.');
      require(record(action) && record(assessment) && text(action.action_id) && action.action_id === assessment.action_id
        && ['committed', 'suppressed', 'rejected'].includes(action.status)
        && integer(action.accepted_revision) && integer(action.checked_revision) && integer(action.decision_sequence)
        && assessment.accepted_revision === action.accepted_revision
        && assessment.current_revision_at_decision === action.checked_revision
        && assessment.decision_sequence === action.decision_sequence
        && typeof assessment.authorized_at_decision === 'boolean' && typeof assessment.atomic_evidence === 'boolean'
        && ['PASS', 'FAIL'].includes(assessment.status) && assessment.status === branch.execution_result,
      'Action identity, revisions or existing assessment bindings are incomplete or inconsistent.');
      require(record(branch.evaluation) && branch.evaluation.instruction_adherence === assessment.status
        && Array.isArray(branch.evaluation.checks), 'The existing execution assessment is inconsistent.');
      const acceptedCheck = single(branch.evaluation.checks.filter(item => record(item) && item.name === 'Accepted instruction evidence'),
        'The existing accepted-instruction check is missing or ambiguous.');
      require(acceptedCheck.status === 'PASS', 'Accepted instruction evidence was not established by the existing assessment.');

      const journal = evidence.journal;
      require(Array.isArray(journal) && journal.length > 0, 'The recorded journal is missing.');
      let previous = 0;
      for (const event of journal) {
        require(record(event) && integer(event.sequence) && event.sequence > previous && text(event.event)
          && record(event.data) && text(event.transaction_id), 'Journal order, event data or transaction references are incomplete or ambiguous.');
        previous = event.sequence;
      }
      const accepted = evidence.accepted_instructions;
      const acceptanceEvents = journal.filter(event => event.event === 'instruction_accepted');
      require(Array.isArray(accepted) && accepted.length > 0 && accepted.length === acceptanceEvents.length,
        'Accepted rows and their journal events do not have a complete binding.');
      const boundAccepted = [];
      let previousRevision = 0, previousAcceptance = 0;
      for (const row of accepted) {
        require(record(row) && integer(row.revision) && row.revision > previousRevision
          && ['reschedule', 'withdraw_pending'].includes(row.operation) && timestamp(row.target_time)
          && acceptedFields.filter(field => !['revision', 'target_time'].includes(field)).every(field => text(row[field]))
          && Array.isArray(row.evidence_turn_ids) && row.evidence_turn_ids.length > 0 && row.evidence_turn_ids.every(text),
        'The accepted instruction rows are incomplete or ambiguous.');
        const event = single(acceptanceEvents.filter(item => item.data.revision === row.revision),
          'An accepted revision has no unique journal reference.');
        require(event.sequence > previousAcceptance && same(row, event.data, acceptedFields)
          && Array.isArray(event.data.evidence_turn_ids) && event.data.evidence_turn_ids.length === row.evidence_turn_ids.length
          && row.evidence_turn_ids.every((value, index) => value === event.data.evidence_turn_ids[index]),
        'An accepted instruction disagrees with its journal reference.');
        boundAccepted.push({row, event});
        previousRevision = row.revision; previousAcceptance = event.sequence;
      }
      const current = boundAccepted[boundAccepted.length - 1];
      require(current.row.revision === assessment.current_revision_at_decision,
        'This compact view requires the decision revision to remain the final accepted revision.');
      const original = single(boundAccepted.filter(item => item.row.revision === action.accepted_revision),
        'The queued action has no unique originating accepted revision.');

      const queued = single(journal.filter(event => event.event === 'action_queued' && event.data.action_id === action.action_id),
        'The action has no unique queued-event reference.');
      const check = single(journal.filter(event => event.event === 'authorization_checked' && event.data.action_id === action.action_id),
        'The action has no unique authorization-check reference.');
      const terminalEvents = journal.filter(event => ['action_committed', 'action_suppressed', 'action_rejected'].includes(event.event)
        && event.data.action_id === action.action_id);
      const terminal = single(terminalEvents, 'The action has no unique terminal-event reference.');
      require(terminal.sequence === action.decision_sequence && terminal.event === 'action_' + action.status
        && original.event.sequence < queued.sequence && queued.sequence < check.sequence && check.sequence < terminal.sequence
        && current.event.sequence < check.sequence && original.row.operation === 'reschedule'
        && action.operation === 'reschedule' && action.booking_reference === original.row.booking_reference
        && action.target_time === original.row.target_time && same(action, queued.data, actionFields)
        && same(action, terminal.data, actionFields), 'Queued, accepted, checked and terminal event bindings do not agree.');
      require(check.data.accepted_revision === action.accepted_revision
        && check.data.checked_revision === action.checked_revision
        && terminal.data.checked_revision === action.checked_revision
        && check.data.authorized === assessment.authorized_at_decision
        && terminal.data.authorized === assessment.authorized_at_decision,
      'The recorded authorization check disagrees with the existing action assessment.');
      const sameTransaction = check.transaction_id === terminal.transaction_id && check.sequence + 1 === terminal.sequence;
      require(!assessment.atomic_evidence || sameTransaction,
        'The existing atomic-evidence claim disagrees with its transaction references.');

      const booking = evidence.booking, after = terminal.data.after, before = terminal.data.before, initial = branch.initial_booking;
      require(record(booking) && record(after) && record(before) && record(initial)
        && bookingFields.every(field => text(booking[field]) && text(after[field]) && text(before[field]) && text(initial[field]))
        && timestamp(booking.starts_at) && timestamp(after.starts_at)
        && same(booking, after, bookingFields) && same(booking, initial, ['reference', 'service', 'timezone'])
        && same(before, initial, ['reference', 'service', 'timezone'])
        && booking.reference === action.booking_reference && booking.reference === current.row.booking_reference
        && booking.timezone === original.row.timezone && booking.timezone === current.row.timezone
        && evidence.read_source === 'independent read-only SQLite transaction'
        && integer(evidence.read_after_sequence) && evidence.read_after_sequence === previous,
      'The independent readback is missing or disagrees with the terminal booking snapshot.');

      // Values are copied literally. This view neither determines a verdict nor
      // invents a timestamp/event for the separate read-only SQLite snapshot.
      return {
        available: true,
        accepted: {sequence: current.event.sequence, revision: current.row.revision, operation: current.row.operation, target_time: current.row.target_time},
        check: {sequence: check.sequence, accepted_revision: check.data.accepted_revision, checked_revision: check.data.checked_revision,
          authorized: check.data.authorized, transaction_id: check.transaction_id},
        action: {sequence: terminal.sequence, status: action.status, transaction_id: terminal.transaction_id},
        read: {read_after_sequence: evidence.read_after_sequence, starts_at: booking.starts_at, source: evidence.read_source},
        check_and_action_same_transaction: assessment.atomic_evidence === true && sameTransaction
      };
    } catch (error) {
      // Never expose arbitrary input exceptions or fall back to a canned story.
      return {available: false, reason: error instanceof EvidenceUnavailable ? error.message : 'Required decisive-step evidence is unavailable.'};
    }
  }

  root.DecisionEvidence = Object.freeze({read});
})(globalThis);
