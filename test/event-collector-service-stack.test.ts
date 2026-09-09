import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { EventCollectorServiceStack } from '../lib/event-collector-service-stack';

test('Test Stack Created', () => {
  const app = new cdk.App();

  const stack = new EventCollectorServiceStack(app, 'MyEventCollectorServiceStack');

  const template = Template.fromStack(stack);

  template.resourceCountIs('AWS::S3::Bucket', 1);

  template.hasResourceProperties('AWS::S3::Bucket', {
    BucketName: 'event-collector-service-raw-events',
  });

  template.resourceCountIs('AWS::Lambda::Function', 1);

  template.hasResourceProperties('AWS::Lambda::Function', {
    FunctionName: 'event-collector-service-events-processing-lambda',
    Runtime: 'python3.13',
    Handler: 'event-processor-lambda-handler.handler',
  });

  template.resourceCountIs('AWS::ApiGatewayV2::Api', 1);

  template.hasResourceProperties('AWS::ApiGatewayV2::Api', {
    Name: 'event-collector-api',
    ProtocolType: 'HTTP',
  });

  template.resourceCountIs('AWS::ApiGatewayV2::Integration', 1);

  template.hasResourceProperties('AWS::ApiGatewayV2::Integration', {
    IntegrationType: 'AWS_PROXY',
    PayloadFormatVersion: '2.0',
  });

  template.resourceCountIs('AWS::ApiGatewayV2::Route', 1);

  template.hasResourceProperties('AWS::ApiGatewayV2::Route', {
    RouteKey: 'POST /events',
    AuthorizationType: 'NONE',
  });

  template.hasResourceProperties('AWS::ApiGatewayV2::Stage', {
    StageName: '$default',
    AutoDeploy: true,
  });
});