## Testing the Event Collector API on Floci

The API Gateway is deployed locally using Floci.

AWS-style API Gateway URLs such as:

```text
https://<api-id>.execute-api.us-east-1.amazonaws.com
```

will not resolve locally because Floci exposes AWS services through:

```text
http://localhost:4566
```

### Health Check

Verify Floci is running:

```bash
curl http://localhost:4566/_floci/health
```

### Invoke the Events API

The event collector exposes:

```text
POST /events
```

Use the Floci API Gateway endpoint:

```bash
curl -i -X POST \
  'http://localhost:4566/execute-api/<api-id>/$default/events' \
  -H 'Content-Type: application/json' \
  -d '{
    "eventType": "test_event",
    "appId": "test-app",
    "userId": "123"
  }'
```

Example:

```bash
curl -i -X POST \
  'http://localhost:4566/execute-api/f987ff2baa/$default/events' \
  -H 'Content-Type: application/json' \
  -d '{
    "eventType": "test_event",
    "appId": "test-app",
    "userId": "123"
  }'
```

The `$default` stage is used because the `HttpApi` created by CDK uses the default API Gateway stage.

## Load Testing

The load test script sends multiple events concurrently to the API Gateway endpoint.

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install requests
```

Run a load test:

```bash
python load_test.py 1000
```

By default, the script uses 20 concurrent workers.

The worker count can be changed using:

```bash
python load_test.py 1000 --workers 40
```

Example output:

```text
Sending 1000 events
Workers: 20
URL: http://localhost:4566/execute-api/f987ff2baa/$default/events

Results
-------
Total:           1000
Successful:      986
Failed:          14
Total time:      22.47s
Average latency: 988.54ms
Requests/sec:    44.51
Status codes:    {"200": 986, "ERROR": 14}

Errors
------
7x ReadTimeout: HTTPConnectionPool(host='localhost', port=4566): Read timed out. (read timeout=10)
```

### Read Timeout Errors

A `ReadTimeout` means the connection to Floci was established successfully, but the request did not receive a complete HTTP response within the configured timeout.

For example:

```text
ReadTimeout: HTTPConnectionPool(host='localhost', port=4566): Read timed out. (read timeout=10)
```

means:

```text
Client
  ↓
Connection established to localhost:4566
  ↓
Request sent
  ↓
Floci / API Gateway / Lambda processing
  ↓
No response within 10 seconds
  ↓
ReadTimeout
```

This usually indicates that the local environment is becoming saturated under concurrent load.

The timeout can be increased in the load test script:

```python
response = requests.post(url, json=payload, timeout=30)
```

Or separate connection and response timeouts can be used:

```python
response = requests.post(url, json=payload, timeout=(2, 30))
```

This allows:

```text
2 seconds  → establish connection
30 seconds → wait for response
```

Timeouts should still be counted as failed requests during load testing.

### Testing Different Concurrency Levels

Run the same number of events with different worker counts:

```bash
python load_test.py 1000 --workers 5
python load_test.py 1000 --workers 10
python load_test.py 1000 --workers 20
python load_test.py 1000 --workers 40
```

Compare:

```text
Requests/sec
Average latency
Failed requests
Timeouts
```

This helps identify the concurrency level at which the local Floci environment begins to saturate.
