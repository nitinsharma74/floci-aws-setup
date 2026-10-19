import * as cdk from 'aws-cdk-lib';
import { LambdaIntegration, RestApi } from 'aws-cdk-lib/aws-apigateway';
import { AttributeType, BillingMode, Table } from 'aws-cdk-lib/aws-dynamodb';
import { PolicyStatement } from 'aws-cdk-lib/aws-iam';
import { Code, Function, Runtime } from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';

export class RateLimitedApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const table = new Table(this, 'ApiState', {
      partitionKey: { name: 'pk', type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'expiresAt',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const handler = new Function(this, 'ResponseHandler', {
      runtime: Runtime.PYTHON_3_13,
      handler: 'response_handler.handler',
      code: Code.fromAsset('stacks/rate-limited-api-stack/lambda/response'),
      timeout: cdk.Duration.seconds(15),
      environment: {
        TABLE_NAME: table.tableName,
        RATE_LIMIT: '10',
        CACHE_TTL_SECONDS: '3600',
      },
    });
    handler.addToRolePolicy(new PolicyStatement({
      actions: ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem'],
      resources: [table.tableArn],
    }));

    const api = new RestApi(this, 'Api', {
      restApiName: 'rate-limited-api',
      cloudWatchRole: false,
      deployOptions: { stageName: 'dev', cacheClusterEnabled: false },
    });
    api.root.addResource('response').addMethod('GET', new LambdaIntegration(handler));

    new cdk.CfnOutput(this, 'ApiId', { value: api.restApiId });
    new cdk.CfnOutput(this, 'ResponseUrl', { value: api.urlForPath('/response') });
    new cdk.CfnOutput(this, 'StateTableName', { value: table.tableName });
  }
}
