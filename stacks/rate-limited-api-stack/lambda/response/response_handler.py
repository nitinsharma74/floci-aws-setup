"""A demo REST endpoint with shared, atomic per-user limits and response caching."""

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)
_table = None


def get_table():
    global _table
    if _table is None:
        # Floci supplies the SDK endpoint in its Lambda environment. On AWS the
        # SDK uses its normal regional endpoint; never use host localhost here.
        _table = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
    return _table


def response(status, body, headers=None):
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Cache-Control': 'no-store',
                    **(headers or {})},
        'body': body if isinstance(body, str) else json.dumps(body),
    }


def conditional_failure(error):
    return error.response['Error']['Code'] == 'ConditionalCheckFailedException'


def cache_key(event, user):
    # Preserve repeated values but ignore query parameter and value ordering.
    params = dict(event.get('multiValueQueryStringParameters') or {})
    for name, value in (event.get('queryStringParameters') or {}).items():
        params.setdefault(name, [value])
    query = sorted((name, sorted(values)) for name, values in params.items())
    identity = [user, event.get('httpMethod', 'GET'), event.get('path', '/response'), query]
    return 'CACHE#' + hashlib.sha256(
        json.dumps(identity, separators=(',', ':'), ensure_ascii=True).encode()
    ).hexdigest()


def cached_response(table, key, user, ttl):
    # A conditional writer wins each empty/expired cache slot. Losers read the
    # winner rather than returning their independently generated response.
    for _ in range(3):
        now = int(time.time())
        item = table.get_item(Key={'pk': key}, ConsistentRead=True).get('Item')
        if item and int(item['expiresAt']) > now:
            return response(200, item['body'])
        body = json.dumps({
            'userId': user,
            'responseId': str(uuid.uuid4()),
            'generatedAt': datetime.fromtimestamp(now, timezone.utc).isoformat(),
        })
        try:
            table.put_item(
                Item={'pk': key, 'body': body, 'expiresAt': now + ttl},
                ConditionExpression='attribute_not_exists(pk) OR expiresAt <= :now',
                ExpressionAttributeValues={':now': now},
            )
            return response(200, body)
        except ClientError as error:
            if not conditional_failure(error):
                raise
    # Includes an unexpected disappearance of the winner during repeated races.
    return response(503, {'message': 'Response cache temporarily unavailable'})


def handler(event, context):
    headers = {key.lower(): value for key, value in (event.get('headers') or {}).items()}
    user = (headers.get('x-user-id') or '').strip()
    if not user:
        return response(400, {'message': 'X-User-Id is required'})

    now = int(time.time())
    window = now // 60
    user_hash = hashlib.sha256(user.encode()).hexdigest()
    try:
        table = get_table()
        try:
            table.update_item(
                Key={'pk': f'RATE#{user_hash}#{window}'},
                UpdateExpression='SET expiresAt = :expiry ADD #count :one',
                ConditionExpression='attribute_not_exists(#count) OR #count < :limit',
                ExpressionAttributeNames={'#count': 'count'},
                ExpressionAttributeValues={
                    ':one': 1, ':limit': int(os.environ.get('RATE_LIMIT', '10')),
                    ':expiry': (window + 1) * 60,
                },
            )
        except ClientError as error:
            if not conditional_failure(error):
                raise
            return response(429, {'message': 'Rate limit exceeded'},
                            {'Retry-After': str(max(1, (window + 1) * 60 - int(time.time())))})

        return cached_response(table, cache_key(event, user), user,
                               int(os.environ.get('CACHE_TTL_SECONDS', '3600')))
    except (BotoCoreError, ClientError):
        logger.exception('API state storage failed')
        return response(503, {'message': 'API state storage temporarily unavailable'})
