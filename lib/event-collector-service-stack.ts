import * as cdk from 'aws-cdk-lib';
import { CfnWorkGroup } from 'aws-cdk-lib/aws-athena';
import { HttpApi, HttpMethod } from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { CfnDatabase, CfnTable } from 'aws-cdk-lib/aws-glue';
import { PolicyStatement, Role, ServicePrincipal } from 'aws-cdk-lib/aws-iam';
import { Stream, StreamMode } from 'aws-cdk-lib/aws-kinesis';
import { CfnDeliveryStream } from 'aws-cdk-lib/aws-kinesisfirehose';
import { Code, Function, Runtime, StartingPosition } from 'aws-cdk-lib/aws-lambda';
import { KinesisEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { BlockPublicAccess, Bucket } from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export class EventCollectorServiceStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // #########################################
    // S3 Bucket Setup
    // #########################################

    const rawEventsBucket = new Bucket(this, 'RawEventsBucket', {
      bucketName: 'event-collector-service-raw-events',
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // #########################################
    // Kinesis Setup
    // #########################################

    const eventsStream = new Stream(this, 'EventsStream', {
      streamName: 'event-collector-service-events-stream',
      streamMode: StreamMode.ON_DEMAND, // ON_DEMAND, PROVISIONED
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // #########################################
    // Firehose Setup
    // #########################################

    const firehoseRole = new Role(this, 'FirehoseRole', {
      assumedBy: new ServicePrincipal('firehose.amazonaws.com'),
    });

    rawEventsBucket.grantWrite(firehoseRole);

    const eventsDeliveryStream = new CfnDeliveryStream(this, 'EventsDeliveryStream', {
      deliveryStreamName: 'event-collector-service-events-delivery-stream',
      deliveryStreamType: 'DirectPut', // DirectPut, KinesisStreamAsSource, MSKAsSource, DatabaseAsSource
      extendedS3DestinationConfiguration: {
        bucketArn: rawEventsBucket.bucketArn,
        roleArn: firehoseRole.roleArn,
        bufferingHints: {
          intervalInSeconds: 60, // 0-900
          sizeInMBs: 5, // 1-128
        },
        compressionFormat: 'GZIP', // UNCOMPRESSED, GZIP, ZIP, Snappy, HADOOP_SNAPPY
        prefix: 'events/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/',
        errorOutputPrefix: 'errors/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/',
      },
    });

    // #########################################
    // Ingestion Lambda Setup
    // #########################################

    const eventsProcessorLambda = new Function(this, 'EventsProcessorLambda', {
      functionName: 'event-collector-service-events-processing-lambda',
      runtime: Runtime.PYTHON_3_13,
      handler: 'event_processor_lambda_handler.handler',
      code: Code.fromAsset(
        'stacks/event-collector-service-stack/lambda/event-processor-lambda'
      ),
      environment: {
        KINESIS_STREAM_NAME: eventsStream.streamName,
      },
    });

    eventsStream.grantWrite(eventsProcessorLambda);

    // #########################################
    // Kinesis -> Firehose Lambda Setup
    // #########################################

    const kinesisToFirehoseLambda = new Function(this, 'KinesisToFirehoseLambda', {
      functionName: 'event-collector-service-kinesis-to-firehose-lambda',
      runtime: Runtime.PYTHON_3_13,
      handler: 'kinesis_to_firehose_lambda_handler.handler',
      code: Code.fromAsset(
        'stacks/event-collector-service-stack/lambda/kinesis-to-firehose-lambda'
      ),
      environment: {
        FIREHOSE_DELIVERY_STREAM_NAME: eventsDeliveryStream.ref,
      },
    });

    kinesisToFirehoseLambda.addToRolePolicy(
      new PolicyStatement({
        actions: ['firehose:PutRecord', 'firehose:PutRecordBatch'],
        resources: [eventsDeliveryStream.attrArn],
      }),
    );

    kinesisToFirehoseLambda.addEventSource(
      new KinesisEventSource(eventsStream, {
        startingPosition: StartingPosition.LATEST,
        batchSize: 100,
      }),
    );

    // #########################################
    // API Gateway Setup
    // #########################################

    const eventIntegration = new HttpLambdaIntegration(
      'EventCollectorIntegration',
      eventsProcessorLambda,
    );

    const api = new HttpApi(this, 'EventCollectorApi', {
      apiName: 'event-collector-api',
    });

    api.addRoutes({
      path: '/events',
      methods: [HttpMethod.POST],
      integration: eventIntegration,
    });

    // #########################################
    // Glue Setup
    // #########################################

    const eventsDatabase = new CfnDatabase(this, 'EventsDatabase', {
      catalogId: this.account,
      databaseInput: {
        name: 'event_collector',
      },
    });

    const rawEventsTable = new CfnTable(this, 'RawEventsTable', {
      catalogId: this.account,
      databaseName: eventsDatabase.ref,
      tableInput: {
        name: 'raw_events',
        tableType: 'EXTERNAL_TABLE', // EXTERNAL_TABLE, VIRTUAL_VIEW
        parameters: {
          classification: 'json', // json, csv, parquet, avro, orc
          compressionType: 'gzip', // gzip, none
        },
        storageDescriptor: {
          location: `s3://${rawEventsBucket.bucketName}/events/`,
          inputFormat: 'org.apache.hadoop.mapred.TextInputFormat',
          outputFormat: 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat',
          columns: [
            { name: 'eventType', type: 'string' },
            { name: 'eventId', type: 'string' },
            { name: 'appId', type: 'string' },
            { name: 'userId', type: 'string' },
            { name: 'timestamp', type: 'double' },
          ],
          serdeInfo: {
            serializationLibrary: 'org.openx.data.jsonserde.JsonSerDe',
          },
        },
        partitionKeys: [],
      },
    });

    rawEventsTable.addResourceDependency(eventsDatabase);

    // #########################################
    // Athena Setup
    // #########################################

    const athenaResultsBucket = new Bucket(this, 'AthenaResultsBucket', {
      bucketName: 'event-collector-service-athena-results',
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new CfnWorkGroup(this, 'AthenaWorkGroup', {
      name: 'event-collector-service-workgroup',
      workGroupConfiguration: {
        enforceWorkGroupConfiguration: true,
        resultConfiguration: {
          outputLocation: `s3://${athenaResultsBucket.bucketName}/results/`,
        },
      },
    });

    // #########################################
    // CloudFormation Outputs
    // #########################################

    new cdk.CfnOutput(this, 'EventCollectorApiUrl', {
      value: api.apiEndpoint,
    });

    new cdk.CfnOutput(this, 'RawBucketName', {
      value: rawEventsBucket.bucketName,
    });

    new cdk.CfnOutput(this, 'KinesisStreamName', {
      value: eventsStream.streamName,
    });

    new cdk.CfnOutput(this, 'FirehoseDeliveryStreamName', {
      value: eventsDeliveryStream.ref,
    });
  }
}