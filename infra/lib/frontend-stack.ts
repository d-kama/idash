import * as path from 'node:path';
import { RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
import {
  AllowedMethods,
  CachePolicy,
  Function as CfFunction,
  Distribution,
  FunctionCode,
  FunctionEventType,
  FunctionRuntime,
  GeoRestriction,
  KeyValueStore,
  OriginRequestPolicy,
  ViewerProtocolPolicy,
} from 'aws-cdk-lib/aws-cloudfront';
import { HttpOrigin, S3BucketOrigin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { BlockPublicAccess, Bucket } from 'aws-cdk-lib/aws-s3';
import { BucketDeployment, Source } from 'aws-cdk-lib/aws-s3-deployment';
import type { Construct } from 'constructs';

export interface IdashFrontendStackProps extends StackProps {
  /** デプロイ環境名（例: 'dev'） */
  envName: string;
  /** BFF の API Gateway ドメイン（ホスト名のみ）。`/api/*` の HttpOrigin に使う */
  apiDomain: string;
}

/**
 * フロントエンド配信の infra（CloudFront を唯一の入口とするアクセス制御。ADR-0006）。
 *
 * - サイト配信 = 非公開 S3（OAC）。`/api/*` = BFF の API Gateway（HttpOrigin・キャッシュ無効・
 *   ホスト以外の viewer ヘッダを転送）。
 * - **Basic 認証**: `cloudfront.Function`（JS 2.0）+ `KeyValueStore` を**両 behavior** の
 *   viewer-request に適用。値は CDK では作らず手動投入（public repo 制約。SSM SecureString と
 *   同じ運用）。origin-verify（CloudFront 経由限定化）は後続で本 Function に注入を追加する。
 * - **Geo 制限 allowlist(JP)**。SPA フォールバック（403/404→index.html）は入れない（1ページで
 *   不要なうえ、カスタムエラー応答が `/api/*` のエラーまで書き換える副作用があるため）。
 * - 物理名は付けない（自動命名）。サイトバケットはビルド成果物のみで再生成可能なため DESTROY +
 *   autoDeleteObjects（永続データを持つ batch の S3 とは扱いを変える）。
 */
export class IdashFrontendStack extends Stack {
  /** CloudFront ディストリビューションのドメイン（動作確認 URL） */
  public readonly distributionDomainName: string;

  constructor(scope: Construct, id: string, props: IdashFrontendStackProps) {
    super(scope, id, props);
    const { apiDomain } = props;

    // 非公開サイトバケット（OAC 経由のみ読める）。ビルド成果物のみ = 消えても再生成可能。
    const siteBucket = new Bucket(this, 'SiteBucket', {
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Basic 認証（+将来 origin-verify）の秘密を保持する KVS。値は手動投入（README）。
    const authKvStore = new KeyValueStore(this, 'AuthKeyValueStore');

    const authFunction = new CfFunction(this, 'BasicAuthFunction', {
      runtime: FunctionRuntime.JS_2_0,
      code: FunctionCode.fromFile({ filePath: path.join(__dirname, 'functions/basic-auth.js') }),
      keyValueStore: authKvStore,
    });

    // 両 behavior へ同一 Function を viewer-request で適用（付け漏らすと API が素通しになる）。
    const authAssociation = [
      { function: authFunction, eventType: FunctionEventType.VIEWER_REQUEST },
    ];

    const distribution = new Distribution(this, 'Distribution', {
      defaultRootObject: 'index.html',
      geoRestriction: GeoRestriction.allowlist('JP'),
      defaultBehavior: {
        origin: S3BucketOrigin.withOriginAccessControl(siteBucket),
        viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        functionAssociations: authAssociation,
      },
      additionalBehaviors: {
        // `/api/*` は BFF へパススルー（FastAPI が `/api/visualization` を解決）。read-only。
        '/api/*': {
          origin: new HttpOrigin(apiDomain),
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: CachePolicy.CACHING_DISABLED,
          originRequestPolicy: OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
          allowedMethods: AllowedMethods.ALLOW_GET_HEAD,
          functionAssociations: authAssociation,
        },
      },
    });

    // ビルド済み dist を配備し、デプロイ時に CloudFront をインバリデートする。
    // synth 時に dist の存在が必要（Taskfile で synth を build-front に依存させる）。
    new BucketDeployment(this, 'DeploySite', {
      sources: [Source.asset(path.join(__dirname, '../../apps/frontend/dist'))],
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    this.distributionDomainName = distribution.distributionDomainName;
  }
}
