"""Four finite regressions for normalized actual Caddy output.

CAPTURED_ACCESS is an actual Caddy 2.11.1 record from the verified synthetic
TLS run on 2026-09-12 (A09_PROXY_REVIEW_AFTER_ROUTE, 16 checks). Its core msg
survived Caddy's `msg delete`; normalization must remove it before storage.
"""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
import uuid

MODULE = None
CAPTURED_ACCESS = {
    'level': 'info', 'ts': 1789205941.398476,
    'logger': 'http.log.access.bos_https', 'msg': 'handled request',
    'bytes_read': 0, 'user_id': '', 'duration': 0.364671573,
    'size': 43, 'status': 200,
}
CANARY = 'BOS_PROXY_PRIVATE_CANARY_9e7ad4cb'
FIELDS = {'event', 'status', 'version', 'correlation_id'}


class ProxyLoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MODULE is None:
            from boss_project import proxy_logging
        else:
            spec = importlib.util.spec_from_file_location('synthetic_proxy_logging', MODULE)
            proxy_logging = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(proxy_logging)
        cls.module = proxy_logging

    def assert_record(self, record, event, status, version='0.2.9-dev'):
        self.assertEqual(set(record), FIELDS)
        self.assertEqual((record['event'], record['status'], record['version']),
                         (event, status, version))
        identifier = uuid.UUID(record['correlation_id'])
        self.assertEqual(identifier.version, 4)
        self.assertNotIn(CANARY, json.dumps(record))

    def test_actual_capture_and_unknown_private_fields_are_discarded(self):
        record = dict(CAPTURED_ACCESS, msg=CANARY, user_id=CANARY,
                      correlation_id=CANARY, unknown_private=CANARY,
                      error=CANARY, request={'uri': CANARY, 'body': CANARY,
                      'headers': {'Cookie': [CANARY], 'Authorization': [CANARY]}},
                      resp_headers={'Set-Cookie': [CANARY]}, stacktrace=CANARY)
        result = self.module.normalize_proxy_line(json.dumps(record), version='0.2.9-dev')
        self.assert_record(result, 'proxy_request', 200)

    def test_malformed_non_object_and_oversized_lines_are_generic(self):
        lines = [CANARY, '{"msg":"' + CANARY, json.dumps(CANARY), 'null', '[]',
                 '[' * 1100 + ']' * 1100,
                 CANARY * (self.module.MAX_LINE_CHARACTERS // len(CANARY) + 1)]
        for line in lines:
            with self.subTest(shape=len(line)):
                self.assert_record(self.module.normalize_proxy_line(line, version='0.2.9-dev'),
                                   'proxy_unstructured', None)

    def test_only_http_integer_status_and_controlled_version_survive(self):
        for status in [True, False, '200', 200.0, None, -1, 0, 99, 600, CANARY]:
            with self.subTest(status_type=type(status).__name__):
                result = self.module.normalize_proxy_line(json.dumps({'status': status, 'msg': CANARY}),
                                                         version=CANARY)
                self.assert_record(result, 'proxy_log', None, 'unknown')
        for status in [100, 200, 413, 599]:
            self.assert_record(self.module.normalize_proxy_line(json.dumps({'status': status}),
                               version='0.2.9-dev'), 'proxy_request', status)

    def test_writer_emits_only_normalized_json_with_fresh_ids(self):
        class Stream(io.StringIO):
            flushes = 0
            def flush(self):
                self.flushes += 1
                super().flush()
        stream = Stream()
        self.module.write_proxy_line(json.dumps(dict(CAPTURED_ACCESS, msg=CANARY)), stream,
                                     version='0.2.9-dev')
        self.module.write_proxy_line(CANARY, stream, version='0.2.9-dev')
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(stream.flushes, 2)
        first, second = map(json.loads, lines)
        self.assert_record(first, 'proxy_request', 200)
        self.assert_record(second, 'proxy_unstructured', None)
        self.assertNotEqual(first['correlation_id'], second['correlation_id'])
        self.assertNotIn(CANARY, stream.getvalue())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path)
    args, remaining = parser.parse_known_args()
    MODULE = args.module
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    unittest.main(argv=[sys.argv[0], *remaining])
