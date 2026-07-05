import * as fs from 'node:fs';
import * as path from 'node:path';
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { beforeAll, describe, expect, it } from 'vitest';
import { IdashFrontendStack } from '../lib/frontend-stack.js';

const DIST = path.join(__dirname, '../../apps/frontend/dist');

// Source.asset は synth 時に dist の存在を要求する。スナップショットは asset ハッシュを正規化する
// ため中身は問わない。CI/ローカルで dist 未ビルドでもテストが自己完結するようスタブを用意する。
beforeAll(() => {
  if (!fs.existsSync(path.join(DIST, 'index.html'))) {
    fs.mkdirSync(DIST, { recursive: true });
    fs.writeFileSync(path.join(DIST, 'index.html'), '<!doctype html>\n');
  }
});

// CDK の asset ハッシュ（64桁 hex）はフロント/依存の変更で揺れる。フロントの内容は frontend の
// vitest が担保するので、infra スナップショットからはハッシュを正規化し構造差分だけを見る。
function normalize(template: object): unknown {
  return JSON.parse(JSON.stringify(template).replace(/[a-f0-9]{64}/g, 'NORMALIZED_ASSET_HASH'));
}

function synth(): Template {
  const app = new App();
  const stack = new IdashFrontendStack(app, 'Idash-dev-Frontend', {
    envName: 'dev',
    env: { region: 'ap-northeast-1' },
    // 実配線では BFF の apiEndpoint 由来トークン。テストはスタック単体で見るため固定値。
    apiDomain: 'example.execute-api.ap-northeast-1.amazonaws.com',
  });
  return Template.fromStack(stack);
}

describe('IdashFrontendStack', () => {
  it('matches the CloudFormation snapshot', () => {
    expect(normalize(synth().toJSON())).toMatchSnapshot();
  });

  it('applies the basic-auth function to BOTH behaviors (viewer-request)', () => {
    // 付け漏らすと /api が素通しになる（未確定事項・リスク）。両 behavior の関連付けを固定検証。
    const config = Object.values(synth().findResources('AWS::CloudFront::Distribution'))[0]
      .Properties.DistributionConfig;
    const behaviors = [config.DefaultCacheBehavior, ...config.CacheBehaviors];
    expect(behaviors).toHaveLength(2);
    for (const behavior of behaviors) {
      expect(behavior.FunctionAssociations).toEqual([
        { EventType: 'viewer-request', FunctionARN: expect.anything() },
      ]);
    }
  });

  it('restricts geography to JP', () => {
    synth().hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: {
        Restrictions: { GeoRestriction: { RestrictionType: 'whitelist', Locations: ['JP'] } },
      },
    });
  });

  it('disables caching on the /api/* behavior', () => {
    const config = Object.values(synth().findResources('AWS::CloudFront::Distribution'))[0]
      .Properties.DistributionConfig;
    // CachePolicyId = managed CACHING_DISABLED（4135ea2d-...）。既定 behavior と異なることを確認。
    expect(config.CacheBehaviors[0].PathPattern).toBe('/api/*');
    expect(config.CacheBehaviors[0].CachePolicyId).not.toBe(
      config.DefaultCacheBehavior.CachePolicyId,
    );
  });
});
