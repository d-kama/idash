import { App } from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { describe, expect, it } from 'vitest';
import { IdashBatchStack } from '../lib/batch-stack.js';
import { IdashBffStack } from '../lib/bff-stack.js';

describe('IdashBffStack', () => {
  const synth = () => {
    const app = new App();
    // データストア（S3）をプロパティ渡しで受け取るため batch を先にインスタンス化する。
    const batch = new IdashBatchStack(app, 'Idash-dev-Batch', {
      envName: 'dev',
      env: { region: 'ap-northeast-1' },
    });
    const stack = new IdashBffStack(app, 'Idash-dev-Bff', {
      envName: 'dev',
      env: { region: 'ap-northeast-1' },
      dataBucket: batch.dataBucket,
      dataLocation: batch.dataLocation,
    });
    return Template.fromStack(stack);
  };

  it('matches the CloudFormation snapshot', () => {
    expect(synth()).toMatchSnapshot();
  });

  it('throttles the default stage (cost guard)', () => {
    // 重要な値（コスト暴発対策のスロットリング）は fine-grained でも固定する。
    synth().hasResourceProperties('AWS::ApiGatewayV2::Stage', {
      StageName: '$default',
      DefaultRouteSettings: { ThrottlingBurstLimit: 40, ThrottlingRateLimit: 20 },
    });
  });

  it('caps concurrency on the BFF function (cost guard)', () => {
    synth().hasResourceProperties('AWS::Lambda::Function', {
      ReservedConcurrentExecutions: 3,
    });
  });

  it('wires ORIGIN_VERIFY_PARAM_ARN into the function environment (security guard)', () => {
    // BFF は fail-closed（この env が無いと起動時エラー）だが、配線の欠落自体はスナップショット
    // 差分にしか出ず test:update で黙って通りうるため、直接アサートで固定する。
    synth().hasResourceProperties('AWS::Lambda::Function', {
      Environment: {
        Variables: Match.objectLike({
          ORIGIN_VERIFY_PARAM_ARN: Match.anyValue(),
        }),
      },
    });
  });
});
