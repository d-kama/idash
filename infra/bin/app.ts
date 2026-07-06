#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import { IdashBatchStack } from '../lib/batch-stack.js';
import { IdashBffStack } from '../lib/bff-stack.js';
import { IdashFrontendStack } from '../lib/frontend-stack.js';

const app = new App();

const envName = app.node.tryGetContext('env') ?? 'dev';

// account は env-agnostic（undefined）。region のみ固定。
const env = { region: 'ap-northeast-1' };

// Batch → Bff → Frontend の順にインスタンス化し、S3 / API ドメインをプロパティ渡しで配線する
// （クロススタック参照より明示的。既定方針どおり）。
const batch = new IdashBatchStack(app, `Idash-${envName}-Batch`, { envName, env });

const bff = new IdashBffStack(app, `Idash-${envName}-Bff`, {
  envName,
  env,
  dataBucket: batch.dataBucket,
  dataLocation: batch.dataLocation,
});

new IdashFrontendStack(app, `Idash-${envName}-Frontend`, {
  envName,
  env,
  apiDomain: bff.apiDomain,
});
