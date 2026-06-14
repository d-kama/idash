#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import { IdashBatchStack } from '../lib/batch-stack.js';

const app = new App();

const envName = app.node.tryGetContext('env') ?? 'dev';

new IdashBatchStack(app, `Idash-${envName}-Batch`, {
  envName,
  // account は env-agnostic（undefined）。region のみ固定。
  env: { region: 'ap-northeast-1' },
});
