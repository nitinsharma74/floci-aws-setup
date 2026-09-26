import csv
import io
import json
import logging
import os
from urllib.parse import urlparse

import boto3
from opensearchpy import (
    AWSV4SignerAuth,
    OpenSearch,
    RequestsHttpConnection,
    helpers,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# Environment variables
MOVIES_BUCKET = os.environ["MOVIES_BUCKET"]
MOVIES_KEY = os.environ.get("MOVIES_KEY", "raw/movies.csv")
OPENSEARCH_DOMAIN = os.environ["OPENSEARCH_DOMAIN"]
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "movies")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


# AWS clients
s3 = boto3.client("s3")
opensearch_service = boto3.client("opensearch")


def get_opensearch_endpoint():
    """
    Resolve the real OpenSearch endpoint at runtime.

    This avoids relying on the CDK DomainEndpoint value, which may not
    be resolved correctly by Floci when injected into Lambda environment
    variables.
    """

    logger.info(
        "Resolving OpenSearch endpoint for domain: %s",
        OPENSEARCH_DOMAIN,
    )

    response = opensearch_service.describe_domain(DomainName=OPENSEARCH_DOMAIN)

    domain_status = response["DomainStatus"]

    endpoint = domain_status.get("Endpoint")

    # VPC OpenSearch domains can expose endpoints differently.
    if not endpoint:
        endpoints = domain_status.get("Endpoints", {})

        if endpoints:
            endpoint = next(iter(endpoints.values()))

    if not endpoint:
        raise RuntimeError(
            f"No endpoint found for OpenSearch domain '{OPENSEARCH_DOMAIN}'"
        )

    logger.info("Resolved OpenSearch endpoint: %s", endpoint)

    return endpoint


def create_opensearch_client():
    endpoint = get_opensearch_endpoint()

    # AWS OpenSearch endpoints normally do not contain a scheme.
    # Floci may return host:port for its local OpenSearch container.
    if "://" not in endpoint:
        if "amazonaws.com" in endpoint:
            endpoint = f"https://{endpoint}"
        else:
            endpoint = f"http://{endpoint}"

    parsed = urlparse(endpoint)

    host = parsed.hostname
    use_ssl = parsed.scheme == "https"
    port = parsed.port or (443 if use_ssl else 80)

    logger.info(
        "Connecting to OpenSearch host=%s port=%s ssl=%s",
        host,
        port,
        use_ssl,
    )

    client_config = {
        "hosts": [
            {
                "host": host,
                "port": port,
            }
        ],
        "use_ssl": use_ssl,
        "verify_certs": use_ssl,
        "http_compress": True,
        "timeout": 30,
    }

    # Real AWS OpenSearch requires AWS SigV4 authentication.
    # Floci's local OpenSearch data plane does not.
    if host and "amazonaws.com" in host:
        logger.info("Using AWS SigV4 authentication")

        credentials = boto3.Session().get_credentials()

        client_config["http_auth"] = AWSV4SignerAuth(
            credentials,
            AWS_REGION,
            "es",
        )

        client_config["connection_class"] = RequestsHttpConnection
    else:
        logger.info("Using local OpenSearch connection without SigV4")

    return OpenSearch(**client_config)


def create_index_if_needed(client):
    """
    Create the movies index and its mappings if it does not already exist.
    """

    if client.indices.exists(index=OPENSEARCH_INDEX):
        logger.info(
            "OpenSearch index '%s' already exists",
            OPENSEARCH_INDEX,
        )
        return

    logger.info(
        "Creating OpenSearch index '%s'",
        OPENSEARCH_INDEX,
    )

    index_definition = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "properties": {
                "movieId": {"type": "integer"},
                "title": {"type": "text"},
                "genres": {"type": "keyword"},
                "title_suggest": {"type": "completion"},
            }
        },
    }

    client.indices.create(
        index=OPENSEARCH_INDEX,
        body=index_definition,
    )

    logger.info(
        "Created OpenSearch index '%s'",
        OPENSEARCH_INDEX,
    )


def read_movies_from_s3():
    """
    Read movies.csv from S3 and return a CSV DictReader.
    """

    logger.info(
        "Reading movie dataset from s3://%s/%s",
        MOVIES_BUCKET,
        MOVIES_KEY,
    )

    response = s3.get_object(
        Bucket=MOVIES_BUCKET,
        Key=MOVIES_KEY,
    )

    csv_stream = io.TextIOWrapper(
        response["Body"],
        encoding="utf-8",
    )

    return csv.DictReader(csv_stream)


def generate_movie_documents(csv_reader):
    """
    Convert MovieLens CSV rows into OpenSearch bulk-index documents.
    """

    for row in csv_reader:
        genres = []

        if row["genres"] != "(no genres listed)":
            genres = row["genres"].split("|")

        yield {
            "_op_type": "index",
            "_index": OPENSEARCH_INDEX,
            # Using movieId as the OpenSearch document ID makes
            # repeated ingestion idempotent.
            "_id": row["movieId"],
            "_source": {
                "movieId": int(row["movieId"]),
                "title": row["title"],
                "genres": genres,
                # Used later by our autocomplete endpoint.
                "title_suggest": {"input": [row["title"]]},
            },
        }


def handler(event, context):
    logger.info("Starting movie ingestion")

    try:
        # Connect to the actual OpenSearch instance.
        client = create_opensearch_client()

        logger.info("Connected to OpenSearch")

        # Create the index if this is the first ingestion.
        create_index_if_needed(client)

        # Read MovieLens CSV from S3.
        movies = read_movies_from_s3()

        logger.info("Movie dataset retrieved successfully")

        # Bulk index the movie documents.
        indexed_count, errors = helpers.bulk(
            client,
            generate_movie_documents(movies),
            chunk_size=500,
            raise_on_error=False,
            raise_on_exception=False,
        )

        logger.info(
            "Movie ingestion completed: indexed=%s errors=%s",
            indexed_count,
            len(errors),
        )

        # Log a small number of errors if any occurred.
        if errors:
            logger.error(
                "Sample indexing errors: %s",
                errors[:5],
            )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Movie ingestion completed",
                    "indexed": indexed_count,
                    "errors": len(errors),
                    "index": OPENSEARCH_INDEX,
                }
            ),
        }

    except Exception:
        logger.exception("Movie ingestion failed")
        raise
