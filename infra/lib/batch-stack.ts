import * as path from 'node:path';
import { Duration, IgnoreMode, RemovalPolicy, Stack, type StackProps, TimeZone } from 'aws-cdk-lib';
import { DockerImageCode, DockerImageFunction } from 'aws-cdk-lib/aws-lambda';
import { LogGroup, RetentionDays } from 'aws-cdk-lib/aws-logs';
import { BlockPublicAccess, Bucket } from 'aws-cdk-lib/aws-s3';
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
 * collect（データ収集）Lambda のみ（notify は Phase 4 = 別タスク）。
 * - Lambda はコンテナイメージ（`DockerImageFunction.fromImageAsset`）。版ピン chrome を
 *   同梱した `apps/batch/Dockerfile` を build context = リポジトリルートでビルドする
 *   （Docker ビルドは synth ではなく deploy 時に走る）。
 * - スクレイピング失敗時のエラーページ証跡を保存する S3 バケットを併設する
 *   （`S3ErrorPageStore` の書き込み先 = env `ERROR_PAGE_BUCKET`）。
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

    // スクレイピング失敗時のエラーページ証跡（HTML）を保存する S3 バケット。
    // - 公開全面ブロック / 30 日でライフサイクル失効（証跡は短期保持で十分）。
    // - スタック削除時に破棄（DESTROY）。**autoDeleteObjects は付けない**（snapshot を
    //   綺麗に保つ。destroy 前にオブジェクトが残る場合は手動でバケットを空にする運用）。
    const errorPageBucket = new Bucket(this, 'ErrorPageBucket', {
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true, // 非 HTTPS アクセスを拒否（AWS S3.5 ベストプラクティス）。
      lifecycleRules: [{ expiration: Duration.days(30) }],
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // CloudWatch Logs を明示作成（保持 7 日 + スタック削除時に破棄）。
    const collectLogGroup = new LogGroup(this, 'CollectFnLogGroup', {
      logGroupName: `/aws/lambda/${id}-CollectFn`,
      retention: RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // build context = リポジトリルート（COPY packages/ + apps/batch/ のため）。
    // infra/lib から 2 つ上がリポジトリルート。
    const repoRoot = path.join(__dirname, '../..');

    // データ収集 Lambda（版ピン chrome 同梱のコンテナイメージ）。
    // runtime / handler はイメージの CMD が決めるため指定しない。
    // functionName は付けない（CDK 自動命名）。固定名にすると PackageType 変更
    // （Zip⇄Image）等の置換時に新旧で名前衝突し deploy が詰まるため。参照は ARN /
    // オブジェクト経由なので物理名は不要。
    const collectFn = new DockerImageFunction(this, 'CollectFn', {
      code: DockerImageCode.fromImageAsset(repoRoot, {
        file: 'apps/batch/Dockerfile',
        // `.dockerignore` を asset フィンガープリントにも効かせる。これがないと
        // build context 外の dev ファイル（scripts/ や *.local.json 等）の変更でも
        // image asset ハッシュが揺れ、Vitest snapshot が不要に壊れる。
        ignoreMode: IgnoreMode.DOCKER,
      }),
      memorySize: 2048,
      timeout: Duration.minutes(10),
      reservedConcurrentExecutions: 1, // 同時実行ハードキャップ（コスト暴発対策）
      logGroup: collectLogGroup,
      environment: {
        ENV_NAME: envName,
        SHEETS_SA_PARAM_ARN: sheetsSaParam.parameterArn,
        SOURCE_LOGIN_PARAM_ARN: sourceLoginParam.parameterArn,
        ERROR_PAGE_BUCKET: errorPageBucket.bucketName,
      },
    });

    // SSM 読取権限（aws/ssm マネージドキーのため kms:Decrypt の明示付与は不要）。
    sheetsSaParam.grantRead(collectFn);
    sourceLoginParam.grantRead(collectFn);

    // エラーページ保存は PutObject のみ（S3ErrorPageStore.save）→ grantWrite で十分。
    errorPageBucket.grantWrite(collectFn);

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
