# Local AWS Development with Floci + TypeScript CDK

This repository contains AWS examples developed locally with Floci, AWS CDK in
TypeScript, and Python Lambda functions. Use the existing stacks below to deploy
and test each service.

## Projects

| Stack | What it does | Guide |
| --- | --- | --- |
| `TestStack` | An S3 upload invokes a Lambda that uppercases the file contents and writes them to a processed bucket. | [Stack source](lib/test-stack.ts) |
| `EventCollectorServiceStack` | An HTTP API accepts events for processing through Lambda, Kinesis, Firehose, S3, Glue, and Athena. | [Event Collector Service](docs/event-collector-service/README.md) |
| `OpenSearchServiceStack` | Ingests MovieLens data and serves title search with typo tolerance, genre filters, and JSON pagination. Autocomplete is planned. | [OpenSearch Movie Search Service](docs/opensearch-service/README.md) |

The CDK entry point is [bin/app.ts](bin/app.ts). Stack definitions live in `lib/`,
Lambda code in `stacks/`, and infrastructure and Python tests in `test/`.

```text
.
├── bin/app.ts
├── lib/
├── stacks/
├── docs/
├── test/
│   └── python/
├── cdk.json
├── package.json
├── package-lock.json
└── tsconfig.json
```

## Prerequisites

Install Node.js/npm, AWS CLI v2, Floci, and Python 3. Python 3.13 matches the Lambda
runtime. Install and start Docker Desktop (or a compatible Docker engine) before
using Floci or bundling Lambda dependencies. Commands below assume a macOS shell
and are run from the repository root.

```bash
# Install the command-line prerequisites with Homebrew.
brew install node awscli python
brew install floci-io/floci/floci

# Verify the installed tools; AWS CLI should report aws-cli/2.x.
node --version
npm --version
aws --version
floci --version
python3 --version

# Verify that the Docker engine is running and reachable.
docker info
```

Docker is also required for CDK synthesis and infrastructure tests because the
OpenSearch Lambda dependencies are bundled in Docker. Bundling downloads Python
packages, so it requires network access.

## Set up the repository

```bash
# Install the Node dependencies recorded in package-lock.json, including CDK tools.
npm ci

# Start the local AWS emulator.
floci start

# Load Floci's local endpoint, test credentials, and region into this shell.
eval "$(floci env)"

# Set the dedicated S3 endpoint required by aws-cdk-local.
export AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566

# Confirm that AWS calls reach the local account (000000000000).
aws sts get-caller-identity

# Create CDKToolkit and its asset bucket in Floci, normally once per local environment.
npx cdklocal bootstrap

# Type-check the existing CDK app.
npm run build

# List the three stack names available for deployment.
npx cdklocal list
```

Reload the Floci environment and S3 endpoint in each new terminal session.
The default local region is `us-east-1`. Bootstrapping must be repeated if the
local bootstrap resources are removed or the emulator state is reset.

## Build and deploy a stack

Choose a stack from the project table. This example deploys the movie service:

```bash
# Generate the movie stack's CloudFormation template and bundled Lambda assets.
npx cdklocal synth OpenSearchServiceStack

# Review changes to the local deployment.
npx cdklocal diff OpenSearchServiceStack

# Deploy the selected stack to Floci.
npx cdklocal deploy OpenSearchServiceStack

# Inspect the deployed stack and its outputs.
aws cloudformation describe-stacks --stack-name OpenSearchServiceStack

# List local S3 buckets, including the CDK bootstrap bucket.
aws s3 ls
```

For the other examples, substitute `TestStack` or `EventCollectorServiceStack`.
Follow the selected service guide for data upload, invocation, and verification.
In particular, Floci may require the OpenSearch domain to be created separately;
follow [Run locally](docs/opensearch-service/README.md#run-locally) to create the
domain, upload the CSV, and run ingestion before searching.

## Movie search quick start

After completing [OpenSearch setup and ingestion](docs/opensearch-service/README.md#run-locally),
use API Gateway's local endpoint to search the data:

```bash
# Discover the deployed API ID instead of hardcoding a session-specific value.
MOVIES_API_ID=$(aws apigatewayv2 get-apis \
  --query "Items[?Name=='movies-search-api'].ApiId | [0]" --output text)

# Construct Floci's host-accessible route; preserve the literal $default stage name.
MOVIES_SEARCH_URL="http://localhost:4566/execute-api/${MOVIES_API_ID}/\$default/movies/search"

# Search titles with typo tolerance and filter to Comedy; return at most five movies.
curl -sS --max-time 30 --get "$MOVIES_SEARCH_URL" \
  --data-urlencode 'q=toy stroy' \
  --data-urlencode 'genre=Comedy' \
  --data-urlencode 'limit=5'
```

If API discovery returns `None`, check that `OpenSearchServiceStack` is deployed
and that the shell uses the Floci environment. The JSON response contains
`query`, `genre`, `total`, `movies`, and `nextCursor`. Follow the cursor to retrieve
additional pages. The demo endpoint is unauthenticated.

See [Search movies through the API](docs/opensearch-service/README.md#search-movies-through-the-api)
for parameters, sample responses, pagination, and errors. For direct Docker
queries, see [Manually search and verify movie data](docs/opensearch-service/README.md#manually-search-and-verify-movie-data).

## Run tests

```bash
# Type-check the TypeScript stack definitions.
npm run build

# Run all CDK infrastructure tests; Docker must be running for Lambda bundling.
npm test -- --runInBand
```

Python unit tests cover movie-search queries, pagination, cursor validation,
connection setup, and failures. See the commented environment and test commands
in [Test the search implementation](docs/opensearch-service/README.md#test-the-search-implementation).
These tests mock OpenSearch; deployed API checks use the commands in the service guide.

## Recommended local workflow

```bash
# Start Floci and configure this terminal for local AWS calls.
floci start
eval "$(floci env)"
export AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566

# Confirm the local account, then validate changes.
aws sts get-caller-identity
npm run build
npm test -- --runInBand

# Review and deploy just the stack being changed.
npx cdklocal diff OpenSearchServiceStack
npx cdklocal deploy OpenSearchServiceStack
```

## Clean up a stack

Destroy a selected stack only when its resources are no longer needed. The stacks
use destructive removal policies for some resources. Nonempty S3 buckets may
prevent deletion because automatic object deletion is not configured; review
and handle their contents before retrying a failed teardown.

```bash
# Remove the selected application stack from the configured local environment.
npx cdklocal destroy OpenSearchServiceStack

# Inspect the remaining local stacks.
aws cloudformation list-stacks
```

`CDKToolkit` and its reusable bootstrap resources are separate from the application
stack. A manually created Floci OpenSearch domain is also managed separately;
do not assume deleting the stack removes that domain or its indexed data.

## Troubleshooting

### Credentials or endpoint errors

For `InvalidClientTokenId` or calls unexpectedly reaching AWS, check the selected
CLI and reload the local configuration:

```bash
# Check CLI version and which installation your shell selects.
aws --version
which -a aws

# Reload local credentials and endpoints; remove a stale temporary AWS session token.
eval "$(floci env)"
unset AWS_SESSION_TOKEN
export AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566

# Inspect endpoint settings without printing credentials.
printenv AWS_ENDPOINT_URL AWS_ENDPOINT_URL_S3

# Compare default endpoint resolution with an explicit local request.
aws sts get-caller-identity
aws sts get-caller-identity --endpoint-url http://localhost:4566
```

Expected endpoints are `http://localhost.floci.io:4566` and
`http://s3.localhost.floci.io:4566`. If only the explicit request works, check AWS
CLI v2 installation, PATH order, and endpoint overrides in your AWS configuration.
Use Homebrew to install or upgrade `awscli` as appropriate. On Apple Silicon,
Homebrew's CLI is usually `/opt/homebrew/bin/aws`; ensure the intended installation
appears first in PATH and open a new terminal after changing it.

### `AWS_ENDPOINT_URL_S3 must be specified`

`aws-cdk-local` requires the S3 override alongside the general Floci endpoint:

```bash
# Restore the S3 endpoint, then retry the selected deployment.
export AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566
npx cdklocal deploy OpenSearchServiceStack
```

### Docker is unavailable or Lambda bundling fails

Start Docker Desktop or your configured Docker engine, then check connectivity:

```bash
# Inspect the selected Docker context and its engine.
docker context show
docker info

# Confirm Floci and service containers are running.
docker ps --format '{{.Names}}\t{{.Ports}}'
```

For package-download failures during bundling, check the container's network
access. Retry the failed synthesis, test, or deployment after fixing the cause.

### Direct OpenSearch curl hangs

Floci may return an internal Docker address that your Mac cannot reach directly.
Use the HTTP API URL for application searches, or run direct queries inside the
OpenSearch container using the helper in
[Manually search and verify movie data](docs/opensearch-service/README.md#manually-search-and-verify-movie-data).

## Local vs real AWS

Use `cdklocal` with the Floci environment for local deployments. Use `cdk` with
real AWS credentials and region settings for AWS deployments. Switching the
command alone does not clear local credentials or endpoint overrides.

Before targeting AWS, use a shell configured for your intended AWS profile and
region. Remove Floci's `AWS_ENDPOINT_URL`, `AWS_ENDPOINT_URL_S3`, any other
service endpoint overrides, and its test credentials from that shell. Check
profile-level endpoint settings too. Ensure `CDK_DEFAULT_ACCOUNT` and
`CDK_DEFAULT_REGION`, if set explicitly, refer to the intended AWS environment.

```bash
# Verify the intended AWS account and selected region after configuring the shell.
aws sts get-caller-identity
aws configure list

# Review the selected stack using the normal AWS CDK CLI.
npx cdk diff OpenSearchServiceStack
```

Account `000000000000` indicates the local Floci environment. Review the actual
account before any AWS deployment. The repository is a local demo, and AWS
readiness requires additional work: the search API is public and unauthenticated,
S3 bucket names are fixed, removal policies can delete data, and ingestion is
missing some AWS permissions. See
[OpenSearch permissions](docs/opensearch-service/README.md#opensearch-permissions)
for the current permission boundaries and gaps.
