#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { FlociAwsSetupStack } from '../lib/floci-aws-setup-stack';

const app = new cdk.App();
new FlociAwsSetupStack(app, 'InfraStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT ?? '000000000000',
    region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
  },
});
