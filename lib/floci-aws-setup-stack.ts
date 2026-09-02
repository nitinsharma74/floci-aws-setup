import * as cdk from 'aws-cdk-lib/core';
import { Construct } from 'constructs';
import { Bucket } from 'aws-cdk-lib/aws-s3'

export class FlociAwsSetupStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Simple S3 Bucket Creation
    new Bucket(this, 'AppBucket', {
      bucketName: 'my-local-app-bucket',
    });
  }
}
