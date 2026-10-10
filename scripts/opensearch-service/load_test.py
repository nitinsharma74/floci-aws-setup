"""Concurrent movie search load test using only Python's standard library."""

import argparse
import json
import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen


SEARCHES = [
    {'q': 'Toy Story'}, {'q': 'toy stroy'}, {'q': 'Star Wars'},
    {'q': 'The Matrix'}, {'q': 'the matrxi'}, {'q': 'Jurassic Park'},
    {'q': 'The Godfather'}, {'q': 'Pulp Fiction'}, {'q': 'Forrest Gump'},
    {'q': 'The Shawshank Redemption'}, {'q': 'The Dark Knight'},
    {'q': 'The Lord of the Rings'}, {'q': 'Harry Potter'},
    {'q': 'Back to the Future'}, {'q': 'Indiana Jones'},
    {'q': 'Finding Nemo'}, {'q': 'The Lion King'}, {'q': 'Titanic'},
    {'q': 'Alien'}, {'q': 'Terminator'}, {'q': 'Die Hard'},
    {'q': 'Ghostbusters'}, {'q': 'Shrek'}, {'q': 'Inception'},
    {'genre': 'Comedy'}, {'genre': 'Drama'},
    {'genre': 'Action'}, {'genre': 'Adventure'}, {'genre': 'Animation'},
    {'genre': 'Sci-Fi'}, {'genre': 'Thriller'}, {'genre': 'Horror'},
    {'q': 'Toy Story', 'genre': 'Comedy'},
    {'q': 'Star Wars', 'genre': 'Sci-Fi'},
    {'q': 'The Matrix', 'genre': 'Action'},
    {'q': 'Jurassic Park', 'genre': 'Adventure'},
    {'q': 'The Godfather', 'genre': 'Crime'},
    {'q': 'Finding Nemo', 'genre': 'Animation'},
    {'q': 'Titanic', 'genre': 'Romance'},
]


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be greater than zero')
    return number


def positive_timeout(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('must be a finite positive number')
    return number


def send_search(url, params, timeout):
    started = time.perf_counter()
    status, error, movies = None, None, 0
    try:
        with urlopen(url + '?' + urlencode(params), timeout=timeout) as response:
            status = response.status
            data = json.load(response)
        if status != 200:
            error = f'Unexpected HTTP status {status}'
        elif (not isinstance(data, dict)
              or type(data.get('total')) is not int or data['total'] < 0
              or not isinstance(data.get('movies'), list)
              or 'nextCursor' not in data
              or (data['nextCursor'] is not None and not isinstance(data['nextCursor'], str))):
            error = 'Invalid search response'
        else:
            movies = len(data['movies'])
    except HTTPError as exc:
        status = exc.code
        error = f'HTTP {status}: {exc.read(500).decode("utf-8", errors="replace")}'
        exc.close()
    except (URLError, OSError, ValueError) as exc:
        error = f'{type(exc).__name__}: {exc}'
    return {'status': status, 'error': error, 'movies': movies,
            'duration_ms': (time.perf_counter() - started) * 1000}


def percentile(values, percent):
    return values[max(0, math.ceil(len(values) * percent / 100) - 1)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('requests', type=positive_int, help='Total search requests')
    parser.add_argument('--url', required=True, help='Full /movies/search endpoint (quote it)')
    parser.add_argument('--workers', type=positive_int, default=20)
    parser.add_argument('--timeout', type=positive_timeout, default=30, help='Socket timeout in seconds')
    parser.add_argument('--limit', type=positive_int, default=20)
    parser.add_argument('--query', help='Use this title instead of the default mixed workload')
    parser.add_argument('--genre', help='Use this exact genre; combines with --query when supplied')
    parser.add_argument('--output', type=Path, help='Save a JSON summary')
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment:
        parser.error('--url must be an HTTP(S) endpoint without query parameters or a fragment')
    if any(part in ('None', 'null', 'undefined') for part in parsed.path.split('/')):
        parser.error('--url contains a missing API ID; use the API ID from your deployment')
    if args.limit > 100:
        parser.error('--limit must be between 1 and 100')
    for name, value, maximum in [('query', args.query, 200), ('genre', args.genre, 100)]:
        if value is not None and (not value.strip() or len(value.strip()) > maximum):
            parser.error(f'--{name} must contain 1 to {maximum} nonblank characters')
    searches = SEARCHES
    if args.query is not None or args.genre is not None:
        searches = [{key: value.strip() for key, value in
                     [('q', args.query), ('genre', args.genre)] if value is not None}]
    workers = min(args.workers, args.requests)
    print(f'Sending {args.requests} searches with {workers} workers to {args.url}', flush=True)
    print(f'Workload: {json.dumps(searches)}; limit={args.limit}; paginate=false', flush=True)
    started = time.perf_counter()

    # Submit only one task per worker, avoiding a future for every request.
    def run_worker(worker):
        return [send_search(args.url, {**searches[index % len(searches)], 'limit': args.limit, 'paginate': 'false'},
                            args.timeout) for index in range(worker, args.requests, workers)]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = [result for batch in executor.map(run_worker, range(workers)) for result in batch]
    elapsed = time.perf_counter() - started
    durations = sorted(result['duration_ms'] for result in results)
    successful = sum(result['error'] is None for result in results)
    summary = {
        'url': args.url, 'workers': workers, 'searches': searches, 'limit': args.limit, 'paginate': False,
        'requests': len(results), 'successful': successful, 'failed': len(results) - successful,
        'elapsed_seconds': round(elapsed, 3), 'requests_per_second': round(len(results) / elapsed, 2),
        'latency_ms': {'average': round(sum(durations) / len(durations), 2),
                       **{f'p{p}': round(percentile(durations, p), 2) for p in (50, 95, 99)},
                       'max': round(durations[-1], 2)},
        'status_codes': dict(Counter(str(result['status']) if result['status'] is not None
                                     else 'ERROR' for result in results)),
        'movies_returned': sum(result['movies'] for result in results),
        'errors': dict(Counter(result['error'] for result in results if result['error'])),
    }
    print(json.dumps(summary, indent=2))
    if args.output:
        args.output.write_text(json.dumps(summary, indent=2) + '\n')
    return 1 if summary['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
