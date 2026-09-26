# Local AWS Development with Floci + TypeScript CDK

This project uses:

* Floci for local AWS emulation
* AWS CLI v2
* AWS CDK v2 with TypeScript
* `aws-cdk-local` (`cdklocal`) to deploy CDK stacks to Floci

## Projects

| Project | Description |
| --- | --- |
| [Event Collector Service](docs/event-collector-service/README.md) | An event ingestion pipeline using API Gateway, Lambda, Kinesis, Firehose, S3, Glue, and Athena. |
| [OpenSearch Movie Search Service](docs/opensearch-service/README.md) | Weekly movie ingestion from S3 into OpenSearch, triggered by EventBridge and processed by Lambda. |

### 1. Install prerequisites

Install Node.js:

```bash
brew install node
```

Install AWS CLI:

```bash
brew install awscli
```

Install Floci:

```bash
brew install floci-io/floci/floci
```

Verify:

```bash
node --version
npm --version
aws --version
floci --version
```

---

## 2. Start Floci

```bash
floci start
```

Load the local AWS environment:

```bash
eval "$(floci env)"
```

`aws-cdk-local` also requires a dedicated S3 endpoint:

```bash
export AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566
```

Verify:

```bash
env | grep '^AWS_'
```

Expected values should include:

```text
AWS_ENDPOINT_URL=http://localhost.floci.io:4566
AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
```

Verify AWS connectivity:

```bash
aws sts get-caller-identity
```

Expected local account:

```text
000000000000    arn:aws:iam::000000000000:root    000000000000
```

---

## 3. Initialize the TypeScript CDK project

From the root of the empty repository:

```bash
npx aws-cdk init app --language typescript
```

Install `cdklocal`:

```bash
npm install --save-dev aws-cdk-local aws-cdk
```

The project should now contain:

```text
.
├── bin/
├── lib/
├── test/
├── cdk.json
├── package.json
├── package-lock.json
└── tsconfig.json
```

---

## 4. Create the stack

The generated `bin/<project>.ts` should look similar to:

```typescript
#!/usr/bin/env node

import * as cdk from 'aws-cdk-lib';
import { FlociAwsSetupStack } from '../lib/floci-aws-setup-stack';

const app = new cdk.App();

new FlociAwsSetupStack(app, 'FlociAwsSetupStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT ?? '000000000000',
    region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
  },
});
```

---

## 5. Add AWS resources

For example, add an S3 bucket in:

```text
lib/floci-aws-setup-stack.ts
```

```typescript
import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export class FlociAwsSetupStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    new s3.Bucket(this, 'TestBucket', {
      versioned: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });
  }
}
```

CDK will generate the physical bucket name automatically.

---

## 6. Build and synthesize

```bash
npm run build
```

Then:

```bash
npx cdk synth
```

This generates the CloudFormation template locally without deploying anything.

---

## 7. Bootstrap CDK in Floci

Make sure the Floci environment is loaded:

```bash
eval "$(floci env)"
export AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566
```

Then bootstrap:

```bash
npx cdklocal bootstrap
```

This creates the CDK bootstrap stack:

```text
CDKToolkit
```

It also creates the CDK asset bucket used internally by CDK.

You normally only need to bootstrap once.

---

## 8. Deploy the stack

```bash
npx cdklocal deploy
```

Or without confirmation prompts:

```bash
npx cdklocal deploy --require-approval never
```

Verify the CloudFormation stacks:

```bash
aws cloudformation list-stacks
```

Verify S3 buckets:

```bash
aws s3 ls
```

You should see:

* the bucket created by your application stack
* a CDK bootstrap asset bucket created by `CDKToolkit`

---

## 9. Destroy the application stack

```bash
npx cdklocal destroy
```

This removes your application stack and its resources.

It does **not** remove the `CDKToolkit` bootstrap stack.

To inspect remaining stacks:

```bash
aws cloudformation list-stacks
```

The CDK bootstrap resources can normally be left in place and reused.

---

## Recommended local workflow

For each development session:

```bash
floci start

eval "$(floci env)"
export AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566

aws sts get-caller-identity

npm run build
npx cdklocal deploy
```

Check resources:

```bash
aws s3 ls
aws cloudformation list-stacks
```

Destroy the application stack when needed:

```bash
npx cdklocal destroy
```

---

# Troubleshooting

## `InvalidClientTokenId`

### Error

```text
An error occurred (InvalidClientTokenId) when calling the
GetCallerIdentity operation:
The security token included in the request is invalid.
```

If this works:

```bash
aws sts get-caller-identity \
  --endpoint-url http://localhost:4566
```

but this does not:

```bash
aws sts get-caller-identity
```

your AWS CLI is probably too old to use `AWS_ENDPOINT_URL`.

Check:

```bash
aws --version
which -a aws
```

Upgrade using Homebrew:

```bash
brew install awscli
```

On Apple Silicon, the Homebrew version should normally be:

```text
/opt/homebrew/bin/aws
```

If both an old and new AWS CLI exist:

```bash
which -a aws
```

For example:

```text
/opt/homebrew/bin/aws
/usr/local/bin/aws
```

Inspect the old one:

```bash
ls -l /usr/local/bin/aws
```

If it points to:

```text
/usr/local/aws-cli/aws
```

remove the old installation:

```bash
sudo rm /usr/local/bin/aws
sudo rm -rf /usr/local/aws-cli
```

Also remove the old completer if present:

```bash
sudo rm /usr/local/bin/aws_completer 2>/dev/null
```

Refresh the shell:

```bash
hash -r
```

Verify:

```bash
which -a aws
aws --version
```

Then reload Floci:

```bash
eval "$(floci env)"
```

and test:

```bash
aws sts get-caller-identity
```

---

## `AWS_ENDPOINT_URL_S3 must be specified`

### Error

```text
EnvironmentMisconfigurationError:
If specifying 'AWS_ENDPOINT_URL' then
'AWS_ENDPOINT_URL_S3' must be specified
```

This comes from `aws-cdk-local`.

Fix it by setting the S3 endpoint:

```bash
export AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566
```

Verify:

```bash
env | grep '^AWS_ENDPOINT'
```

Expected:

```text
AWS_ENDPOINT_URL=http://localhost.floci.io:4566
AWS_ENDPOINT_URL_S3=http://s3.localhost.floci.io:4566
```

Then retry:

```bash
npx cdklocal bootstrap
npx cdklocal deploy
```

---

## Local vs real AWS

Use:

```bash
npx cdklocal deploy
```

for Floci.

Use:

```bash
npx cdk deploy
```

for real AWS.

Before deploying to real AWS, always verify:

```bash
aws sts get-caller-identity
```

If the account is:

```text
000000000000
```

you are still connected to Floci.
