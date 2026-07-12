#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import { IdashBatchStack } from '../lib/batch-stack.js';
import { IdashBffStack } from '../lib/bff-stack.js';
import { IdashFrontendStack } from '../lib/frontend-stack.js';

const app = new App();

const envName = app.node.tryGetContext('env') ?? 'dev';

// account は env-agnostic（undefined）。region のみ固定。
const env = { region: 'ap-northeast-1' };

// Batch → Bff → Frontend の順にインスタンス化し、S3 / API ドメインをプロパティ渡しで配線する。
// 注意: CFn トークン（bff.apiDomain 等）のプロパティ渡しは CloudFormation の Export/ImportValue
// （クロススタック参照）を生成する。使用中の Export は更新・削除できないため、参照元リソース
// （BffHttpApi 等）の論理 ID 変更・置換や Bff スタック単独の destroy は、先に Frontend 側の
// 参照を外す（更新/削除する）順序制約が付く。
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
