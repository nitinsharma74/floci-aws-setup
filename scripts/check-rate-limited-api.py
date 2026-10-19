#!/usr/bin/env python3
"""Smoke-test a deployed demo API using only the Python standard library."""
import json
import sys
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(url, user=None):
    headers = {'X-User-Id': user} if user else {}
    try:
        result = urlopen(Request(url, headers=headers), timeout=30)
    except HTTPError as error:
        result = error
    with result:
        return result.code, result.headers, result.read().decode()


def main(url):
    user = f'smoke-{uuid.uuid4()}'
    assert call(url)[0] == 400, 'Missing identity should return 400'
    other = call(url, user + '-other')
    assert other[0] == 200, f'Other user failed: {other}'
    query_url = url + ('&' if '?' in url else '?') + 'variant=smoke'
    variant = call(query_url, user + '-other')
    assert variant[0] == 200 and variant[2] != other[2], 'Query cache isolation failed'

    remaining = 60 - time.time() % 60
    if remaining < 40:
        print(f'Waiting {remaining + 1:.1f}s for a fresh minute...', flush=True)
        time.sleep(remaining + 1)
    window = int(time.time()) // 60
    results = [call(url, user) for _ in range(11)]
    assert int(time.time()) // 60 == window, 'Requests crossed a minute boundary; rerun'
    assert [item[0] for item in results] == [200] * 10 + [429], results
    assert len({item[2] for item in results[:10]}) == 1, 'Cached bodies differ'
    assert 1 <= int(results[-1][1]['Retry-After']) <= 60, 'Invalid Retry-After'
    assert json.loads(results[0][2])['userId'] == user
    assert results[0][2] != other[2], 'User cache isolation failed'
    print('Passed: identity validation, query/user isolation, ten identical responses, then HTTP 429.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 scripts/check-rate-limited-api.py RESPONSE_URL')
    main(sys.argv[1])
