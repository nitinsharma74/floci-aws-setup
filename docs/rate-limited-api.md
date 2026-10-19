# REST API with rate limiting and response caching

`RateLimitedApiStack` is an independent API Gateway REST API backed by a Python
3.13 Lambda and one on-demand DynamoDB table. It does not depend on the other
example stacks.

## Behavior

Call `GET /response` with an `X-User-Id` header. A missing or blank identity
returns HTTP 400. The header is a caller-provided demo identity, not authentication;
clients can change it. Real applications should derive identity from verified
credentials.

Each user may make ten requests per fixed UTC minute across all query variants.
Every valid request consumes an allowance before the cache lookup, including
cache hits. Request eleven returns HTTP 429 with a `Retry-After` header indicating
seconds until the next minute. Fixed windows allow bursts across minute boundaries.

Successful JSON bodies contain `userId`, `responseId`, and `generatedAt`. The same
user, method, path, and query parameters receive the same body for 3,600 seconds
from its creation. Query parameter names and repeated values are sorted for the
cache key; repeated values are preserved. Different users or parameters get
separate entries. Reads do not extend expiry. At expiry a new response is stored.
Concurrent cache misses use a conditional write and strongly consistent reads so
callers return the winning response.

Lambda explicitly checks cache expiry; DynamoDB TTL only cleans up old records.
The table stores separate hashed cache keys and per-user, per-minute counters.
Storage errors return HTTP 503 without bypassing rate enforcement or caching.
A failed request after admission still consumes its allowance. Counters are shared
across Lambda instances. Rate and cache duration are configured with the Lambda
`RATE_LIMIT=10` and `CACHE_TTL_SECONDS=3600` environment variables.

Caching happens inside Lambda, so a cache hit still invokes Lambda and DynamoDB.
API Gateway cache clusters are disabled to ensure every call reaches the limiter.
Floci's native gateway throttling settings are not enforced; see
[Floci API Gateway support](https://floci.io/floci/services/api-gateway/#usage-reporting).
Responses use `Cache-Control: no-store` so client caching does not bypass the demo.

## Deploy locally

From the repository root, with Docker running:

```bash
floci start
eval "$(floci env)"
export AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566
aws sts get-caller-identity # expected local account: 000000000000
# Needed once per local environment.
npx cdklocal bootstrap
npm run build
npx cdklocal synth RateLimitedApiStack
npx cdklocal diff RateLimitedApiStack
npx cdklocal deploy RateLimitedApiStack --require-approval never

API_ID=$(aws cloudformation describe-stacks --stack-name RateLimitedApiStack \
  --query "Stacks[0].Outputs[?OutputKey=='ApiId'].OutputValue | [0]" --output text)
RESPONSE_URL="http://localhost:4566/execute-api/${API_ID}/dev/response"
```

Outputs include `ApiId`, `ResponseUrl` (the standard AWS URL), and `StateTableName`.
Use the constructed local URL above to call Floci from the host. Lambda relies on
Floci's SDK endpoint environment; do not set its DynamoDB endpoint to host localhost.
If deployment synthesizes the existing OpenSearch assets, its dependency bundling
also requires Docker and package-download access, as described in the root README.

## Verify behavior

Use a fresh identity to avoid allowances consumed in earlier checks:

```bash
DEMO_USER="cache-demo-$(date +%s)"
curl -sS "$RESPONSE_URL" -H "X-User-Id: $DEMO_USER"
curl -sS "$RESPONSE_URL" -H "X-User-Id: $DEMO_USER"
# Both bodies have the same responseId and generatedAt.

curl -sS "$RESPONSE_URL" -H "X-User-Id: ${DEMO_USER}-other"
# Different userId and responseId.

curl -sS "$RESPONSE_URL?variant=another" -H "X-User-Id: $DEMO_USER"
# A separate cached response for different query parameters.

curl -i "$RESPONSE_URL"
# HTTP 400: X-User-Id is required.
```

For a repeatable limit check, run the smoke script. It waits for a fresh minute
when needed, sends eleven requests for a unique user, checks that ten bodies are
identical, and verifies HTTP 429 and `Retry-After` on the eleventh request. It also
checks isolation and missing identity. The script stops if the request loop crosses
a minute boundary; rerun it in that case.

```bash
python3 scripts/check-rate-limited-api.py "$RESPONSE_URL"
```

A repeated successful request after one hour generates a new body. Unit tests use
a controlled clock to verify the exact expiry boundary without an hour-long wait.

## Tests

```bash
npm run build
npm test -- --runInBand test/rate-limited-api-stack.test.ts
python3 -m venv /tmp/floci-rate-api-tests
/tmp/floci-rate-api-tests/bin/python -m pip install boto3
/tmp/floci-rate-api-tests/bin/python -m unittest discover \
  -s test/python -p test_rate_limited_api.py
```

The infrastructure assertions cover REST routing and integration, disabled gateway
caching, table TTL, runtime configuration, outputs, and table-restricted IAM.
Python tests cover concurrency, cache expiry and isolation, limits and rollover,
and storage failures. The Python tests make no AWS calls. The live smoke script
verifies the deployed integration and real DynamoDB conditional operations in Floci.

## Cleanup

```bash
npx cdklocal destroy RateLimitedApiStack
```

This demo uses a destructive table removal policy: destroying the stack deletes
its counters and cached responses. No production deployment or authentication is
included.
