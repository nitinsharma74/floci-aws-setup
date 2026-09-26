import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
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
