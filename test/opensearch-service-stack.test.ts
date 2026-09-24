import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { OpensearchServiceStack } from '../lib/opensearch-service-stack';

test('Test Stack Created', () => {
  const app = new cdk.App();

  // WHEN
  const stack = new OpensearchServiceStack(app, 'MyTestStack');
  
  // THEN
  const template = Template.fromStack(stack);

  // Check search lambda
  template.hasResourceProperties('AWS::Lambda::Function', {
    FunctionName: 'opensearch-stack-search-lambda',
    Runtime: 'python3.13',
    Handler: 'opensearch_search_lambda.handler',
  });
  
});