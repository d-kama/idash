import { Duration, RemovalPolicy, Stack, type StackProps, TimeZone } from 'aws-cdk-lib';
import { Code, Function as LambdaFunction, Runtime } from 'aws-cdk-lib/aws-lambda';
import { LogGroup, RetentionDays } from 'aws-cdk-lib/aws-logs';
import { Schedule, ScheduleExpression } from 'aws-cdk-lib/aws-scheduler';
import { LambdaInvoke } from 'aws-cdk-lib/aws-scheduler-targets';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import type { Construct } from 'constructs';

export interface IdashBatchStackProps extends StackProps {
  /** デプロイ環境名（例: 'dev'）。SSM パラメータ名・環境変数に使用 */
  envName: string;
}

/**
 * データ収集バッチの infra。
 *
 * Phase 1（issue-2）の最小実装: collect（データ収集）Lambda のみ。
 * - Lambda はプレースホルダ zip（`Code.fromInline` / `Runtime.PYTHON_3_13`）。
 *   コンテナ化（`DockerImageFunction`）は Phase 3 で差替。
 * - notify（サマリ通知）Lambda は Phase 4（TODO）。
 */
export class IdashBatchStack extends Stack {
  constructor(scope: Construct, id: string, props: IdashBatchStackProps) {
    super(scope, id, props);
    const { envName } = props;

    const sheetsSaParamName = `/idash/${envName}/sheets-sa`;
    const sourceLoginParamName = `/idash/${envName}/source-login`;

    // SSM SecureString は CDK では作成しない（CloudFormation が SecureString を作成不可）。
    // 事前作成済みパラメータを名前でインポートする。
    const sheetsSaParam = StringParameter.fromSecureStringParameterAttributes(
      this,
      'SheetsSaForCollect',
      { parameterName: sheetsSaParamName },
    );
    const sourceLoginParam = StringParameter.fromSecureStringParameterAttributes(
      this,
      'SourceLogin',
      { parameterName: sourceLoginParamName },
    );

    // CloudWatch Logs を明示作成（保持 7 日 + スタック削除時に破棄）。
    const collectLogGroup = new LogGroup(this, 'CollectFnLogGroup', {
      logGroupName: `/aws/lambda/${id}-CollectFn`,
      retention: RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // データ収集 Lambda（Phase 1 はプレースホルダ）。
    const collectFn = new LambdaFunction(this, 'CollectFn', {
      functionName: `${id}-CollectFn`,
      runtime: Runtime.PYTHON_3_13,
      handler: 'index.handler',
      code: Code.fromInline(
        'def handler(event, context):\n    return {"status": "placeholder"}\n',
      ),
      memorySize: 1024,
      timeout: Duration.minutes(5),
      reservedConcurrentExecutions: 1, // 同時実行ハードキャップ（コスト暴発対策）
      logGroup: collectLogGroup,
      environment: {
        ENV_NAME: envName,
        SHEETS_SA_PARAM_ARN: sheetsSaParam.parameterArn,
        SOURCE_LOGIN_PARAM_ARN: sourceLoginParam.parameterArn,
      },
    });

    // SSM 読取権限（aws/ssm マネージドキーのため kms:Decrypt の明示付与は不要）。
    sheetsSaParam.grantRead(collectFn);
    sourceLoginParam.grantRead(collectFn);

    // 収集スケジュール: 日次 JST 09:00（Asia/Tokyo）。
    new Schedule(this, 'DailyCollect', {
      schedule: ScheduleExpression.cron({
        minute: '0',
        hour: '9',
        timeZone: TimeZone.ASIA_TOKYO,
      }),
      target: new LambdaInvoke(collectFn, {}),
    });
  }
}
