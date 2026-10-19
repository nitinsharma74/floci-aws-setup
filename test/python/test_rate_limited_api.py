"""Behavior tests with a locked state store and controlled time (no AWS calls)."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from botocore.exceptions import ClientError, EndpointConnectionError

SOURCE = Path(__file__).resolve().parents[2] / 'stacks/rate-limited-api-stack/lambda/response/response_handler.py'
spec = importlib.util.spec_from_file_location('response_handler', SOURCE)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def failure(code='ConditionalCheckFailedException'):
    return ClientError({'Error': {'Code': code, 'Message': code}}, 'WriteItem')


class StateTable:
    def __init__(self):
        self.items = {}
        self.lock = threading.Lock()
        self.read_barrier = None
        self.conflicts = 0

    def update_item(self, **kwargs):
        with self.lock:
            key = kwargs['Key']['pk']
            item = self.items.get(key, {'count': 0})
            values = kwargs['ExpressionAttributeValues']
            if item['count'] >= values[':limit']:
                raise failure()
            self.items[key] = {'count': item['count'] + 1, 'expiresAt': values[':expiry']}

    def get_item(self, **kwargs):
        assert kwargs['ConsistentRead'] is True
        with self.lock:
            item = copy.deepcopy(self.items.get(kwargs['Key']['pk']))
        # Force simultaneous initial misses to exercise conditional-write losers.
        if item is None and self.read_barrier is not None:
            self.read_barrier.wait(timeout=5)
        return {'Item': item} if item else {}

    def put_item(self, **kwargs):
        with self.lock:
            item = kwargs['Item']
            old = self.items.get(item['pk'])
            if old and old['expiresAt'] > kwargs['ExpressionAttributeValues'][':now']:
                self.conflicts += 1
                raise failure()
            self.items[item['pk']] = copy.deepcopy(item)


class RateLimitedApiTests(unittest.TestCase):
    def setUp(self):
        self.table = StateTable()
        self.now = 6000
        self.env = patch.dict(os.environ, RATE_LIMIT='10', CACHE_TTL_SECONDS='3600')
        self.clock = patch.object(api.time, 'time', side_effect=lambda: self.now)
        self.store = patch.object(api, 'get_table', return_value=self.table)
        for patcher in (self.env, self.clock, self.store):
            patcher.start()
            self.addCleanup(patcher.stop)

    def event(self, user='alice', query=None):
        return {'headers': {'X-User-Id': user}, 'httpMethod': 'GET',
                'path': '/response', 'multiValueQueryStringParameters': query}

    def call(self, user='alice', query=None):
        return api.handler(self.event(user, query), None)

    def test_missing_or_blank_user_does_not_touch_storage(self):
        for event in ({}, {'headers': {}}, self.event('  ')):
            self.assertEqual(api.handler(event, None)['statusCode'], 400)
        api.get_table.assert_not_called()

    def test_cached_body_and_expiry_do_not_change_on_hit(self):
        first = self.call()
        self.now += 59
        self.assertEqual(self.call()['body'], first['body'])
        item = next(value for key, value in self.table.items.items() if key.startswith('CACHE#'))
        self.assertEqual(item['expiresAt'], 9600)
        self.assertEqual(set(json.loads(first['body'])), {'userId', 'responseId', 'generatedAt'})

    def test_expired_item_is_replaced_without_waiting_for_ttl_cleanup(self):
        first = self.call()
        self.now = 9599
        self.assertEqual(self.call()['body'], first['body'])
        self.now = 9600
        self.assertNotEqual(self.call()['body'], first['body'])

    def test_user_and_query_isolation_and_canonicalization(self):
        first = self.call(query={'a': ['2', '1'], 'b': ['x']})
        self.assertEqual(self.call(query={'b': ['x'], 'a': ['1', '2']})['body'], first['body'])
        self.assertNotEqual(self.call('bob', {'a': ['2', '1'], 'b': ['x']})['body'], first['body'])
        self.assertNotEqual(self.call(query={'a': ['1']})['body'], first['body'])
        event = self.event()
        event['queryStringParameters'] = {'a': '1'}
        self.assertEqual(api.cache_key(event, 'alice'), api.cache_key(self.event(query={'a': ['1']}), 'alice'))
        event['path'] = '/another'
        self.assertNotEqual(api.cache_key(event, 'alice'), api.cache_key(self.event(), 'alice'))

    def test_cache_hits_count_and_minute_rollover_resets_limit(self):
        responses = [self.call() for _ in range(10)]
        self.assertEqual({item['statusCode'] for item in responses}, {200})
        self.assertEqual(len({item['body'] for item in responses}), 1)
        limited = self.call()
        self.assertEqual(limited['statusCode'], 429)
        self.assertEqual(limited['headers']['Retry-After'], '60')
        self.assertEqual(self.call('bob')['statusCode'], 200)
        self.now = 6059
        self.assertEqual(self.call()['headers']['Retry-After'], '1')
        self.now = 6060
        self.assertEqual(self.call()['body'], responses[0]['body'])

    def test_concurrent_misses_return_the_winner(self):
        self.table.read_barrier = threading.Barrier(8)
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: self.call(), range(8)))
        self.assertEqual({item['statusCode'] for item in responses}, {200})
        self.assertEqual(len({item['body'] for item in responses}), 1)
        self.assertEqual(self.table.conflicts, 7)

    def test_concurrent_requests_admit_only_ten(self):
        with ThreadPoolExecutor(max_workers=20) as pool:
            responses = list(pool.map(lambda _: self.call(), range(20)))
        self.assertEqual(sum(item['statusCode'] == 200 for item in responses), 10)
        self.assertEqual(sum(item['statusCode'] == 429 for item in responses), 10)

    def test_storage_failures_return_503(self):
        for method in ('update_item', 'get_item', 'put_item'):
            with self.subTest(method=method), patch.object(self.table, method, side_effect=failure('InternalServerError')):
                self.assertEqual(self.call()['statusCode'], 503)
        with patch.object(api, 'get_table', side_effect=EndpointConnectionError(endpoint_url='http://unavailable')):
            self.assertEqual(self.call()['statusCode'], 503)

    def test_disappearing_cache_winner_returns_503(self):
        with patch.object(self.table, 'put_item', side_effect=failure()):
            self.assertEqual(self.call()['statusCode'], 503)


if __name__ == '__main__':
    unittest.main()
