import argparse
import json
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


DEFAULT_URL = 'http://localhost:4566/execute-api/f987ff2baa/$default/events'
DEFAULT_WORKERS = 20


def send_event(url: str, index: int):
    payload = {'eventType': 'load_test_event', 'eventId': str(uuid.uuid4()), 'appId': 'load-test-app', 'userId': f'user-{index}', 'timestamp': time.time()}
    start = time.perf_counter()

    try:
        response = requests.post(url, json=payload, timeout=(2, 10))
        duration = time.perf_counter() - start
        return {'success': 200 <= response.status_code < 300, 'status_code': response.status_code, 'duration': duration, 'error': None if response.ok else response.text}
    except requests.RequestException as exc:
        duration = time.perf_counter() - start
        return {'success': False, 'status_code': None, 'duration': duration, 'error': f'{type(exc).__name__}: {exc}'}


def main():
    parser = argparse.ArgumentParser(description='Send events concurrently to the Event Collector API.')
    parser.add_argument('events', type=int, help='Number of events to send')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help=f'Number of parallel workers (default: {DEFAULT_WORKERS})')
    parser.add_argument('--url', default=DEFAULT_URL, help='Event collector endpoint')
    args = parser.parse_args()

    if args.events <= 0: raise ValueError('events must be greater than 0')
    if args.workers <= 0: raise ValueError('workers must be greater than 0')

    print(f'Sending {args.events} events')
    print(f'Workers: {args.workers}')
    print(f'URL: {args.url}')

    start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(send_event, args.url, index) for index in range(args.events)]
        results = [future.result() for future in as_completed(futures)]

    total_duration = time.perf_counter() - start
    successful = sum(1 for result in results if result['success'])
    failed = len(results) - successful
    durations = [result['duration'] for result in results]
    average_latency = sum(durations) / len(durations) if durations else 0
    requests_per_second = len(results) / total_duration if total_duration > 0 else 0

    status_codes = Counter(result['status_code'] or 'ERROR' for result in results)
    errors = Counter(result['error'] for result in results if result['error'])

    print('\nResults')
    print('-------')
    print(f'Total:           {len(results)}')
    print(f'Successful:      {successful}')
    print(f'Failed:          {failed}')
    print(f'Total time:      {total_duration:.2f}s')
    print(f'Average latency: {average_latency * 1000:.2f}ms')
    print(f'Requests/sec:    {requests_per_second:.2f}')
    print(f'Status codes:    {json.dumps(status_codes)}')

    if errors:
        print('\nErrors')
        print('------')
        for error, count in errors.items(): print(f'{count}x {error}')


if __name__ == '__main__':
    main()