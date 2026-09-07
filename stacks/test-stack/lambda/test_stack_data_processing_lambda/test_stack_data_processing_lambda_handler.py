import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

PROCESSED_BUCKET_NAME = os.environ["PROCESSED_BUCKET_NAME"]


def handler(event, context):
    logger.info(f"Received event: {event} with context: {context}")

    for record in event["Records"]:
        raw_bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        logger.info(f"Processing file: s3://{raw_bucket}/{key}")

        response = s3.get_object(Bucket=raw_bucket, Key=key)

        content = response["Body"].read().decode("utf-8")
        processed_content = content.upper()
        s3.put_object(Bucket=PROCESSED_BUCKET_NAME, Key=key, Body=processed_content)

        logger.info(f"Processed file written to s3://{PROCESSED_BUCKET_NAME}/{key}")

    return {
        "statusCode": 200,
        "body": f"File processed successfully and written to s3://{PROCESSED_BUCKET_NAME}/{key}"
    }