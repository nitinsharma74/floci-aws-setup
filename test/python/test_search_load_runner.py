"""Verify the load runner never requests pagination."""

import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit


path = Path(__file__).resolve().parents[2] / 'scripts/opensearch-service/load_test.py'
spec = importlib.util.spec_from_file_location('search_load', path)
load = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load)


class RunnerTests(unittest.TestCase):
    def test_all_workers_disable_pagination(self):
        class Reply(io.BytesIO):
            status = 200

        def reply(*args, **kwargs):
            return Reply(b'{"total":100,"movies":[],"nextCursor":null}')

        output = io.StringIO()
        with patch.object(load, 'urlopen', side_effect=reply) as request, \
                patch('sys.argv', ['load', '12', '--workers', '3', '--url',
                                   'http://localhost/execute-api/example/$default/movies/search']), \
                patch('sys.stdout', output):
            self.assertEqual(load.main(), 0)
        self.assertEqual(request.call_count, 12)
        for call in request.call_args_list:
            query = parse_qs(urlsplit(call.args[0]).query)
            self.assertEqual(query['paginate'], ['false'])
            self.assertNotIn('cursor', query)
        summary = json.loads(output.getvalue().split('\n', 2)[2])
        self.assertEqual(summary['successful'], 12)
        self.assertFalse(summary['paginate'])

    def test_missing_api_id_fails_before_requests(self):
        with patch('sys.argv', ['load', '100', '--url',
                               'http://localhost/execute-api/None/$default/movies/search']), \
                patch('sys.stderr', io.StringIO()), patch.object(load, 'urlopen') as request:
            with self.assertRaises(SystemExit) as raised:
                load.main()
            self.assertEqual(raised.exception.code, 2)
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
