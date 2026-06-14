import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { describe, expect, it } from 'vitest';
import { IdashBatchStack } from '../lib/batch-stack.js';

describe('IdashBatchStack', () => {
  it('matches the CloudFormation snapshot', () => {
    const app = new App();
    const stack = new IdashBatchStack(app, 'Idash-dev-Batch', {
      envName: 'dev',
      env: { region: 'ap-northeast-1' },
    });

    expect(Template.fromStack(stack)).toMatchSnapshot();
  });
});
