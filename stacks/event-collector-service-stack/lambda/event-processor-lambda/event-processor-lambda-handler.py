import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    logger.info(f"Received event: {event} with context: {context}")
    
    return {
        "statusCode": 200,
        "body": "Events Processed Successfully!!"
    }