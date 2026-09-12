import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { EventCollectorServiceStack } from '../lib/event-collector-service-stack';

test('Test Stack Created', () => {
  const app = new cdk.App();
  const stack = new EventCollectorServiceStack(app, 'MyEventCollectorServiceStack');
  const template = Template.fromStack(stack);

  template.resourceCountIs('AWS::S3::Bucket', 2);

  template.hasResourceProperties('AWS::S3::Bucket', {
    BucketName: 'event-collector-service-raw-events',
  });

  template.hasResourceProperties('AWS::S3::Bucket', {
    BucketName: 'event-collector-service-athena-results',
  });

  template.hasResourceProperties('AWS::IAM::Role', {
    AssumeRolePolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({
          Effect: 'Allow',
          Principal: {
            Service: 'firehose.amazonaws.com',
          },
          Action: 'sts:AssumeRole',
        }),
      ]),
    },
  });

  template.resourceCountIs('AWS::KinesisFirehose::DeliveryStream', 1);
  template.hasResourceProperties('AWS::KinesisFirehose::DeliveryStream', {
    DeliveryStreamName: 'event-collector-service-events-delivery-stream',
    DeliveryStreamType: 'DirectPut',
    ExtendedS3DestinationConfiguration: Match.objectLike({
      BufferingHints: {
        IntervalInSeconds: 60,
        SizeInMBs: 5,
      },
      CompressionFormat: 'GZIP',
      Prefix:
        'events/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/',
      ErrorOutputPrefix:
        'errors/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/',
    }),
  });

  template.resourceCountIs('AWS::Lambda::Function', 1);
  template.hasResourceProperties('AWS::Lambda::Function', {
    FunctionName: 'event-collector-service-events-processing-lambda',
    Runtime: 'python3.13',
    Handler: 'event-processor-lambda-handler.handler',
    Environment: {
      Variables: Match.objectLike({
        FIREHOSE_DELIVERY_STREAM_NAME: Match.anyValue(),
      }),
    },
  });

  template.hasResourceProperties('AWS::IAM::Policy', {
    PolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({
          Effect: 'Allow',
          Action: Match.arrayWith([
            'firehose:PutRecord',
            'firehose:PutRecordBatch',
          ]),
        }),
      ]),
    },
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

  template.resourceCountIs('AWS::Glue::Database', 1);
  template.hasResourceProperties('AWS::Glue::Database', {
    DatabaseInput: {
      Name: 'event_collector',
    },
  });

  template.resourceCountIs('AWS::Glue::Table', 1);
  template.hasResourceProperties('AWS::Glue::Table', {
    DatabaseName: Match.anyValue(),
    TableInput: {
      Name: 'raw_events',
      TableType: 'EXTERNAL_TABLE',
      Parameters: {
        classification: 'json',
        compressionType: 'gzip',
      },
      StorageDescriptor: Match.objectLike({
        Location: Match.anyValue(),
        InputFormat: 'org.apache.hadoop.mapred.TextInputFormat',
        OutputFormat:
          'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat',
        Columns: [
          { Name: 'eventType', Type: 'string' },
          { Name: 'eventId', Type: 'string' },
          { Name: 'appId', Type: 'string' },
          { Name: 'userId', Type: 'string' },
          { Name: 'timestamp', Type: 'double' },
        ],
        SerdeInfo: {
          SerializationLibrary: 'org.openx.data.jsonserde.JsonSerDe',
        },
      }),
      PartitionKeys: [],
    },
  });

  template.resourceCountIs('AWS::Athena::WorkGroup', 1);
  template.hasResourceProperties('AWS::Athena::WorkGroup', {
    Name: 'event-collector-service-workgroup',
    WorkGroupConfiguration: {
      EnforceWorkGroupConfiguration: true,
      ResultConfiguration: {
        OutputLocation: Match.anyValue(),
      },
    },
  });
});
