"""Focused offline boundaries for the read-only evidence handoff exporter."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.responses import JSONResponse

from intent_replay.benchmark_cases import digest, seal
from intent_replay.benchmark_execution import execute_prepared
from intent_replay.evidence_handoff import BUNDLE_NAMES, MAX_REPORT_BYTES, build_bundle, main, render_report
from intent_replay.temporal import RevisionStore

ROOT = Path(__file__).resolve().parents[1]


class HTMLAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs = []
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append((tag, dict(attrs)))


class EvidenceHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = {name: ROOT / 'fresh_case_evidence/executions' / (name + '.json')
                     for name in ('fresh-withdrawal-meta', 'fresh-control-meta',
                                  'fresh-withdrawal-baseten', 'fresh-control-baseten')}
        cls.originals = {name: path.read_bytes() for name, path in cls.paths.items()}
        cls.reports = {name: json.loads(raw) for name, raw in cls.originals.items()}

    def setUp(self):
        self.blockers = ExitStack()
        self.addCleanup(self.blockers.close)
        for name in ('httpx.HTTPTransport.handle_request', 'httpx.AsyncHTTPTransport.handle_async_request',
                     'socket.create_connection', 'intent_replay.meta_client.create_client',
                     'intent_replay.benchmark_targets.OpenAI'):
            self.blockers.enter_context(patch(name, side_effect=AssertionError('External operation forbidden')))

    def report(self, name='fresh-withdrawal-meta'):
        return deepcopy(self.reports[name])

    def unpack(self, value):
        raw = build_bundle(value)
        with zipfile.ZipFile(BytesIO(raw)) as z:
            self.assertEqual(z.namelist(), list(BUNDLE_NAMES))
            self.assertIsNone(z.testzip())
            return {name: z.read(name) for name in z.namelist()}

    def test_four_saved_cases_preserve_json_bytes_bindings_and_expectations(self):
        for name in self.paths:
            with self.subTest(name=name):
                report = self.report(name)
                before = digest(report)
                parts = self.unpack(report)
                manifest = json.loads(parts['manifest.json'])
                self.assertEqual(parts['report.json'], JSONResponse(report).body)
                self.assertEqual(parts['prepared.json'], JSONResponse(report['prepared']).body)
                self.assertEqual(manifest['regression_status'], 'PASS')
                self.assertEqual(manifest['equivalent_regression_exit_code'], 0)
                self.assertEqual(manifest['report_canonical_sha256'], digest(report))
                self.assertEqual(manifest['prepared_canonical_sha256'], digest(report['prepared']))
                self.assertEqual(manifest['report_seal_sha256'], report['sha256'])
                self.assertEqual(manifest['prepared_seal_sha256'], report['prepared']['sha256'])
                self.assertEqual(manifest['export_new_executions'], 0)
                self.assertEqual(manifest['export_new_model_requests'], 0)
                self.assertTrue(manifest['contains_unredacted_evidence'])
                html = parts['report.html'].decode('utf-8')
                if report['prepared']['case'].get('withdrawal'):
                    self.assertIn('The proposal was captured before withdrawal.', html)
                    self.assertNotIn('This no-withdrawal control keeps the original request in force.', html)
                else:
                    self.assertIn('This no-withdrawal control keeps the original request in force.', html)
                    self.assertNotIn('The proposal was captured before withdrawal.', html)
                for filename, record in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(parts[filename]).hexdigest(), record['sha256'])
                    self.assertEqual(len(parts[filename]), record['bytes'])
                self.assertEqual(set(manifest['files']), set(BUNDLE_NAMES) - {'manifest.json'})
                self.assertEqual(digest(report), before)
                self.assertEqual(self.paths[name].read_bytes(), self.originals[name])

    def test_export_is_deterministic_and_never_replays(self):
        report = self.report()
        with patch('intent_replay.benchmark_execution.execute_prepared', side_effect=AssertionError('Replay forbidden')):
            self.assertEqual(build_bundle(report), build_bundle(report))

    def test_expected_faulty_execution_failure_remains_passing_regression(self):
        parts = self.unpack(self.report())
        html = parts['report.html'].decode()
        self.assertIn('Regression PASS', html)
        self.assertIn('An expected faulty execution FAIL can match a passing regression.', html)
        self.assertIn('report.json#/reports/0/execution_result', html)
        self.assertIn('report.json#/reports/1/final_evidence/booking/starts_at', html)
        self.assertIn('report.json#/reports/0/final_evidence/journal/8', html)
        self.assertIn('Factual accuracy (separate)', html)
        self.assertIn('Recorded overall task', html)
        self.assertIn('not evidence that the model ignored', html)

    def test_actual_unexpected_guarded_commit_exports_mismatch_without_changing_expectations(self):
        prepared = self.report()['prepared']
        before = digest(prepared)
        original_execute = RevisionStore.execute
        def unexpected(store, implementation, **kwargs):
            return original_execute(store, 'faulty' if implementation == 'corrected' else implementation, **kwargs)
        with patch.object(RevisionStore, 'execute', new=unexpected):
            report = execute_prepared(prepared)
        parts = self.unpack(report)
        manifest = json.loads(parts['manifest.json'])
        self.assertEqual(manifest['regression_status'], 'FAIL')
        self.assertEqual(manifest['equivalent_regression_exit_code'], 1)
        self.assertIn('1/2 branches match', parts['report.html'].decode())
        self.assertIn('MISMATCH', parts['report.html'].decode())
        self.assertEqual(report['reports'][1]['final_evidence']['booking']['starts_at'], prepared['case']['requested_time'])
        self.assertEqual(report['reports'][1]['private_expectation_comparison']['expected'], prepared['case']['private_expectations']['corrected'])
        self.assertEqual(digest(prepared), before)

    def test_missing_observations_export_error_without_verified_pass_badges(self):
        report = self.report()
        del report['reports'][1]['final_evidence']['booking']['starts_at']
        parts = self.unpack(seal(report))
        manifest = json.loads(parts['manifest.json'])
        self.assertEqual(manifest['regression_status'], 'ERROR')
        self.assertEqual(manifest['equivalent_regression_exit_code'], 2)
        html = parts['report.html'].decode()
        self.assertIn('NOT AVAILABLE', html)
        self.assertIn('NOT VERIFIED', html)
        self.assertIn('Stored branch assessments below are recorded labels only', html)
        self.assertNotIn('class="status PASS"', html)
        self.assertEqual(json.loads(parts['report.json']), seal(report))

    def test_assessment_exception_is_visible_and_escaped(self):
        with patch('intent_replay.evidence_handoff.assess', side_effect=ValueError('<script>alert(1)</script>')):
            parts = self.unpack(self.report())
        html = parts['report.html'].decode()
        self.assertIn('Regression ERROR', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('class="status PASS"', html)

    def test_untrusted_text_is_inert_in_all_rendered_locations(self):
        attack = '</pre><img src="https://example.invalid/pixel" onerror="alert(1)"><script>alert(2)</script>&\"'
        report = self.report()
        report['reports'][0]['attribution'] = attack
        report['reports'][0]['final_evidence']['journal'][0]['data']['untrusted_note'] = attack
        report['created_at'] = attack
        html = render_report(seal(report))
        self.assertIn('&lt;img', html)
        self.assertIn('&lt;script&gt;', html)
        audit = HTMLAudit(); audit.feed(html)
        self.assertFalse(set(audit.tags) & {'script', 'img', 'iframe', 'object', 'embed', 'form', 'base', 'link'})
        self.assertFalse(any(name.startswith('on') for _, attrs in audit.attrs for name in attrs))
        for _, attrs in audit.attrs:
            for key in ('href', 'src', 'action'):
                self.assertNotIn(key, attrs)
        csp = [attrs['content'] for tag, attrs in audit.attrs if tag == 'meta' and attrs.get('http-equiv') == 'Content-Security-Policy']
        self.assertEqual(len(csp), 1)
        self.assertIn("default-src 'none'", csp[0])
        self.assertIn("script-src 'none'", csp[0])
        self.assertIn("form-action 'none'", csp[0])

    def test_invalid_report_seal_is_rejected(self):
        report = self.report(); report['reports'][0]['execution_result'] = 'PASS'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            build_bundle(report)

    def test_prepared_validation_cannot_be_bypassed_by_resealing_report(self):
        report = self.report(); report['prepared']['case']['request'] += ' unsupported mutation'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            build_bundle(seal(report))

    def test_wrong_report_identity_profile_runtime_and_binding_are_rejected(self):
        mutations = [
            ('execution_id', lambda r: r.update(execution_id='../outside')),
            ('profile', lambda r: r.update(profile='other')),
            ('experiment', lambda r: r.update(experiment_id='wrong')),
            ('source', lambda r: r['runtime'].update(location='modal')),
            ('new-inference', lambda r: r['runtime'].update(model_requests=1)),
            ('revalidation', lambda r: r['revalidation'].update(original_prepared_sha256='wrong')),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                report = self.report(); mutate(report)
                with self.assertRaises(ValueError): build_bundle(seal(report))

    def test_nonfinite_and_oversized_json_are_rejected(self):
        report = self.report(); report['extra'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'finite'): build_bundle(report)
        report = self.report(); report['extra'] = 'x' * MAX_REPORT_BYTES
        with self.assertRaisesRegex(ValueError, '8 MB'): build_bundle(report)

    def test_cli_exports_without_overwrite_or_input_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); source = parent / 'report.json'; output = parent / 'bundle.zip'
            source.write_bytes(self.originals['fresh-withdrawal-meta'])
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(main([str(source), '--output', str(output)]), 0)
                original_bundle = output.read_bytes()
                self.assertEqual(main([str(source), '--output', str(output)]), 2)
            self.assertEqual(output.read_bytes(), original_bundle)
            self.assertEqual(source.read_bytes(), self.originals['fresh-withdrawal-meta'])

    def test_cli_rejects_invalid_input_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); source = parent / 'invalid.json'; output = parent / 'bundle.zip'
            source.write_text('{invalid', encoding='utf-8')
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(main([str(source), '--output', str(output)]), 2)
            self.assertFalse(output.exists())

    def test_cli_error_brief_success_does_not_claim_passing_regression(self):
        report = self.report()
        del report['reports'][1]['final_evidence']['booking']['starts_at']
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); source = parent / 'report.json'; output = parent / 'bundle.zip'
            source.write_text(json.dumps(seal(report)), encoding='utf-8')
            text = StringIO()
            with redirect_stdout(text), redirect_stderr(StringIO()):
                self.assertEqual(main([str(source), '--output', str(output)]), 0)
            self.assertTrue(output.is_file())
            self.assertIn('Regression check of retained evidence: ERROR (equivalent regression exit 2)', text.getvalue())
            self.assertIn('Export exit 0 means only that the bundle was written', text.getvalue())
            self.assertNotIn('Regression PASS', text.getvalue())

    def test_cli_deeply_nested_json_fails_without_traceback_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); source = parent / 'nested.json'; output = parent / 'bundle.zip'
            source.write_text('[' * 2000 + '0' + ']' * 2000, encoding='utf-8')
            errors = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(errors):
                self.assertEqual(main([str(source), '--output', str(output)]), 2)
            self.assertIn('EVIDENCE EXPORT ERROR:', errors.getvalue())
            self.assertNotIn('Traceback', errors.getvalue())
            self.assertFalse(output.exists())

    def test_cli_parser_recursion_error_is_reported_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); source = parent / 'report.json'; output = parent / 'bundle.zip'
            source.write_bytes(self.originals['fresh-withdrawal-meta'])
            errors = StringIO()
            with patch('intent_replay.evidence_handoff.json.loads', side_effect=RecursionError('Controlled parser depth failure')), redirect_stdout(StringIO()), redirect_stderr(errors):
                self.assertEqual(main([str(source), '--output', str(output)]), 2)
            self.assertIn('RecursionError', errors.getvalue())
            self.assertNotIn('Traceback', errors.getvalue())
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
