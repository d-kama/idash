import * as path from 'node:path';
import { Duration, IgnoreMode, RemovalPolicy, Stack, type StackProps, TimeZone } from 'aws-cdk-lib';
import { Alarm, ComparisonOperator, TreatMissingData } from 'aws-cdk-lib/aws-cloudwatch';
import { SnsAction } from 'aws-cdk-lib/aws-cloudwatch-actions';
import { DockerImageCode, DockerImageFunction, type IFunction } from 'aws-cdk-lib/aws-lambda';
import { LogGroup, RetentionDays } from 'aws-cdk-lib/aws-logs';
import { BlockPublicAccess, Bucket } from 'aws-cdk-lib/aws-s3';
import { Schedule, ScheduleExpression } from 'aws-cdk-lib/aws-scheduler';
import { LambdaInvoke } from 'aws-cdk-lib/aws-scheduler-targets';
import { Topic } from 'aws-cdk-lib/aws-sns';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import type { Construct } from 'constructs';

export interface IdashBatchStackProps extends StackProps {
  /** デプロイ環境名（例: 'dev'）。SSM パラメータ名・環境変数に使用 */
  envName: string;
}

/**
 * バッチ（collect / notify）の infra。
 *
 * collect（データ収集・平日 09:00 JST）と notify（サマリ通知・日曜 09:00 JST）の
 * 2 つの Lambda。
 * - Lambda はコンテナイメージ（`DockerImageFunction.fromImageAsset`）。版ピン chrome を
 *   同梱した `apps/batch/Dockerfile` を build context = リポジトリルートでビルドする
 *   （Docker ビルドは synth ではなく deploy 時に走る）。collect / notify は同一イメージを
 *   共有し、`cmd` で関数ごとにハンドラを上書きする（image asset のフィンガープリントは
 *   不変＝1回ビルドして 2 関数が参照）。
 * - スクレイピング失敗時のエラーページ証跡を保存する S3 バケットを併設する
 *   （`S3ErrorPageStore` の書き込み先 = env `ERROR_PAGE_BUCKET`。collect のみ書き込み）。
 */
export class IdashBatchStack extends Stack {
  constructor(scope: Construct, id: string, props: IdashBatchStackProps) {
    super(scope, id, props);
    const { envName } = props;

    const sheetsSaParamName = `/idash/${envName}/sheets-sa`;
    const sourceLoginParamName = `/idash/${envName}/source-login`;
    const notifyLineParamName = `/idash/${envName}/notify-line`;

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
    const notifyLineParam = StringParameter.fromSecureStringParameterAttributes(
      this,
      'NotifyLine',
      { parameterName: notifyLineParamName },
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
    // logGroupName は付けない（CDK 自動命名）。永続化が要るリソース（S3 等）以外は
    // 自動命名に寄せる方針。Lambda へは logGroup 経由（LoggingConfig）で割り当てる。
    const collectLogGroup = new LogGroup(this, 'CollectFnLogGroup', {
      retention: RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // 失敗通知の宛先 SNS Topic（自動命名）。CloudWatch Alarm のアクション先。
    // **Email サブスクは CDK で作らない**（個人アドレスを IaC に残さない。SSM SecureString を
    // 手動作成する既存方針と同じ思想）。デプロイ後に Topic へ手動サブスク＋承認する（README 参照）。
    const alertTopic = new Topic(this, 'BatchAlertTopic');

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

    // 失敗検知アラーム（collect）。例外・timeout・OOM・起動失敗を一律 Lambda `Errors` で拾う。
    this.addErrorsAlarm('CollectErrorsAlarm', collectFn, alertTopic);

    // 収集スケジュール: 平日のみ（Mon–Fri）JST 09:00（Asia/Tokyo）。
    // 土日は更新されず・メンテも多いため日次から平日のみへ縮退（notify の日曜 09:00 とも競合しない）。
    new Schedule(this, 'DailyCollect', {
      schedule: ScheduleExpression.cron({
        minute: '0',
        hour: '9',
        weekDay: 'MON-FRI',
        timeZone: TimeZone.ASIA_TOKYO,
      }),
      // retryAttempts=0: リトライせず即失敗・即アラーム化（ADR-0004）。
      target: new LambdaInvoke(collectFn, { retryAttempts: 0 }),
    });

    // サマリ通知 Lambda（収集と同一イメージを cmd 違いで再利用）。
    // notify は Sheets read + LINE 通知のみで軽量（chrome 起動なし）。memory 512 / timeout 1分。
    const notifyLogGroup = new LogGroup(this, 'NotifyFnLogGroup', {
      retention: RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const notifyFn = new DockerImageFunction(this, 'NotifyFn', {
      code: DockerImageCode.fromImageAsset(repoRoot, {
        file: 'apps/batch/Dockerfile',
        // notify ハンドラを CMD として上書き（image asset は collect と同一＝1回ビルド）。
        cmd: ['batch.handler_notify.handler'],
        ignoreMode: IgnoreMode.DOCKER,
      }),
      memorySize: 512,
      timeout: Duration.minutes(1),
      reservedConcurrentExecutions: 1, // 同時実行ハードキャップ（コスト暴発対策）
      logGroup: notifyLogGroup,
      environment: {
        ENV_NAME: envName,
        SHEETS_SA_PARAM_ARN: sheetsSaParam.parameterArn,
        NOTIFY_LINE_PARAM_ARN: notifyLineParam.parameterArn,
        NOTIFY_DAYS: '7',
      },
    });

    // SSM 読取権限（sheets-sa は read 用に再利用 / notify-line は LINE トークン）。
    // エラーページ S3 は notify では使わないため付与しない。
    sheetsSaParam.grantRead(notifyFn);
    notifyLineParam.grantRead(notifyFn);

    // 失敗検知アラーム（notify）。collect と別アラームにし、どちらが落ちたか即わかるようにする。
    this.addErrorsAlarm('NotifyErrorsAlarm', notifyFn, alertTopic);

    // 通知スケジュール: 週次・日曜 JST 09:00（Asia/Tokyo）。
    new Schedule(this, 'WeeklyNotify', {
      schedule: ScheduleExpression.cron({
        minute: '0',
        hour: '9',
        weekDay: 'SUN',
        timeZone: TimeZone.ASIA_TOKYO,
      }),
      // retryAttempts=0: リトライせず即失敗・即アラーム化（ADR-0004）。
      target: new LambdaInvoke(notifyFn, { retryAttempts: 0 }),
    });
  }

  /**
   * Lambda の `Errors` メトリクスに失敗検知アラームを張り、SNS Topic をアクションに配線する。
   *
   * 低頻度バッチ向けに `Sum ≥ 1` / `evaluationPeriods=1` / `treatMissingData=notBreaching`
   * （データ無しを誤発報しない）。collect / notify で別アラームを作るため fn ごとに呼ぶ。
   * OK（復旧）通知は付けない（次回成功＝復旧が自明なバッチのため不要）。
   */
  private addErrorsAlarm(id: string, fn: IFunction, topic: Topic): void {
    const alarm = new Alarm(this, id, {
      metric: fn.metricErrors({ period: Duration.minutes(5) }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: TreatMissingData.NOT_BREACHING,
    });
    alarm.addAlarmAction(new SnsAction(topic));
  }
}
