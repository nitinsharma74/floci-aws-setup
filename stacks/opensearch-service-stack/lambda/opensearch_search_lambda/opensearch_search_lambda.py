"""Movie title/genre search with snapshot-based continuation cursors."""

import base64
import binascii
import json
import logging
import math
import os
import time
from urllib.parse import parse_qs, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import ConnectionError, ConnectionTimeout, TransportError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
INDEX = os.environ.get("OPENSEARCH_INDEX", "movies")
KEEP_ALIVE = "5m"
_client = None


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def get_client():
    global _client
    if _client is not None:
        return _client
    service = boto3.client("opensearch", config=Config(
        connect_timeout=3, read_timeout=3, retries={"total_max_attempts": 1},
    ))
    domain = service.describe_domain(
        DomainName=os.environ["OPENSEARCH_DOMAIN"],
    )["DomainStatus"]
    endpoint = domain.get("Endpoint") or next(iter(domain.get("Endpoints", {}).values()), None)
    if not endpoint:
        raise ApiError(503, "SEARCH_UNAVAILABLE", "Search is temporarily unavailable.")
    if "://" not in endpoint:
        endpoint = ("https://" if ".amazonaws.com" in endpoint else "http://") + endpoint
    parsed = urlparse(endpoint)
    host = parsed.hostname
    if not host or parsed.scheme not in ("http", "https"):
        raise RuntimeError("Invalid OpenSearch endpoint")
    aws_host = host.endswith((".amazonaws.com", ".amazonaws.com.cn"))
    use_ssl = aws_host or parsed.scheme == "https"
    config = dict(
        hosts=[{"host": host, "port": parsed.port or (443 if use_ssl else 80)}],
        use_ssl=use_ssl, verify_certs=use_ssl, http_compress=True,
        timeout=5, max_retries=0, retry_on_timeout=False,
    )
    if aws_host:
        config.update(
            http_auth=AWSV4SignerAuth(boto3.Session().get_credentials(),
                                      os.environ.get("AWS_REGION", "us-east-1"), "es"),
            connection_class=RequestsHttpConnection,
        )
    _client = OpenSearch(**config)
    return _client


def encode_cursor(pit_id, sort, params):
    data = {"v": 1, "pit": pit_id, "sort": sort, "params": params}
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":"),
                                              allow_nan=False).encode()).decode().rstrip("=")


def decode_cursor(token, params):
    try:
        if not token or len(token) > 8000:
            raise ValueError()
        data = json.loads(base64.b64decode(token + "=" * (-len(token) % 4),
                                          altchars=b"-_", validate=True))
        if not isinstance(data, dict) or type(data.get("v")) is not int or data["v"] != 1:
            raise ValueError()
        if data.get("params") != params:
            raise ValueError()
        if not isinstance(data.get("pit"), str) or not data["pit"] or len(data["pit"]) > 6000:
            raise ValueError()
        sort = data.get("sort")
        if not isinstance(sort, list) or len(sort) != (2 if params["q"] else 1):
            raise ValueError()
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in sort):
            raise ValueError()
        if type(sort[-1]) is not int:
            raise ValueError()
        return data
    except (ValueError, TypeError, binascii.Error, UnicodeError, OverflowError):
        raise ApiError(400, "INVALID_CURSOR", "Invalid cursor or changed search parameters.") from None


def parse_request(event):
    raw = event.get("queryStringParameters") or {}
    if not isinstance(raw, dict):
        raise ApiError(400, "INVALID_REQUEST", "Invalid query parameters.")
    # HTTP API v2 joins duplicate values with commas; inspect the raw query too.
    if any(len(values) != 1 for values in parse_qs(
            event.get("rawQueryString") or "", keep_blank_values=True).values()):
        raise ApiError(400, "INVALID_REQUEST", "Query parameters must not be repeated.")
    if set(raw) - {"q", "genre", "limit", "cursor"} or any(not isinstance(v, str) for v in raw.values()):
        raise ApiError(400, "INVALID_REQUEST", "Unsupported query parameters.")
    query, genre = raw.get("q", "").strip(), raw.get("genre", "").strip()
    if not query and not genre:
        raise ApiError(400, "INVALID_REQUEST", "Provide q or genre.")
    if len(query) > 200 or len(genre) > 100:
        raise ApiError(400, "INVALID_REQUEST", "q must be at most 200 characters and genre at most 100.")
    limit = raw.get("limit", "20")
    if not limit.isascii() or not limit.isdigit() or len(limit) > 3 or not 1 <= int(limit) <= 100:
        raise ApiError(400, "INVALID_REQUEST", "limit must be an integer from 1 to 100.")
    params = {"q": query or None, "genre": genre or None, "limit": int(limit)}
    cursor = decode_cursor(raw["cursor"], params) if "cursor" in raw else None
    return params, cursor


def close_snapshot(client, pit_id):
    try:
        client.delete_pit(body={"pit_id": [pit_id]}, request_timeout=2)
    except Exception:
        # Cleanup must not turn a completed search into a failed request. The PIT expires.
        logger.warning("Snapshot cleanup failed", exc_info=True)


def ensure_complete(result):
    if result.get("timed_out"):
        raise ApiError(504, "SEARCH_TIMEOUT", "Search timed out. Please retry.")
    if result.get("_shards", {}).get("failed", 0):
        raise ApiError(503, "SEARCH_UNAVAILABLE", "Search is temporarily unavailable.")


def search_movies(client, params, cursor):
    pit_id = cursor["pit"] if cursor else None
    handed_off = False
    completed = False
    try:
        if not pit_id:
            snapshot = client.create_pit(index=INDEX, params={
                "keep_alive": KEEP_ALIVE, "allow_partial_pit_creation": "false",
            })
            pit_id = snapshot["pit_id"]
            ensure_complete(snapshot)
        query = {"bool": {"must": [], "filter": []}}
        if params["q"]:
            query["bool"]["must"].append({"match": {"title": {
                "query": params["q"], "fuzziness": "AUTO", "operator": "and",
            }}})
        if params["genre"]:
            query["bool"]["filter"].append({"term": {"genres": params["genre"]}})
        sort = [{"_score": "desc"}, {"movieId": "asc"}] if params["q"] else [{"movieId": "asc"}]
        body = {
            "query": query, "sort": sort, "size": params["limit"] + 1,
            "track_total_hits": True, "timeout": "4s",
            "_source": ["movieId", "title", "genres"],
            "pit": {"id": pit_id, "keep_alive": KEEP_ALIVE},
        }
        if cursor:
            body["search_after"] = cursor["sort"]
        result = client.search(body=body, params={"allow_partial_search_results": "false"})
        ensure_complete(result)
        hits = result["hits"]["hits"]
        total = result["hits"]["total"]
        if total["relation"] != "eq":
            raise ApiError(503, "SEARCH_UNAVAILABLE", "Could not obtain complete search results.")
        page = hits[:params["limit"]]
        next_cursor = encode_cursor(pit_id, page[-1]["sort"], params) if len(hits) > len(page) else None
        movies = [{field: hit["_source"][field] for field in ("movieId", "title", "genres")} for hit in page]
        handed_off = next_cursor is not None
        completed = True
        return {"query": params["q"], "genre": params["genre"], "total": total["value"],
                "movies": movies, "nextCursor": next_cursor}
    finally:
        # Keep existing cursors retryable after transient failures; clean newly opened PITs.
        if pit_id and not handed_off and (not cursor or completed):
            close_snapshot(client, pit_id)


def response(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
            "body": json.dumps(body, separators=(",", ":"), allow_nan=False)}


def handler(event, context):
    global _client
    started = time.monotonic()
    request_id = getattr(context, "aws_request_id", None) or event.get("requestContext", {}).get("requestId")
    status, count = 500, 0
    cursor = None
    try:
        params, cursor = parse_request(event)
        data = search_movies(get_client(), params, cursor)
        count = len(data["movies"])
        status = 200
        return response(status, data)
    except ApiError as exc:
        error = exc
    except ConnectionTimeout:
        _client = None
        error = ApiError(504, "SEARCH_TIMEOUT", "Search timed out. Please retry.")
    except ConnectionError:
        _client = None
        error = ApiError(503, "SEARCH_UNAVAILABLE", "Search is temporarily unavailable.")
        logger.warning("OpenSearch connection failed request_id=%s", request_id, exc_info=True)
    except TransportError as exc:
        # Only a missing search context is cursor expiry; missing indices are unavailable.
        details = json.dumps(exc.info or {})
        if cursor and ("search_context_missing_exception" in details or "resource_not_found_exception" in details):
            error = ApiError(410, "CURSOR_EXPIRED", "Search cursor expired. Restart without a cursor.")
        elif exc.status_code in (408, 504):
            error = ApiError(504, "SEARCH_TIMEOUT", "Search timed out. Please retry.")
        else:
            error = ApiError(503, "SEARCH_UNAVAILABLE", "Search is temporarily unavailable.")
        logger.warning("OpenSearch request failed request_id=%s", request_id, exc_info=True)
    except (BotoCoreError, ClientError):
        error = ApiError(503, "SEARCH_UNAVAILABLE", "Search is temporarily unavailable.")
        logger.warning("Domain discovery failed request_id=%s", request_id, exc_info=True)
    except Exception:
        error = ApiError(500, "INTERNAL_ERROR", "An unexpected error occurred.")
        logger.exception("Search failed request_id=%s", request_id)
    finally:
        logger.info("Search request_id=%s duration_ms=%d count=%d status=%d",
                    request_id, (time.monotonic() - started) * 1000, count,
                    error.status if "error" in locals() else status)
    return response(error.status, {"error": {"code": error.code, "message": error.message}})
