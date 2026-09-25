import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    return {
        'statusCode': 202,
        'body': json.dumps("Search Result")
    }
