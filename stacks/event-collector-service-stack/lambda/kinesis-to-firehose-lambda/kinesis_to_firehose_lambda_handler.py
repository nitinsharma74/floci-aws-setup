import base64
import boto3
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

firehose = boto3.client('firehose')
delivery_stream_name = os.environ['FIREHOSE_DELIVERY_STREAM_NAME']


def handler(event, context):
    records = []

    for record in event['Records']:
        data = base64.b64decode(record['kinesis']['data'])

        records.append({
            'Data': data,
        })

    if not records:
        return

    response = firehose.put_record_batch(
        DeliveryStreamName=delivery_stream_name,
        Records=records,
    )

    failed_count = response.get('FailedPutCount', 0)

    logger.info(
        f'Received {len(event["Records"])} Kinesis records, '
        f'sent {len(records)} records to Firehose, '
        f'failed={failed_count}'
    )

    if failed_count > 0:
        logger.error(f'Firehose response: {response}')
        raise RuntimeError(f'Failed to send {failed_count} records to Firehose')