import base64
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode

from opensearchpy.exceptions import ConnectionError, ConnectionTimeout, TransportError

path = Path(__file__).resolve().parents[2] / 'stacks/opensearch-service-stack/lambda/opensearch_search_lambda/opensearch_search_lambda.py'
spec = importlib.util.spec_from_file_location('movie_search', path)
search = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search)


def result(ids, total=None, title=True, **extra):
    return {
        'timed_out': False, '_shards': {'failed': 0},
        'hits': {'total': {'value': total if total is not None else len(ids), 'relation': 'eq'},
                 'hits': [{'_source': {'movieId': i, 'title': f'Movie {i}', 'genres': ['Comedy'],
                                      'title_suggest': {'input': ['hidden']}},
                           'sort': [2.5, i] if title else [i]} for i in ids]}, **extra,
    }


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.create_pit.return_value = {'pit_id': 'snapshot', '_shards': {'failed': 0}}
        self.client.search.return_value = result([1])
        self.client_patch = patch.object(search, 'get_client', return_value=self.client)
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.logs = patch.object(search, 'logger')
        self.logs.start()
        self.addCleanup(self.logs.stop)

    def call(self, params=None, **event):
        response = search.handler({'queryStringParameters': params, **event}, Mock(aws_request_id='test'))
        self.assertEqual(response['headers']['Content-Type'], 'application/json')
        return response['statusCode'], json.loads(response['body'])

    def test_title_fuzzy_and_genre_filter(self):
        status, data = self.call({'q': ' toy stroy ', 'genre': ' Comedy '})
        self.assertEqual(status, 200)
        body = self.client.search.call_args.kwargs['body']
        self.assertEqual(body['query']['bool']['must'], [{'match': {'title': {
            'query': 'toy stroy', 'fuzziness': 'AUTO', 'operator': 'and'}}}])
        self.assertEqual(body['query']['bool']['filter'], [{'term': {'genres': 'Comedy'}}])
        self.assertEqual(body['sort'], [{'_score': 'desc'}, {'movieId': 'asc'}])
        self.assertEqual(data['query'], 'toy stroy')
        self.assertEqual(set(data['movies'][0]), {'movieId', 'title', 'genres'})
        self.assertIsNone(data['nextCursor'])
        self.client.delete_pit.assert_called_once()

    def test_genre_only_and_no_results(self):
        self.client.search.return_value = result([], title=False)
        status, data = self.call({'genre': 'Comedy'})
        self.assertEqual(status, 200)
        self.assertEqual(data, {'query': None, 'genre': 'Comedy', 'total': 0, 'movies': [], 'nextCursor': None})
        body = self.client.search.call_args.kwargs['body']
        self.assertEqual(body['sort'], [{'movieId': 'asc'}])
        self.assertEqual(body['query']['bool']['must'], [])
        self.client.delete_pit.assert_called_once()

    def test_invalid_parameters_do_not_contact_opensearch(self):
        for params in [None, {}, {'q': ' '}, {'q': 'x' * 201}, {'genre': 'x' * 101},
                       {'q': 'toy', 'limit': '0'}, {'q': 'toy', 'limit': '101'},
                       {'q': 'toy', 'limit': '1.5'}, {'q': 'toy', 'limit': '²'},
                       {'q': 'toy', 'limit': '-1'}, {'q': 'toy', 'cursor': ''},
                       {'q': 'toy', 'cursor': '!bad'}, {'q': 'toy', 'unknown': 'x'}, {'q': 1}]:
            with self.subTest(params=params):
                self.assertEqual(self.call(params)[0], 400)
        self.assertEqual(self.call({'q': 'toy,toy'}, rawQueryString='q=toy&q=toy')[0], 400)
        self.client.create_pit.assert_not_called()

    def test_pagination_continuity_and_cleanup(self):
        self.client.search.side_effect = [result([1, 2, 3], total=3), result([3], total=3)]
        status, first = self.call({'q': 'toy', 'limit': '2'})
        self.assertEqual(status, 200)
        self.assertEqual([m['movieId'] for m in first['movies']], [1, 2])
        self.client.delete_pit.assert_not_called()
        status, last = self.call({'q': 'toy', 'limit': '2', 'cursor': first['nextCursor']})
        self.assertEqual(status, 200)
        self.assertEqual(last['total'], 3)
        self.assertEqual([m['movieId'] for m in last['movies']], [3])
        self.assertIsNone(last['nextCursor'])
        self.assertEqual(self.client.search.call_args.kwargs['body']['search_after'], [2.5, 2])
        self.client.create_pit.assert_called_once()
        self.client.delete_pit.assert_called_once_with(body={'pit_id': ['snapshot']}, request_timeout=2)

    def test_exact_page_size_is_final(self):
        self.client.search.return_value = result([1, 2])
        self.assertIsNone(self.call({'q': 'toy', 'limit': '2'})[1]['nextCursor'])
        self.client.delete_pit.assert_called_once()

    def test_cursor_validation(self):
        params = {'q': 'toy', 'genre': None, 'limit': 20}
        cursor = search.encode_cursor('snapshot', [1.0, 1], params)
        self.assertEqual(self.call({'q': 'changed', 'cursor': cursor})[0], 400)
        self.assertEqual(self.call({'q': 'toy', 'limit': '10', 'cursor': cursor})[0], 400)
        for changes in [{'v': 2}, {'sort': [True, 1]}, {'sort': [float('nan'), 1]},
                        {'sort': [1]}, {'pit': ''}, {'params': []}]:
            data = {'v': 1, 'pit': 'snapshot', 'sort': [1.0, 1], 'params': params, **changes}
            bad = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
            self.assertEqual(self.call({'q': 'toy', 'cursor': bad})[0], 400)

    def test_partial_or_timed_out_results_are_errors(self):
        for extra, status in [({'timed_out': True}, 504), ({'_shards': {'failed': 1}}, 503)]:
            self.client.search.return_value = result([1], **extra)
            self.assertEqual(self.call({'q': 'toy'})[0], status)
        self.assertEqual(self.client.delete_pit.call_count, 2)

    def test_partial_snapshot_is_cleaned(self):
        self.client.create_pit.return_value['_shards']['failed'] = 1
        self.assertEqual(self.call({'q': 'toy'})[0], 503)
        self.client.search.assert_not_called()
        self.client.delete_pit.assert_called_once()

    def test_error_mapping(self):
        for error, status in [
            (ConnectionTimeout('TIMEOUT', 'private details'), 504),
            (ConnectionError('N/A', 'private details', OSError('connection refused')), 503),
            (TransportError(404, 'missing', {'error': {'type': 'index_not_found_exception'}}), 503),
            (RuntimeError('private details'), 500),
        ]:
            with self.subTest(error=error):
                self.client.search.side_effect = error
                actual, data = self.call({'q': 'toy'})
                self.assertEqual(actual, status)
                self.assertNotIn('private details', json.dumps(data))

    def test_expired_cursor_and_retryable_failure(self):
        cursor = search.encode_cursor('snapshot', [1.0, 1], {'q': 'toy', 'genre': None, 'limit': 20})
        self.client.search.side_effect = TransportError(404, 'missing', {
            'error': {'type': 'search_context_missing_exception'}})
        status, data = self.call({'q': 'toy', 'cursor': cursor})
        self.assertEqual(status, 410)
        self.assertEqual(data['error']['code'], 'CURSOR_EXPIRED')
        self.client.search.side_effect = ConnectionTimeout('TIMEOUT', 'timeout')
        self.assertEqual(self.call({'q': 'toy', 'cursor': cursor})[0], 504)
        self.client.delete_pit.assert_not_called()

    def test_cleanup_failure_does_not_hide_results(self):
        self.client.delete_pit.side_effect = RuntimeError('cleanup failed')
        self.assertEqual(self.call({'q': 'toy'})[0], 200)

    def test_sdk_serializes_boolean_url_parameters_for_opensearch(self):
        # Exercise the real SDK down to its HTTP boundary, without a network request.
        client = search.OpenSearch(hosts=[{'host': 'localhost', 'port': 9200}])
        self.addCleanup(client.close)
        replies = [
            {'pit_id': 'snapshot', '_shards': {'failed': 0}},
            result([1]), {'pits': [{'pit_id': 'snapshot', 'successful': True}]},
        ]
        connection = client.transport.get_connection()
        with patch.object(connection, 'perform_request', side_effect=[
            (200, {}, json.dumps(reply)) for reply in replies
        ]) as wire:
            data = search.search_movies(client, {'q': 'toy', 'genre': None, 'limit': 20}, None)
        self.assertEqual(data['total'], 1)
        queries = [parse_qs(urlencode(call.args[2])) for call in wire.call_args_list]
        self.assertEqual(queries[0]['allow_partial_pit_creation'], ['false'])
        self.assertEqual(queries[1]['allow_partial_search_results'], ['false'])
        self.assertEqual(wire.call_args_list[2].args[0], 'DELETE')


class ClientTests(unittest.TestCase):
    @patch.dict(os.environ, {'OPENSEARCH_DOMAIN': 'movies-search', 'AWS_REGION': 'us-east-1'})
    @patch.object(search, 'OpenSearch')
    @patch.object(search.boto3, 'client')
    def test_local_endpoint_and_cache(self, boto_client, constructor):
        search._client = None
        self.addCleanup(setattr, search, '_client', None)
        boto_client.return_value.describe_domain.return_value = {'DomainStatus': {'Endpoint': 'http://172.17.0.5:9200'}}
        self.assertIs(search.get_client(), search.get_client())
        constructor.assert_called_once()
        config = constructor.call_args.kwargs
        self.assertEqual(config['hosts'], [{'host': '172.17.0.5', 'port': 9200}])
        self.assertFalse(config['use_ssl'])
        self.assertNotIn('http_auth', config)
        self.assertEqual(config['max_retries'], 0)

    @patch.dict(os.environ, {'OPENSEARCH_DOMAIN': 'movies-search', 'AWS_REGION': 'us-east-1'})
    @patch.object(search, 'AWSV4SignerAuth')
    @patch.object(search.boto3, 'Session')
    @patch.object(search, 'OpenSearch')
    @patch.object(search.boto3, 'client')
    def test_aws_vpc_endpoint_is_signed_and_verified(self, boto_client, constructor, session, signer):
        search._client = None
        self.addCleanup(setattr, search, '_client', None)
        boto_client.return_value.describe_domain.return_value = {'DomainStatus': {
            'Endpoints': {'vpc': 'vpc-movies.us-east-1.es.amazonaws.com'}}}
        search.get_client()
        config = constructor.call_args.kwargs
        self.assertTrue(config['use_ssl'])
        self.assertTrue(config['verify_certs'])
        self.assertEqual(config['http_auth'], signer.return_value)
        signer.assert_called_once_with(session.return_value.get_credentials.return_value, 'us-east-1', 'es')


if __name__ == '__main__':
    unittest.main()
