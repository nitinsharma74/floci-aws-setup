import * as cdk from 'aws-cdk-lib';
import { Function, Runtime, Code } from 'aws-cdk-lib/aws-lambda';
import { Bucket, EventType } from 'aws-cdk-lib/aws-s3';
import { LambdaDestination } from 'aws-cdk-lib/aws-s3-notifications';
import { Construct } from 'constructs';

export class TestStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create a S3 buckets
    // 1. Raw Data Bucket
    const rawBucket = new Bucket(this, 'RawDataBucket', {
        bucketName: 'test-stack-raw-data-bucket',
        removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // 2. Processed files bucket
    const processedBucket = new Bucket(this, 'ProcessedDataBucket', {
      bucketName: 'test-stack-processed-data-bucket',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Creating the Lambda Function to process data
    const processingLambda = new Function(this, 'TestLambda', {
      functionName: 'test-stack-data-processing-lambda',
      runtime: Runtime.PYTHON_3_13,
      handler: 'test_stack_data_processing_lambda_handler.handler',
      code: Code.fromAsset(
        'stacks/test-stack/lambda/test_stack_data_processing_lambda'
      ),
      // define environment varialbles for the function
      environment: {
        PROCESSED_BUCKET_NAME: processedBucket.bucketName,
      },
    });

    // Lambda can read files from raw bucket
    rawBucket.grantRead(processingLambda);

    // Lambda can write files to processed bucket
    processedBucket.grantWrite(processingLambda);

    // Raw S3 bucket triggers Lambda whenever a file is uploaded
    rawBucket.addEventNotification(
      EventType.OBJECT_CREATED,
      new LambdaDestination(processingLambda)
    );

  }
}