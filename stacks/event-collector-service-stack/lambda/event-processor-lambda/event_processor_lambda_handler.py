import boto3
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from event_schema_validator import EventSchemaValidator

logger = logging.getLogger()
logger.setLevel(logging.INFO)

kinesis = boto3.client('kinesis')
stream_name = os.environ['KINESIS_STREAM_NAME']
validator = EventSchemaValidator()


def handler(event, context):
    body = json.loads(event['body'])

    body = validator.tag(body)
    body['processedAt'] = datetime.now(timezone.utc).isoformat()

    partition_key = body.get('accountId', body.get('eventId', str(uuid.uuid4())))
    data = (json.dumps(body) + '\n').encode('utf-8')

    response = kinesis.put_record(
        StreamName=stream_name,
        Data=data,
        PartitionKey=partition_key,
    )

    logger.info(f"Event {body.get('eventId')} schemaStatus={body['schemaStatus']}")

    return {
        'statusCode': 202,
        'body': json.dumps({
            'message': 'Event accepted',
            'schemaStatus': body['schemaStatus'],
            'schemaErrors': body['schemaErrors'],
            'sequenceNumber': response['SequenceNumber'],
        }),
    }