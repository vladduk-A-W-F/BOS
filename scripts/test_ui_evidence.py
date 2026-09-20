"""Synthetic artifact controls only: no browser, server or business suite."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

from scripts import check_ui, verify


class UIEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bos-ui-evidence-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'ui-report.json'
        self.source = 'a' * 64
        screenshots = [f'viewport-{w}{s}.png' for w in (390, 768, 1440) for s in ('', '-dialog')]
        screenshots += ['native-zoom-200.png', 'native-zoom-200-dialog.png', 'network-failure.png',
                        'network-recovered.png', 'uah-preview.png', 'uah-confirmed.png']
        self.detail = {'schema': 'bos.gate10.local.v1', 'gate': 10, 'complete': True,
                       'source_sha256': self.source, 'source_unchanged': True, 'source_databases_unchanged': True,
                       'cleanup': dict.fromkeys(('browser_closed', 'server_stopped', 'runtime_removed'), True),
                       'isolation': {'server_process': {'actual_server_exit_verified': True, 'launcher_exit_verified': True,
                                                        'ownership_verified_before_application': True}},
                       'checks': [{'id': name, 'passed': True} for name in check_ui.CHECKS],
                       'artifacts': [], 'screenshots': screenshots}
        for name in screenshots:
            content = b'\x89PNG\r\n\x1a\n' + name.encode()
            (self.root / name).write_bytes(content)
            self.detail['artifacts'].append({'path': name, 'bytes': len(content),
                                             'sha256': hashlib.sha256(content).hexdigest()})

    def write(self):
        self.path.write_text(json.dumps(self.detail), encoding='utf-8')
        self.summary = {'gate': 10, 'report': str(self.path), 'report_sha256': check_ui.digest(self.path),
                        'complete': self.detail['complete'], 'source_sha256': self.source}

    def evidence(self, returncode=0):
        return verify.ui_evidence(json.dumps(self.summary), self.path, self.source, returncode)

    def test_complete_report_and_retained_artifacts(self):
        self.write()
        self.assertTrue(self.evidence()['complete'])

    def test_incomplete_failed_source_changed_or_unclean_never_passes(self):
        for target, key in [(self.detail, 'complete'), (self.detail, 'source_unchanged'),
                            (self.detail, 'source_databases_unchanged')]:
            with self.subTest(key=key):
                target[key] = False
                self.write()
                self.assertFalse(self.evidence()['complete'])
                target[key] = True
        for key in self.detail['cleanup']:
            with self.subTest(cleanup=key):
                self.detail['cleanup'][key] = False
                self.write()
                self.assertFalse(self.evidence()['complete'])
                self.detail['cleanup'][key] = True
        self.write()
        self.assertFalse(self.evidence(returncode=1)['complete'])

    def test_source_summary_path_and_digest_must_match(self):
        for key, value in [('source_sha256', 'b' * 64), ('report', str(self.root / 'wrong.json')),
                           ('report_sha256', '0' * 64), ('complete', False)]:
            with self.subTest(key=key):
                self.write()
                self.summary[key] = value
                self.assertFalse(self.evidence()['complete'])
        self.detail['source_sha256'] = 'b' * 64
        self.write()
        self.assertFalse(self.evidence()['complete'])

    def test_missing_duplicate_or_failed_matrix_check_refused(self):
        self.detail['checks'].pop()
        self.write()
        self.assertFalse(self.evidence()['complete'])
        self.detail['checks'].append(self.detail['checks'][0].copy())
        self.write()
        self.assertFalse(self.evidence()['complete'])
        self.detail['checks'] = [{'id': name, 'passed': name != 'native_zoom_200'} for name in check_ui.CHECKS]
        self.write()
        self.assertFalse(self.evidence()['complete'])

    def test_changed_and_missing_screenshot_refused(self):
        self.write()
        image = self.root / 'uah-preview.png'
        image.write_bytes(b'changed')
        self.assertFalse(self.evidence()['complete'])
        image.unlink()
        self.assertFalse(self.evidence()['complete'])

    def test_unindexed_screenshot_and_artifact_escape_refused(self):
        self.detail['artifacts'].pop()
        self.write()
        self.assertFalse(self.evidence()['complete'])
        for value in ('../outside.png', str(self.root.parent / 'outside.png'), 'ui-report.json'):
            with self.subTest(path=value):
                self.detail['artifacts'][0]['path'] = value
                self.write()
                self.assertFalse(self.evidence()['complete'])

    def test_malformed_missing_or_multiple_reports_refused(self):
        self.write()
        self.assertFalse(verify.ui_evidence('', self.path, self.source, 0)['complete'])
        text = json.dumps(self.summary)
        self.assertFalse(verify.ui_evidence(text + '\n' + text, self.path, self.source, 0)['complete'])
        self.path.write_text('not json', encoding='utf-8')
        self.assertFalse(self.evidence()['complete'])
        self.path.unlink()
        self.assertFalse(self.evidence()['complete'])

    def test_gate10_output_contract_and_zero_exit_requires_valid_report(self):
        source = self.root / 'work/source/scripts'
        source.mkdir(parents=True)
        (source / 'check_ui.py').write_text('# fixture only', encoding='utf-8')
        @contextmanager
        def environment(*args):
            yield {}
        for valid in (True, False):
            with self.subTest(valid=valid), mock.patch.object(verify, 'database', environment), \
                    mock.patch.object(verify, 'source_digest', return_value=self.source), \
                    mock.patch.object(verify, 'execute', return_value=(subprocess.CompletedProcess([], 0, '', ''), {'returncode': 0})) as execute, \
                    mock.patch.object(verify, 'ui_evidence', return_value={'complete': valid}) as evidence:
                result = verify.extension(10, 'sqlite', self.root / 'work', self.root)
                self.assertEqual(result['status'], verify.PASS if valid else verify.FAIL)
                report = self.root / 'ui/ui-report.json'
                self.assertEqual(execute.call_args.args[0][-2:], ['--output', str(report)])
                self.assertEqual(evidence.call_args.args[1:], (report, self.source, 0))

    def test_read_only_oracle_closes_connection(self):
        path = self.root / 'owned.sqlite3'
        connection = sqlite3.connect(path)
        connection.executescript('''CREATE TABLE erp_salesorder(id INTEGER,code TEXT,currency TEXT,branch_id INTEGER);
            CREATE TABLE erp_event(id INTEGER); CREATE TABLE erp_salesline(order_id INTEGER,quantity NUMERIC,price NUMERIC);''')
        connection.close()
        original_connect = sqlite3.connect
        connections = []
        def tracked(*args, **kwargs):
            value = original_connect(*args, **kwargs)
            connections.append(value)
            return value
        with mock.patch.object(check_ui.sqlite3, 'connect', side_effect=tracked):
            self.assertEqual(check_ui.order_facts(path, 'no-record'),
                             {'orders': 0, 'events': 0, 'matches': [], 'lines': []})
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute('SELECT 1')
        path.unlink()

    def test_native_chrome_focus_is_followed_by_modal_return(self):
        check_ui.validate_modal_focus([
            {'inside': True, 'tag': 'BUTTON', 'document_has_focus': True},
            {'inside': False, 'tag': 'BODY', 'document_has_focus': False},
            {'inside': True, 'tag': 'INPUT', 'document_has_focus': True}])

    def test_missing_or_ambiguous_select_never_reads_empty_descendants(self):
        for count in (0, 2):
            with self.subTest(count=count):
                locator = mock.Mock()
                locator.count.return_value = count
                with self.assertRaises(AssertionError):
                    check_ui.choose_named_option(locator, 'Київ')
                locator.locator.assert_not_called()
                locator.select_option.assert_not_called()

    def test_child_handshake_rejects_stale_nonce_or_invalid_pid(self):
        for value in (None, {}, {'pid': 123, 'nonce': 'old'}, {'pid': True, 'nonce': 'new'},
                      {'pid': '123', 'nonce': 'new'}, {'pid': 0, 'nonce': 'new'}):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                check_ui.validate_server_identity(value, 'new')
        self.assertEqual(check_ui.validate_server_identity({'pid': 123, 'nonce': 'new',
            'created_ticks': 123 if check_ui.process_owner.IS_WINDOWS else None,
            'image': check_ui.process_owner.expected_child_image()}, 'new'), 123)

    def test_report_requires_actual_child_and_launcher_exit_proofs(self):
        for key in ('actual_server_exit_verified', 'launcher_exit_verified', 'ownership_verified_before_application'):
            with self.subTest(key=key):
                self.detail['isolation']['server_process'][key] = False
                self.write()
                self.assertFalse(self.evidence()['complete'])
                self.detail['isolation']['server_process'][key] = True
        self.detail.pop('isolation')
        self.write()
        self.assertFalse(self.evidence()['complete'])

    def test_windows_launcher_exit_does_not_prove_actual_server_exit(self):
        server = object.__new__(check_ui.OwnedServer)
        server.handle = 123
        server.kernel = mock.Mock()
        server.kernel.WaitForSingleObject.side_effect = [258, 258]
        server.kernel.TerminateProcess.return_value = True
        server.launcher = mock.Mock()
        server.launcher.poll.return_value = 0
        server.pid = 456
        server.proof = {}
        self.assertFalse(server.stop())
        self.assertFalse(server.proof['actual_server_exit_verified'])
        self.assertTrue(server.proof['launcher_exit_verified'])
        server.kernel.TerminateProcess.assert_called_once_with(123, 0)
        server.kernel.CloseHandle.assert_called_once_with(123)

    def test_named_record_selection_never_falls_back_to_first_option(self):
        locator = mock.Mock()
        locator.count.return_value = 1
        choices = [{'value': '1', 'text': 'ДемоПром'}, {'value': '2', 'text': 'Київ · навчальна філія'}]
        locator.locator.return_value.evaluate_all.return_value = choices
        self.assertEqual(check_ui.choose_named_option(locator, 'Київ'), choices[1])
        locator.select_option.assert_called_once_with('2')
        locator.reset_mock()
        locator.count.return_value = 1
        locator.locator.return_value.evaluate_all.return_value = choices[:1]
        with self.assertRaises(AssertionError):
            check_ui.choose_named_option(locator, 'Київ')
        locator.select_option.assert_not_called()

    def test_outside_page_focus_or_missing_return_is_refused(self):
        inside = {'inside': True, 'tag': 'INPUT', 'document_has_focus': True}
        for outside in ({'inside': False, 'tag': 'BODY', 'document_has_focus': True},
                        {'inside': False, 'tag': 'BUTTON', 'document_has_focus': True},
                        {'inside': False, 'tag': 'BUTTON', 'document_has_focus': False}):
            with self.subTest(outside=outside), self.assertRaises(AssertionError):
                check_ui.validate_modal_focus([inside, outside, inside])
        with self.assertRaises(AssertionError):
            check_ui.validate_modal_focus([inside, {'inside': False, 'tag': 'BODY', 'document_has_focus': False}])

    def test_verifier_closes_owned_sentinel_without_app_execution(self):
        original_connect = sqlite3.connect
        connections = []
        def tracked(*args, **kwargs):
            value = original_connect(*args, **kwargs)
            connections.append(value)
            return value
        report = self.root / 'verify.json'
        with mock.patch.object(verify, 'ROOT', self.root), \
                mock.patch.object(verify, 'source_digest', return_value=self.source), \
                mock.patch.object(verify, 'extension', return_value=verify.outcome(verify.PASS)), \
                mock.patch.object(verify.sqlite3, 'connect', side_effect=tracked), \
                mock.patch.object(sys, 'argv', ['verify', '--suite', 'ui', '--output', str(report)]):
            self.assertEqual(verify.main(), 0)
        self.assertEqual(len(connections), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute('SELECT 1')


if __name__ == '__main__':
    unittest.main()
