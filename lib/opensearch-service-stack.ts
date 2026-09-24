import * as cdk from 'aws-cdk-lib';
import { Function, Runtime, Code } from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';

export class OpensearchServiceStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    
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
