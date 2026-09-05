#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';

// Stacks to be deployed as part of this app
import { DataSanitizationStack } from '../lib/data-sanitization-stack';
import { TestStack } from '../lib/test-stack';

const app = new cdk.App();

// AWS Setup - right now I am using floci, hence it's defaulting to account number 000000000000
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT ?? '000000000000',
  region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
};

new DataSanitizationStack(app, 'DataSanitizationStack', {
  env,
});

new TestStack(app, 'TestStack', {
  env,
});