import * as cdk from 'aws-cdk-lib';
import { Domain, EngineVersion } from 'aws-cdk-lib/aws-opensearchservice';
import { Code, Function, Runtime } from 'aws-cdk-lib/aws-lambda';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { Rule, Schedule } from 'aws-cdk-lib/aws-events';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { Construct } from 'constructs';

export class OpensearchServiceStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const domainName = 'movies-search';

    // S3 bucket to store the movies dataset
    const rawBucket = new Bucket(this, 'MoviesDataBucket', {
      bucketName: 'movies-data-bucket',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // OpenSearch cluster
    const searchDomain = new Domain(this, 'MoviesSearchDomain', {
      // Name of the OpenSearch domain
      domainName,
      // OpenSearch engine version
      version: EngineVersion.OPENSEARCH_2_11,
      // Compute configuration for the cluster
      capacity: {
        // Number of data nodes
        dataNodes: 1,
        // Instance type used by each data node
        dataNodeInstanceType: 't3.small.search',
        // Disable Multi-AZ with Standby for this single-node development cluster
        multiAzWithStandbyEnabled: false,
      },
      // EBS = Elastic Block Store, used to persist OpenSearch data
      ebs: {
        // Attach EBS-backed storage to the OpenSearch node
        enabled: true,
        // Size of the EBS volume in GiB
        volumeSize: 10,
      },
      // Delete the domain when the stack is destroyed
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const ingestionLambda = new Function(this, 'IngestionLambda', {
      functionName: 'opensearch-stack-ingestion-lambda',
      runtime: Runtime.PYTHON_3_13,
      handler: 'opensearch_ingestion_lambda.handler',
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      code: Code.fromAsset(
        'stacks/opensearch-service-stack/lambda/opensearch_ingestion_lambda',
        {
          bundling: {
            image: Runtime.PYTHON_3_13.bundlingImage,
            command: [
              'bash',
              '-c',
              'pip install -r requirements.txt -t /asset-output && cp -au . /asset-output',
            ],
          },
        },
      ),
      environment: {
        // Floci's CloudFormation Ref can return a synthetic ID for this domain.
        OPENSEARCH_DOMAIN: domainName,
        OPENSEARCH_INDEX: 'movies',
        MOVIES_BUCKET: rawBucket.bucketName,
        MOVIES_KEY: 'raw/movies.csv',
      },
    });

    // EventBridge scheduled rules use UTC: every Sunday at 01:00.
    new Rule(this, 'WeeklyMoviesIngestionRule', {
      description: 'Ingest movies every Sunday at 01:00 UTC',
      schedule: Schedule.cron({ minute: '0', hour: '1', weekDay: 'SUN' }),
      targets: [new LambdaFunction(ingestionLambda)],
    });

    // Lambda responsible for searching movies
    const searchLambda = new Function(this, 'SearchLambda', {
      functionName: 'opensearch-stack-search-lambda',
      runtime: Runtime.PYTHON_3_13,
      handler: 'opensearch_search_lambda.handler',
      code: Code.fromAsset(
        'stacks/opensearch-service-stack/lambda/opensearch_search_lambda'
      ),
      environment: {
        OPENSEARCH_ENDPOINT: searchDomain.domainEndpoint,
        OPENSEARCH_INDEX: 'movies',
      },
    });

    // Ingestion Lambda needs to read the movies dataset from S3
    rawBucket.grantRead(ingestionLambda);

    // Ingestion Lambda needs to write documents to the movies index
    searchDomain.grantIndexWrite('movies', ingestionLambda);

    // Search Lambda only needs to read/search the movies index
    searchDomain.grantIndexRead('movies', searchLambda);
  }
}
