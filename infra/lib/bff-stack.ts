import * as path from 'node:path';
import { Duration, Fn, IgnoreMode, RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
import { HttpApi, HttpMethod, HttpStage } from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { DockerImageCode, DockerImageFunction } from 'aws-cdk-lib/aws-lambda';
import { LogGroup, RetentionDays } from 'aws-cdk-lib/aws-logs';
import type { IBucket } from 'aws-cdk-lib/aws-s3';
import type { Construct } from 'constructs';

export interface IdashBffStackProps extends StackProps {
  /** デプロイ環境名（例: 'dev'）。環境変数 ENV_NAME に渡す */
  envName: string;
  /** データストア（単一 Parquet）を格納する S3 バケット。read 権限を付与する */
  dataBucket: IBucket;
  /** データストアの単一 Parquet の S3 URI（環境変数 DATA_LOCATION に渡す） */
  dataLocation: string;
}

/**
 * BFF（可視化 API）の infra。
 *
 * - Lambda はコンテナイメージ（`DockerImageFunction.fromImageAsset`）。chrome を除いた縮小版
 *   `apps/bff/Dockerfile` を build context = リポジトリルートでビルドする。image asset の
 *   `exclude`（apps/batch）で batch イメージとハッシュを相互分離する（共有 `.dockerignore` は
 *   両アプリを許可）。
 * - 公開は HTTP API（API Gateway v2）。`$default` ステージに低めのスロットリングを掛けて
 *   個人利用のコスト暴発を抑える。予約同時実行 3 も同目的（Lambda 側ハードキャップ）。
 * - この時点では CloudFront 未経由・素の API GW（Phase 5）。Basic 認証 / Geo 制限は Phase 6 の
 *   IdashFrontendStack（CloudFront）で前段に付く。API ドメインは公開プロパティで frontend へ渡す。
 *
 * データストアは read のみ（可視化は書き込まない）。物理名は付けない（自動命名。永続リソースは
 * batch スタックの S3 のみ）。
 */
export class IdashBffStack extends Stack {
  /**
   * API Gateway のドメイン（ホスト名のみ、スキーム/パスなし）。
   * IdashFrontendStack の CloudFront `/api/*` behavior の HttpOrigin に渡す。
   */
  public readonly apiDomain: string;

  constructor(scope: Construct, id: string, props: IdashBffStackProps) {
    super(scope, id, props);
    const { envName, dataBucket, dataLocation } = props;

    // CloudWatch Logs を明示作成（保持 1 週間 + スタック削除時に破棄）。logGroupName は付けない
    // （CDK 自動命名。永続化が要るリソース以外は自動命名に寄せる方針）。
    const logGroup = new LogGroup(this, 'BffFnLogGroup', {
      retention: RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // build context = リポジトリルート（COPY packages/ + apps/bff/ のため）。infra/lib から 2 つ上。
    const repoRoot = path.join(__dirname, '../..');

    // 可視化 API Lambda（chrome なし縮小イメージ）。runtime/handler はイメージの CMD が決める。
    // functionName は付けない（CDK 自動命名。PackageType 変更時の置換衝突を避ける）。
    const bffFn = new DockerImageFunction(this, 'BffFn', {
      code: DockerImageCode.fromImageAsset(repoRoot, {
        file: 'apps/bff/Dockerfile',
        // `.dockerignore` を asset フィンガープリントにも効かせる（dev ファイル変更での揺れ防止）。
        ignoreMode: IgnoreMode.DOCKER,
        // 共有 `.dockerignore` は apps/batch も許可するため、bff イメージのフィンガープリントからは
        // apps/batch を除外する（batch 側変更でハッシュが揺れない。bff Dockerfile は apps/batch を
        // COPY しないのでイメージ内容は不変）。batch 側は逆に apps/bff を除外している。
        exclude: ['apps/batch'],
      }),
      memorySize: 512,
      // API Gateway の統合タイムアウト上限（29秒）未満に収める。DuckDB コールドスタートの保険。
      timeout: Duration.seconds(29),
      reservedConcurrentExecutions: 3, // 同時実行ハードキャップ（コスト暴発対策）
      logGroup,
      environment: {
        ENV_NAME: envName,
        DATA_LOCATION: dataLocation,
      },
    });

    // データストアは read のみ（可視化は集計して返すだけ・書き込まない）。glob の LIST も含む。
    dataBucket.grantRead(bffFn);

    // HTTP API（API Gateway v2）。既定ステージはスロットリング設定のため手動作成する
    // （createDefaultStage: false）。`/api/*` のみ Lambda へ流し、FastAPI が `/api/visualization`
    // を解決する（CloudFront も `/api/*` を本 API へパススルーする配線に合わせる）。
    const httpApi = new HttpApi(this, 'BffHttpApi', { createDefaultStage: false });
    httpApi.addRoutes({
      path: '/api/{proxy+}',
      methods: [HttpMethod.GET],
      integration: new HttpLambdaIntegration('BffIntegration', bffFn),
    });

    // `$default` ステージを明示作成し、低めのスロットリングを掛ける（個人利用のコスト暴発対策）。
    new HttpStage(this, 'BffDefaultStage', {
      httpApi,
      autoDeploy: true,
      throttle: { rateLimit: 20, burstLimit: 40 },
    });

    // apiEndpoint = `https://{apiId}.execute-api.{region}.amazonaws.com`。CloudFront の HttpOrigin は
    // ホスト名のみを要するためスキームを剥がす（`https://` を split して 3 要素目 = ドメイン）。
    this.apiDomain = Fn.select(2, Fn.split('/', httpApi.apiEndpoint));
  }
}
