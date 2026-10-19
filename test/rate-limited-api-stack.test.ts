import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { RateLimitedApiStack } from '../lib/rate-limited-api-stack';

test('REST API uses Lambda and a restricted TTL state table without gateway caching', () => {
  const template = Template.fromStack(new RateLimitedApiStack(new cdk.App(), 'RateApi'));
  template.resourceCountIs('AWS::DynamoDB::Table', 1);
  template.hasResourceProperties('AWS::DynamoDB::Table', {
    BillingMode: 'PAY_PER_REQUEST',
    KeySchema: [{ AttributeName: 'pk', KeyType: 'HASH' }],
    TimeToLiveSpecification: { AttributeName: 'expiresAt', Enabled: true },
  });
  template.hasResourceProperties('AWS::Lambda::Function', {
    Runtime: 'python3.13', Handler: 'response_handler.handler', Timeout: 15,
    Environment: { Variables: {
      TABLE_NAME: Match.anyValue(), RATE_LIMIT: '10', CACHE_TTL_SECONDS: '3600',
    } },
  });
  template.resourceCountIs('AWS::ApiGateway::RestApi', 1);
  template.resourceCountIs('AWS::ApiGatewayV2::Api', 0);
  template.hasResourceProperties('AWS::ApiGateway::Resource', { PathPart: 'response' });
  template.hasResourceProperties('AWS::ApiGateway::Method', {
    HttpMethod: 'GET', AuthorizationType: 'NONE',
    Integration: { Type: 'AWS_PROXY', IntegrationHttpMethod: 'POST', Uri: Match.anyValue() },
  });
  template.hasResourceProperties('AWS::ApiGateway::Stage', {
    StageName: 'dev', CacheClusterEnabled: false,
  });
  template.hasResourceProperties('AWS::Lambda::Permission', {
    Action: 'lambda:InvokeFunction', Principal: 'apigateway.amazonaws.com',
    SourceArn: Match.anyValue(),
  });
  const tableId = Object.keys(template.findResources('AWS::DynamoDB::Table'))[0];
  template.hasResourceProperties('AWS::IAM::Policy', {
    PolicyDocument: { Statement: [{
      Action: ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem'],
      Effect: 'Allow', Resource: { 'Fn::GetAtt': [tableId, 'Arn'] },
    }], Version: '2012-10-17' },
  });
  for (const name of ['ApiId', 'ResponseUrl', 'StateTableName']) {
    template.hasOutput(name, { Value: Match.anyValue() });
  }
});
