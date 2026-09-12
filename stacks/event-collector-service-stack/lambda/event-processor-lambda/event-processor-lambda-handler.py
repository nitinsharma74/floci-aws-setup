import boto3
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

firehose = boto3.client('firehose')
delivery_stream_name = os.environ['FIREHOSE_DELIVERY_STREAM_NAME']


def handler(event, context):
    logger.info(f"Received event: {event} with context: {context}")

    body = json.loads(event['body'])
    data = (json.dumps(body) + '\n').encode('utf-8')

    response = firehose.put_record(DeliveryStreamName=delivery_stream_name, Record={'Data': data})

    logger.info(f"Event sent to Firehose: {response['RecordId']}")

    return {
        'statusCode': 202,
        'body': json.dumps({'message': 'Event accepted', 'recordId': response['RecordId']}),
    }