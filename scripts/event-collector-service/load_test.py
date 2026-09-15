import argparse
import json
import random
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests


DEFAULT_URL = 'http://localhost:4566/execute-api/58f2337832/$default/events'
DEFAULT_WORKERS = 20

MERCHANTS = ['amazon', 'walmart', 'target', 'apple', 'netflix', 'uber', 'starbucks', 'bestbuy']
COUNTRIES = ['US', 'MX', 'CA', 'GB', 'DE', 'FR']
CURRENCIES = ['USD', 'MXN', 'CAD', 'GBP', 'EUR']
CHANNELS = ['POS', 'ECOMMERCE', 'ATM', 'MOBILE']
TRANSACTION_TYPES = ['PURCHASE', 'WITHDRAWAL', 'TRANSFER', 'PAYMENT']


def create_transaction(index: int, fraud_rate: float):
    suspicious = random.random() < fraud_rate
    country = random.choice(COUNTRIES)
    channel = random.choice(CHANNELS)
    amount = round(random.uniform(1, 500), 2)

    if suspicious:
        amount = round(random.uniform(3000, 15000), 2)
        channel = random.choice(['ECOMMERCE', 'ATM'])
        country = random.choice(['GB', 'DE', 'FR'])

    return {
        'eventType': 'bank_transaction',
        'eventId': str(uuid.uuid4()),
        'transactionId': str(uuid.uuid4()),
        'accountId': f'account-{random.randint(1, 10000)}',
        'cardId': f'card-{random.randint(1, 20000)}',
        'merchantId': random.choice(MERCHANTS),
        'transactionType': random.choice(TRANSACTION_TYPES),
        'channel': channel,
        'amount': amount,
        'currency': random.choice(CURRENCIES),
        'country': country,
        'deviceId': f'device-{random.randint(1, 5000)}',
        'ipAddress': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'expectedFraud': suspicious,
        'sequence': index,
    }


def send_event(url: str, index: int, fraud_rate: float):
    payload = create_transaction(index, fraud_rate)
    start = time.perf_counter()

    try:
        response = requests.post(url, json=payload, timeout=(2, 10))
        duration = time.perf_counter() - start
        return {'success': response.ok, 'status_code': response.status_code, 'duration': duration, 'error': None if response.ok else response.text, 'fraud': payload['expectedFraud']}
    except requests.RequestException as exc:
        duration = time.perf_counter() - start
        return {'success': False, 'status_code': None, 'duration': duration, 'error': f'{type(exc).__name__}: {exc}', 'fraud': payload['expectedFraud']}


def main():
    parser = argparse.ArgumentParser(description='Send synthetic banking transactions to the Event Collector API.')
    parser.add_argument('events', type=int, help='Number of transactions to send')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help=f'Parallel workers (default: {DEFAULT_WORKERS})')
    parser.add_argument('--fraud-rate', type=float, default=0.05, help='Synthetic fraud rate between 0 and 1 (default: 0.05)')
    parser.add_argument('--url', default=DEFAULT_URL, help='Event collector endpoint')
    args = parser.parse_args()

    if args.events <= 0: raise ValueError('events must be greater than 0')
    if args.workers <= 0: raise ValueError('workers must be greater than 0')
    if not 0 <= args.fraud_rate <= 1: raise ValueError('fraud-rate must be between 0 and 1')

    print(f'Sending {args.events} banking transactions')
    print(f'Workers: {args.workers}')
    print(f'Fraud rate: {args.fraud_rate:.2%}')
    print(f'URL: {args.url}')

    start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(send_event, args.url, index, args.fraud_rate) for index in range(args.events)]
        results = [future.result() for future in as_completed(futures)]

    total_duration = time.perf_counter() - start
    successful = sum(1 for result in results if result['success'])
    failed = len(results) - successful
    synthetic_fraud = sum(1 for result in results if result['fraud'])
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
    print(f'Synthetic fraud: {synthetic_fraud}')
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