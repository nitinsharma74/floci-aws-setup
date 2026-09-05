import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,  # Capture all logs (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s [%(levelname)s] %(message)s",  # Timestamp, log level, and message
    datefmt="%Y-%m-%d %H:%M:%S"
)

# defining the handler
def handler(event, context):
    
    # Generate logs at different severity levels
    logging.debug("This is a diagnostic message for debugging.")
    logging.info("This is a general informational message.")
    logging.warning("This is a warning! Something unexpected happened.")
    logging.error("This is an error! A feature failed to work.")
    logging.critical("This is a critical issue! The application is stopping.")

    return {
        "statusCode": 200,
        "body": "Hello World"
    }