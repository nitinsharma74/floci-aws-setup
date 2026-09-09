import * as cdk from 'aws-cdk-lib';
import { HttpApi, HttpMethod } from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { Function, Code, Runtime } from 'aws-cdk-lib/aws-lambda';
import { Bucket, BlockPublicAccess } from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export class EventCollectorServiceStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create a S3 bucket which will store the raw events data
    const rawEventsBucket = new Bucket(this, 'RawEventsBucket', {
      bucketName: 'event-collector-service-raw-events',
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Create the Lambda function to process events
    const eventsProcessorLambda = new Function(this, 'EventsProcessorLambda', {
      functionName: 'event-collector-service-events-processing-lambda',
      runtime: Runtime.PYTHON_3_13,
      handler: 'event-processor-lambda-handler.handler',
      code: Code.fromAsset(
        'stacks/event-collector-service-stack/lambda/event-processor-lambda'
      ),
    });

    // API Gateway -> Lambda integration
    const eventIntegration = new HttpLambdaIntegration(
      'EventCollectorIntegration',
      eventsProcessorLambda,
    );

    // Create the API
    const api = new HttpApi(this, 'EventCollectorApi', {
      apiName: 'event-collector-api',
    });

    api.addRoutes({
      path: '/events',
      methods: [HttpMethod.POST],
      integration: eventIntegration,
    });

    new cdk.CfnOutput(this, 'EventCollectorApiUrl', {
      value: api.apiEndpoint,
    });

    new cdk.CfnOutput(this, 'RawBucketName', {
      value: rawEventsBucket.bucketName,
    });
  }
}