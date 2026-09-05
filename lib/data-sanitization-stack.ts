import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';

export class DataSanitizationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    new lambda.Function(this, 'SanitizerLambda', {
      functionName: 'data-sanitizer',
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'data_sanitization_handler.handler',
      code: lambda.Code.fromAsset(
        'stacks/data-sanitization-stack/lambda/sanitizer'
      ),
    });
  }
}