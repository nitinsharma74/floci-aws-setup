import * as cdk from 'aws-cdk-lib';
import { Function, Runtime, Code } from 'aws-cdk-lib/aws-lambda';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export class OpensearchServiceStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // S3 bucket to store the movies dataset
    const rawBucket = new Bucket(this, 'MoviesDataBucket', {
      bucketName: 'movies-data-bucket',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    
    // Creating the Lambda Function to process data
    const ingestionLambda = new Function(this, 'IngestionLambda', {
      functionName: 'opensearch-stack-ingestion-lambda',
      runtime: Runtime.PYTHON_3_13,
      handler: 'opensearch_ingestion_lambda.handler',
      code: Code.fromAsset(
        'stacks/opensearch-service-stack/lambda/opensearch_ingestion_lambda'
      ),
    });

    // Creating the Lambda Function to process data
    const processingLambda = new Function(this, 'SearchLambda', {
      functionName: 'opensearch-stack-search-lambda',
      runtime: Runtime.PYTHON_3_13,
      handler: 'opensearch_search_lambda.handler',
      code: Code.fromAsset(
        'stacks/opensearch-service-stack/lambda/opensearch_search_lambda'
      ),
    });
  }
};
