import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { TestStack } from '../lib/test-stack';

test('Test Stack Created', () => {
  const app = new cdk.App();

  // WHEN
  const stack = new TestStack(app, 'MyTestStack');

  // THEN
  const template = Template.fromStack(stack);

  // Check 2 S3 buckets were created
  template.resourceCountIs('AWS::S3::Bucket', 2);

  // Check raw bucket
  template.hasResourceProperties('AWS::S3::Bucket', {
    BucketName: 'test-stack-raw-data-bucket',
  });

  // Check processed bucket
  template.hasResourceProperties('AWS::S3::Bucket', {
    BucketName: 'test-stack-processed-data-bucket',
  });

  // Check processing Lambda
  template.hasResourceProperties('AWS::Lambda::Function', {
    FunctionName: 'test-stack-data-processing-lambda',
    Runtime: 'python3.13',
    Handler: 'test_stack_data_processing_lambda_handler.handler',
    Environment: {
      Variables: {
        PROCESSED_BUCKET_NAME: Match.anyValue(),
      },
    },
  });

  // Check S3 ObjectCreated trigger
  template.hasResourceProperties('Custom::S3BucketNotifications', {
    NotificationConfiguration: {
      LambdaFunctionConfigurations: Match.arrayWith([
        Match.objectLike({
          Events: ['s3:ObjectCreated:*'],
        }),
      ]),
    },
  });

  // Check S3 has permission to invoke Lambda
  template.hasResourceProperties('AWS::Lambda::Permission', {
    Action: 'lambda:InvokeFunction',
    Principal: 's3.amazonaws.com',
  });
});