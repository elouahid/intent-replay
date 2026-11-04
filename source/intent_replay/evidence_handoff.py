"""Inert, read-only handoff of an existing local booking execution report.

No execution, interpretation, inference or verdict generation occurs here. The
existing artifact validators and regression assessment retain their meanings.
"""
import argparse
import hashlib
from html import escape
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import zipfile

from intent_replay.benchmark_cases import PROFILE, check_seal, digest
from intent_replay.benchmark_execution import validate_prepared
from intent_replay.regression import FIELDS, assess


MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_HTML_BYTES = 64 * 1024 * 1024
BUNDLE_NAMES = ("report.html", "report.json", "prepared.json", "README.md", "manifest.json")
CSP = ("default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
       "img-src 'none'; font-src 'none'; connect-src 'none'; object-src 'none'; "
       "base-uri 'none'; form-action 'none'")
_MISSING = object()


def _transport_json(value):
    """Use the existing JSONResponse byte encoding, not original file layout."""
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
        raise ValueError("Evidence must be finite, UTF-8 JSON: " + type(exc).__name__) from None


def _validated(report):
    if not isinstance(report, dict):
        raise ValueError("Execution report must be a JSON object.")
    encoded = _transport_json(report)
    if len(encoded) > MAX_REPORT_BYTES:
        raise ValueError("Execution report exceeds the 8 MB handoff bound.")
    # Work on a private JSON snapshot. Caller objects and source files are never
    # changed, even if a validator internally constructs mutable objects.
    try:
        data = json.loads(encoded)
    except (ValueError, RecursionError) as exc:
        raise ValueError("Evidence cannot be read as bounded JSON: " + type(exc).__name__) from None
    try:
        check_seal(data)
        if (data.get("schema_version") != 7
                or data.get("report_type") != "proposal_execution_comparison"
                or data.get("profile") != PROFILE
                or not isinstance(data.get("execution_id"), str)
                or re.fullmatch(r"[a-f0-9]{32}", data["execution_id"]) is None
                or not isinstance(data.get("runtime"), dict)
                or data["runtime"].get("location") != "local"
                or type(data["runtime"].get("model_requests")) is not int
                or data["runtime"]["model_requests"] != 0):
            raise ValueError("Only schema-7, zero-inference local booking reports are supported.")
        prepared = data["prepared"]
        validate_prepared(prepared)
        if data.get("experiment_id") != prepared["experiment_id"]:
            raise ValueError("Report experiment identity does not match its prepared artifact.")
        revalidation = data.get("revalidation")
        if (not isinstance(revalidation, dict)
                or revalidation.get("original_prepared_sha256") != prepared["sha256"]):
            raise ValueError("Report revalidation does not bind to this prepared artifact.")
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        raise ValueError("Evidence cannot be exported: " + str(exc)[:400]) from None
    try:
        branches = assess(data, prepared)
        status = "PASS" if all(branch["matches"] for branch in branches) else "FAIL"
        error = None
    except Exception as exc:
        # A sealed report may retain a real execution/observation failure. Keep
        # that evidence and show ERROR, never promote its stored PASS labels.
        branches, status = [], "ERROR"
        error = type(exc).__name__ + ": " + str(exc)[:300]
    return data, encoded, branches, status, error


def _get(value, *keys):
    for key in keys:
        if isinstance(key, int) and isinstance(value, list) and 0 <= key < len(value):
            value = value[key]
        elif isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return _MISSING
    return value


def _plain(value):
    if value is _MISSING:
        return "NOT AVAILABLE"
    if value is None:
        return "null (recorded)"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _text(value):
    return escape(_plain(value), quote=True)


def _ref(pointer):
    return '<code class="ref">report.json#' + escape(pointer, quote=True) + '</code>'


def _detail(label, value, pointer):
    return ('<div class="fact"><dt>' + escape(label) + '</dt><dd>' + _text(value)
            + '</dd><dd>' + _ref(pointer) + '</dd></div>')


def _json_detail(title, value, pointer):
    return ('<details><summary>' + escape(title) + '</summary>' + _ref(pointer)
            + '<pre>' + _text(value) + '</pre></details>')


def _render(data, checks, status, error):
    prepared = data["prepared"]
    case, capture = prepared["case"], prepared["capture"]
    checks_by_name = {row["implementation"]: row for row in checks}
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="' + escape(CSP, quote=True) + '">',
             '<title>Intent Replay — local execution evidence</title><style>',
             "*{box-sizing:border-box}body{margin:0;background:#f6f6f0;color:#173b37;font:16px/1.55 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:32px 24px}h1{font-size:2.2rem;line-height:1.15;margin:.2em 0}h2{margin:1.7em 0 .6em}h3{margin:.2em 0 .7em}p{max-width:90ch}a{color:inherit}code,pre{font:13px/1.5 ui-monospace,monospace;overflow-wrap:anywhere}pre{white-space:pre-wrap;max-height:32rem;overflow:auto;background:#f7f8f7;padding:16px;border:1px solid #dce2dd;border-radius:8px}.eyebrow{font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;font-weight:750}.lead{font-size:1.1rem}.notice{padding:16px 20px;background:#fff9e8;border-left:4px solid #b78115;border-radius:6px}.status{display:inline-block;padding:4px 10px;border-radius:5px;background:#e7eeec;font-weight:750}.status.PASS{color:#155b42;background:#e0f0e8}.status.FAIL{color:#852a32;background:#f9e6e6}.status.ERROR{color:#754e00;background:#fff0cc}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.card{background:white;border:1px solid #d7dfda;border-radius:12px;padding:22px}.fact{margin:12px 0}dt{font-weight:650}dd{margin:2px 0;overflow-wrap:anywhere}.ref{color:#586864;font-size:.73rem}.scope{color:#4b6059;font-size:.9rem}.outcome{font-size:1.25rem;font-weight:650}table{width:100%;border-collapse:collapse;margin:14px 0;font-size:.88rem}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #dce3df;padding:9px 6px;overflow-wrap:anywhere}th{font-weight:650}details{margin:14px 0}summary{cursor:pointer;font-weight:650}ol{padding-left:24px}li{margin:12px 0}.journal-data{margin:5px 0}.journal-data pre{max-height:18rem}.binding{border-top:1px solid #ccd7cf;margin-top:26px;padding-top:16px;overflow-wrap:anywhere}@media(max-width:760px){.cards{grid-template-columns:1fr}main{padding:22px 16px}h1{font-size:1.8rem}}@media print{body{background:white}main{max-width:none;padding:0}details{break-inside:avoid}.cards{display:block}.card{margin-bottom:16px;break-inside:avoid}pre{max-height:none;overflow:visible}}",
             '</style></head><body><main><header><p class="eyebrow">Intent Replay · offline evidence handoff</p>',
             '<h1>What reached the booking store?</h1>',
             '<p class="lead">An existing recorded model proposal, its local execution evidence, and the frozen regression check.</p>',
             '<p><span class="status ' + status + '">Regression ' + status + '</span> ',
             'Included local SQLite booking backend · no new execution or model request during export.</p>',
             '<p class="scope">Report ' + _text(data['execution_id']) + ' · execution recorded ' + _text(data.get('created_at')),
             ' · proposal captured ' + _text(prepared['capture'].get('created_at')) + '.</p></header>',
             '<p class="scope">Unredacted evidence: review before sharing. The included demonstration cases are fictional; ',
             'this exporter is not an anonymizer. Hashes establish consistency, not provider authenticity or third-party booking proof.</p>']
    if error:
        parts += ['<p class="notice"><strong>Regression check incomplete.</strong> ' + _text(error),
                  ' Stored branch assessments below are recorded labels only, not verified PASS results. ',
                  'The original JSON remains available; no missing observation was invented.</p>']
    else:
        count = sum(row["matches"] for row in checks)
        parts += ['<p>' + str(count) + '/2 branches match their frozen expectations. ',
                  'An expected faulty execution FAIL can match a passing regression. ',
                  'A regression match does not establish successful action, factual accuracy or overall task success.</p>']
    initial = case['initial_booking']
    booking_label = ' · '.join(str(initial[key]) for key in ('reference', 'service', 'starts_at', 'timezone'))
    target_label = capture['target']['provider'] + ' · ' + capture['target']['model']
    proposal_label = str(_get(capture, 'proposal', 'native_call', 'name')) + ' → ' + str(_get(capture, 'proposal', 'arguments', 'requested_time'))
    parts += ['<section><h2>Request and recorded proposal</h2>',
              '<p class="scope">' + _text(booking_label) + '</p>',
              '<p><strong>Customer request:</strong> ' + _text(case['request']) + '<br>',
              '<strong>Customer revision:</strong> ' + (_text(case['withdrawal']) if case.get('withdrawal') else 'No withdrawal recorded; the original request remains.') + '</p>',
              '<p><strong>Recorded proposal:</strong> ' + _text(proposal_label) + '<br>',
              '<span class="scope">' + _text(target_label) + ' · requested slot available: ' + _text(case['slot_available']) + '</span></p>',
              '<details><summary>Request and proposal evidence references</summary><dl>',
              _detail('Case', case['case_id'], '/prepared/case/case_id'),
              _detail('Initial booking', booking_label, '/prepared/case/initial_booking'),
              _detail('Customer request', case['request'], '/prepared/case/request'),
              _detail('Customer revision / withdrawal', case.get('withdrawal'), '/prepared/case/withdrawal'),
              _detail('Slot availability', case['slot_available'], '/prepared/case/slot_available'),
              _detail('Provider / model', target_label, '/prepared/capture/target'),
              _detail('Proposed operation', _get(capture, 'proposal', 'native_call', 'name'), '/prepared/capture/proposal/native_call/name'),
              _detail('Proposed time', _get(capture, 'proposal', 'arguments', 'requested_time'), '/prepared/capture/proposal/arguments/requested_time'),
              '</dl></details></section>',
              '<section><h2>Observed execution and frozen expectations</h2><div class="cards">']
    branches = data.get('reports')
    if not isinstance(branches, list) or not branches:
        parts.append('<p class="notice">Branch evidence NOT AVAILABLE. No execution assessment is verified.</p>')
        branches = []
    for index, branch in enumerate(branches):
        pointer = '/reports/' + str(index)
        name = _get(branch, 'implementation')
        title = {'faulty': 'Fault-injected worker', 'corrected': 'Guarded worker'}.get(name, 'Recorded branch ' + str(index + 1)) if isinstance(name, str) else 'Recorded branch ' + str(index + 1)
        check = checks_by_name.get(name) if isinstance(name, str) else None
        evidence = _get(branch, 'final_evidence')
        actions = _get(evidence, 'actions')
        action_status = _get(actions, 0, 'status') if isinstance(actions, list) and len(actions) == 1 else _MISSING
        journal = _get(evidence, 'journal')
        decisions = [(i, row) for i, row in enumerate(journal) if _get(row, 'event') in ('action_committed', 'action_suppressed', 'action_rejected')] if isinstance(journal, list) else []
        decision_index, decision = decisions[-1] if decisions else (None, {})
        decision_pointer = pointer + '/final_evidence/journal/' + str(decision_index) + '/data/reason' if decision_index is not None else pointer + '/final_evidence/journal'
        factual = _get(branch, 'factual_accuracy')
        factual_label = _plain(_get(factual, 'status')) + ' · assessed: ' + _plain(_get(factual, 'assessed'))
        parts += ['<article class="card"><h3>' + title + '</h3>']
        if check is not None:
            parts.append('<p class="status ' + ('PASS' if check['matches'] else 'FAIL') + '">' + ('MATCH' if check['matches'] else 'MISMATCH') + ' — regression expectation</p>')
        else:
            parts.append('<p class="status ERROR">NOT VERIFIED — incomplete regression check</p>')
        parts += ['<p class="outcome">Recorded final time: ' + _text(_get(evidence, 'booking', 'starts_at')) + '</p>',
                  _ref(pointer + '/final_evidence/booking/starts_at'), '<dl>',
                  _detail('Recorded action', action_status, pointer + '/final_evidence/actions/0/status'),
                  _detail('Recorded decision reason', _get(decision, 'data', 'reason'), decision_pointer),
                  _detail('Recorded execution assessment' + (' — not verified' if error else ''), _get(branch, 'execution_result'), pointer + '/execution_result'),
                  _detail('Factual accuracy (separate)', factual_label, pointer + '/factual_accuracy'),
                  _detail('Recorded overall task' + (' — not verified' if error else ''), _get(branch, 'evaluation', 'task_verdict'), pointer + '/evaluation/task_verdict'),
                  '</dl><p class="scope">Read source: ' + _text(_get(evidence, 'read_source')) + '; after journal sequence ' + _text(_get(evidence, 'read_after_sequence')) + '.</p>']
        expected = prepared['case']['private_expectations'].get(name, {}) if isinstance(name, str) else {}
        observed = check['observed'] if check is not None else {
            'final_time': _get(evidence, 'booking', 'starts_at'),
            'action_status': _get(evidence, 'actions', 0, 'status'),
            'booking_outcome': _get(branch, 'evaluation', 'booking_outcome'),
            'instruction_adherence': _get(branch, 'execution_result'),
        }
        pointers = {
            'final_time': pointer + '/final_evidence/booking/starts_at',
            'action_status': pointer + '/final_evidence/actions/0/status',
            'booking_outcome': pointer + '/evaluation/booking_outcome',
            'instruction_adherence': pointer + '/execution_result',
        }
        parts += ['<table><thead><tr><th scope="col">Field</th><th scope="col">Frozen expected</th>',
                  '<th scope="col">Observed' + (' (recorded only)' if error else '') + '</th></tr></thead><tbody>']
        for field in FIELDS:
            parts += ['<tr><th scope="row">' + field.replace('_', ' ') + '</th><td>' + _text(expected.get(field, _MISSING)),
                      '</td><td>' + _text(observed.get(field, _MISSING)) + '</td></tr>']
        parts += ['</tbody></table><details><summary>Frozen field and readback evidence references</summary><dl>']
        for field in FIELDS:
            parts += [_detail('Expected ' + field, expected.get(field, _MISSING), '/prepared/case/private_expectations/' + str(name) + '/' + field),
                      _detail('Observed ' + field, observed.get(field, _MISSING), pointers[field])]
        parts += [_detail('Read source', _get(evidence, 'read_source'), pointer + '/final_evidence/read_source'),
                  _detail('Read after sequence', _get(evidence, 'read_after_sequence'), pointer + '/final_evidence/read_after_sequence'),
                  '</dl></details>',
                  _json_detail('Complete recorded actions', actions, pointer + '/final_evidence/actions'),
                  _json_detail('Recorded attribution and factual status', {'attribution': _get(branch, 'attribution') if _get(branch, 'attribution') is not _MISSING else 'NOT AVAILABLE', 'factual_accuracy': factual if factual is not _MISSING else 'NOT AVAILABLE'}, pointer),
                  _json_detail('Accepted revisions', _get(evidence, 'accepted_instructions'), pointer + '/final_evidence/accepted_instructions'),
                  _json_detail('Recorded evaluator checks', _get(branch, 'evaluation'), pointer + '/evaluation'),
                  '<details><summary>Execution journal and exact references</summary>']
        if isinstance(journal, list) and journal:
            parts.append('<ol>')
            for journal_index, row in enumerate(journal):
                jp = pointer + '/final_evidence/journal/' + str(journal_index)
                parts += ['<li><strong>#' + _text(_get(row, 'sequence')) + ' ' + _text(_get(row, 'event')) + '</strong><br>',
                          _ref(jp), '<p>Transaction: ' + _text(_get(row, 'transaction_id')) + '</p>',
                          '<div class="journal-data"><pre>' + _text(_get(row, 'data')) + '</pre></div></li>']
            parts.append('</ol>')
        else:
            parts.append('<p>Journal NOT AVAILABLE.</p>')
        parts += ['</details></article>']
    timing_note = ('The proposal was captured before withdrawal. The fault is injected in the worker; '
                   'a stale commit is not evidence that the model ignored an undelivered instruction.'
                   if case.get('withdrawal') else
                   'This no-withdrawal control keeps the original request in force. '
                   'An authorized commit is the expected local action; no withdrawal was delivered.')
    parts += ['</div><p class="scope">' + timing_note + ' ',
              'Both workers share one proposal and are not independent model trials.</p></section>',
              '<section><h2>Provenance and retained records</h2>',
              '<p>Native proposal call: ' + _text(_get(capture, 'proposal', 'native_call', 'call_id')),
              ' · originating revision: ' + _text(_get(capture, 'proposal', 'originating_revision')) + '.<br>',
              _ref('/prepared/capture/proposal/native_call/call_id') + '<br>' + _ref('/prepared/capture/proposal/originating_revision') + '</p>',
              _json_detail('Full native proposal and original arguments', capture.get('proposal'), '/prepared/capture/proposal'),
              _json_detail('Recorded provider configuration', capture.get('target'), '/prepared/capture/target'),
              _json_detail('Recorded capture source', capture.get('source'), '/prepared/capture/source'),
              _json_detail('Recorded native responses and tool events', {'responses': capture.get('responses'), 'events': capture.get('events')}, '/prepared/capture'),
              _json_detail('Recorded model request usage (not new charges)', capture.get('requests'), '/prepared/capture/requests'),
              _json_detail('Saved customer interpretation', prepared.get('freeze'), '/prepared/freeze'),
              _json_detail('Report revalidation record', data.get('revalidation'), '/revalidation'),
              '<p class="scope">Native records are retained, not regenerated. Factual accuracy is unassessed in this proposal-only profile. ',
              'Execution PASS does not imply overall task PASS. This brief does not verify arbitrary external agents, ',
              'voice systems, production services or a receiving business\'s saved booking.</p></section>',
              '<section><h2>Open and reuse this evidence</h2>',
              '<p>Keep all five bundle files together. <code>report.json</code> is the full recorded execution; ',
              '<code>prepared.json</code> contains its replay inputs and original model capture. ',
              '<code>manifest.json</code> records exact file hashes and canonical object bindings. ',
              'JSON files use the application download encoding; original source-file whitespace is not claimed to be retained.</p>',
              '<p>To run a new local regression, use the application package and follow <code>README.md</code>. ',
              'Choose the extracted <code>prepared.json</code> path manually. This offline HTML does not run any command.</p>',
              '</section><footer class="binding"><dl>',
              _detail('Execution ID', data['execution_id'], '/execution_id'),
              _detail('Execution created at (recorded)', data.get('created_at'), '/created_at'),
              _detail('Report seal SHA-256', data['sha256'], '/sha256'),
              _detail('Prepared seal SHA-256', prepared['sha256'], '/prepared/sha256'),
              '</dl><p class="scope">Export is a presentation of existing evidence, not a new experiment. ',
              'Do not add original inference usage across replays; the same model captures are reused.</p></footer>',
              '</main></body></html>']
    html = ''.join(parts)
    if len(html.encode('utf-8')) > MAX_HTML_BYTES:
        raise ValueError('Rendered report exceeds the bounded HTML size.')
    return html


def render_report(report):
    """Return an inert offline view; reject invalid input, retain check ERROR."""
    data, _, checks, status, error = _validated(report)
    return _render(data, checks, status, error)


def build_bundle(report):
    """Return a deterministic ZIP; no file, ledger, provider or execution writes."""
    data, report_bytes, checks, status, error = _validated(report)
    prepared = data['prepared']
    files = {
        'report.html': _render(data, checks, status, error).encode('utf-8'),
        'report.json': report_bytes,
        'prepared.json': _transport_json(prepared),
        'README.md': ('''# Intent Replay offline evidence bundle

Open `report.html` in a browser. It is self-contained: no server, API key, JavaScript or external assets are needed. Opening or exporting it does not execute a booking action or invoke a model.

This bundle contains unredacted evidence. Review it before sharing. The included demonstration cases are fictional; the exporter does not anonymize other evidence. It covers the included local SQLite booking backend and makes no claim about arbitrary external agents or production systems.

`report.json` is the existing full execution report. `prepared.json` is the exact prepared object in that report. Their UTF-8 JSON encoding matches the application's JSON downloads; source-file whitespace is not preserved. `manifest.json` hashes each other file and records the report/prepared bindings. Hashes establish consistency, not provider authenticity or independently certified truth.

## Reuse the saved case

1. Obtain the matching Intent Replay application package and install its documented Python requirements.
2. Open PowerShell in that application's `source` directory and activate its Python environment (or use its explicit Python executable).
3. Manually extract this bundle into the application's `source/review-bundle` directory. The example below assumes that destination and the `.venv` environment created by the application's clean-start instructions. If you chose a different destination or environment, substitute those paths yourself. The exporter does not choose or execute them.

```powershell
.\\.venv\\Scripts\\python.exe -B .\\scripts\\run_saved_regression.py --prepared .\\review-bundle\\prepared.json
```

The command creates a new local replay and saves new reports; it does not authenticate or replace the exported record. Exit 0 means required frozen expectations matched, 1 means an observed mismatch, and 2 means invalid/incomplete evidence or an execution/assessment error. A deliberately faulty branch's expected execution FAIL can match a passing regression; the guarded branch must also match. Frozen expectations are not updated.

Factual accuracy is unassessed/INCONCLUSIVE. Overall remains FAIL for faulty withdrawal and INCONCLUSIVE for the guarded/control branches in the included demonstrations. No provider or Modal request is needed. The HTML itself never launches this command.
''').encode('utf-8'),
    }
    manifest = {
        'schema_version': 'local-booking-evidence-bundle-v1',
        'execution_id': data['execution_id'], 'experiment_id': data['experiment_id'],
        'case_id': prepared['case']['case_id'],
        'provider': prepared['capture']['target']['provider'],
        'regression_status': status, 'equivalent_regression_exit_code': {'PASS': 0, 'FAIL': 1, 'ERROR': 2}[status],
        'regression_error': error,
        'report_seal_sha256': data['sha256'], 'prepared_seal_sha256': prepared['sha256'],
        'report_canonical_sha256': digest(data), 'prepared_canonical_sha256': digest(prepared),
        'canonical_hash_note': 'Canonical hashes cover the whole JSON object, including its existing sha256 seal. Seal hashes exclude their own sha256 field.',
        'files': {name: {'sha256': hashlib.sha256(value).hexdigest(), 'bytes': len(value)} for name, value in files.items()},
        'manifest_hash_note': 'The manifest does not hash itself. File hashes cover the exact exported bytes.',
        'json_encoding': 'UTF-8, ensure_ascii=False, allow_nan=False, separators=(comma,colon); original file whitespace is not preserved.',
        'export_new_model_requests': 0, 'export_new_executions': 0,
        'contains_unredacted_evidence': True,
        'scope': 'Included local SQLite booking backend only. Recorded model proposal, injected worker defect and separate factual/overall uncertainty remain visible.',
    }
    files['manifest.json'] = json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
    result = BytesIO()
    with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in BUNDLE_NAMES:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
    return result.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, help='Existing sealed local execution report JSON; no replay occurs.')
    parser.add_argument('--output', type=Path, required=True, help='New ZIP path. Existing files are never overwritten.')
    args = parser.parse_args(argv)
    try:
        if args.report.stat().st_size > MAX_REPORT_BYTES:
            raise ValueError('Input report exceeds the 8 MB handoff bound.')
        with args.report.open('rb') as stream:
            raw = stream.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError('Input report exceeds the 8 MB handoff bound.')
        report = json.loads(raw.decode('utf-8'))
        bundle = build_bundle(report)
        with zipfile.ZipFile(BytesIO(bundle)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as stream:
            stream.write(bundle)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        print('EVIDENCE EXPORT ERROR: ' + type(exc).__name__ + ': ' + str(exc)[:400], file=sys.stderr)
        return 2
    print('Evidence bundle saved: ' + str(args.output.resolve()))
    print('Regression check of retained evidence: ' + manifest['regression_status']
          + ' (equivalent regression exit ' + str(manifest['equivalent_regression_exit_code']) + ').')
    print('Export exit 0 means only that the bundle was written; use run_saved_regression.py for regression status.')
    print('Open report.html after extraction. Existing evidence only; 0 new executions; 0 model requests.')
    print('Contains unredacted evidence. Review before sharing; hashes are consistency checks, not authenticity.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
