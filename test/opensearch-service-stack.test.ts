import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { OpensearchServiceStack } from '../lib/opensearch-service-stack';

test('creates the movies data bucket and OpenSearch Lambda functions', () => {
  const app = new cdk.App();
  const stack = new OpensearchServiceStack(app, 'MyTestStack');
  const template = Template.fromStack(stack);

  template.resourceCountIs('AWS::S3::Bucket', 1);

  template.hasResourceProperties('AWS::S3::Bucket', {
    BucketName: 'movies-data-bucket',
  });

  template.resourceCountIs('AWS::Lambda::Function', 2);

  template.hasResourceProperties('AWS::OpenSearchService::Domain', {
    DomainName: 'movies-search',
  });

  template.hasResourceProperties('AWS::Lambda::Function', {
    FunctionName: 'opensearch-stack-ingestion-lambda',
    Runtime: 'python3.13',
    Handler: 'opensearch_ingestion_lambda.handler',
    Environment: {
      Variables: {
        OPENSEARCH_DOMAIN: 'movies-search',
      },
    },
  });

  template.hasResourceProperties('AWS::Lambda::Function', {
    FunctionName: 'opensearch-stack-search-lambda',
    Runtime: 'python3.13',
    Handler: 'opensearch_search_lambda.handler',
    Timeout: 25,
    MemorySize: 512,
    Environment: { Variables: { OPENSEARCH_DOMAIN: 'movies-search', OPENSEARCH_INDEX: 'movies' } },
  });

  const searchFunctionId = stack.getLogicalId(
    stack.node.findChild('SearchLambda').node.defaultChild as cdk.CfnResource,
  );
  template.hasResourceProperties('AWS::ApiGatewayV2::Api', {
    Name: 'movies-search-api', ProtocolType: 'HTTP',
  });
  template.hasResourceProperties('AWS::ApiGatewayV2::Route', {
    RouteKey: 'GET /movies/search', AuthorizationType: 'NONE',
    Target: Match.objectLike({ 'Fn::Join': Match.anyValue() }),
  });
  template.hasResourceProperties('AWS::ApiGatewayV2::Integration', {
    IntegrationType: 'AWS_PROXY', PayloadFormatVersion: '2.0',
    IntegrationUri: { 'Fn::GetAtt': [searchFunctionId, 'Arn'] },
  });
  template.hasResourceProperties('AWS::Lambda::Permission', {
    Action: 'lambda:InvokeFunction',
    FunctionName: { 'Fn::GetAtt': [searchFunctionId, 'Arn'] },
    Principal: 'apigateway.amazonaws.com', SourceArn: Match.anyValue(),
  });
  template.hasOutput('MoviesSearchApiId', { Value: Match.anyValue() });
  template.hasOutput('MoviesSearchUrl', { Value: Match.anyValue() });
  const searchRoleId = stack.getLogicalId(
    stack.node.findChild('SearchLambda').node.findChild('ServiceRole').node.defaultChild as cdk.CfnResource,
  );
  const domainId = stack.getLogicalId(
    stack.node.findChild('MoviesSearchDomain').node.defaultChild as cdk.CfnResource,
  );
  const domainArn = { 'Fn::GetAtt': [domainId, 'Arn'] };
  const domainPath = (path: string) => ({ 'Fn::Join': ['', [domainArn, path]] });
  template.hasResourceProperties('AWS::IAM::Policy', {
    Roles: [{ Ref: searchRoleId }],
    PolicyDocument: { Statement: Match.arrayWith([
      Match.objectLike({ Action: 'es:DescribeDomain', Effect: 'Allow', Resource: domainArn }),
      Match.objectLike({ Action: 'es:ESHttpPost', Effect: 'Allow', Resource: Match.arrayWith([
        domainPath('/movies/_search/point_in_time'), domainPath('/_search'),
      ]) }),
      Match.objectLike({ Action: 'es:ESHttpDelete', Effect: 'Allow', Resource: domainPath('/_search/point_in_time') }),
    ]) },
  });

  const ingestionFunctionId = stack.getLogicalId(
    stack.node.findChild('IngestionLambda').node.defaultChild as cdk.CfnResource,
  );
  const ingestionRuleId = stack.getLogicalId(
    stack.node.findChild('WeeklyMoviesIngestionRule').node.defaultChild as cdk.CfnResource,
  );

  template.resourceCountIs('AWS::Events::Rule', 1);
  template.hasResourceProperties('AWS::Events::Rule', {
    ScheduleExpression: 'cron(0 1 ? * SUN *)',
    State: 'ENABLED',
    Targets: [{
      Arn: { 'Fn::GetAtt': [ingestionFunctionId, 'Arn'] },
      Id: 'Target0',
    }],
  });
  template.hasResourceProperties('AWS::Lambda::Permission', {
    Action: 'lambda:InvokeFunction',
    FunctionName: { 'Fn::GetAtt': [ingestionFunctionId, 'Arn'] },
    Principal: 'events.amazonaws.com',
    SourceArn: { 'Fn::GetAtt': [ingestionRuleId, 'Arn'] },
  });

  expect(existsSync(resolve(
    __dirname,
    '../stacks/opensearch-service-stack/lambda/opensearch_ingestion_lambda/opensearch_ingestion_lambda.py',
  ))).toBe(true);

  expect(existsSync(resolve(
    __dirname,
    '../stacks/opensearch-service-stack/lambda/opensearch_search_lambda/opensearch_search_lambda.py',
  ))).toBe(true);
});
