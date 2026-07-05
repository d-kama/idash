// CloudFront Function（runtime JS 2.0）。両 behavior の viewer-request に適用し、
// KeyValueStore の `basic-auth` キー（期待値 = `Basic <base64(user:pass)>` 全体）と
// リクエストの Authorization ヘッダを照合する。不一致/欠落/KVS 未投入なら 401（フェイルクローズ）。
//
// 値は CDK では投入しない（public repo 制約）。デプロイ後に手動投入する（README 参照）。
// origin-verify 注入（/api/* 限定）は後続の変更で本 Function に追加する。
import cf from 'cloudfront';

const kvs = cf.kvs();

function unauthorized() {
  return {
    statusCode: 401,
    statusDescription: 'Unauthorized',
    headers: { 'www-authenticate': { value: 'Basic' } },
  };
}

async function handler(event) {
  const request = event.request;

  let expected;
  try {
    expected = await kvs.get('basic-auth');
  } catch {
    // KVS 未投入（キー無し）等は認証不能 → フェイルクローズで 401。
    return unauthorized();
  }

  const header = request.headers.authorization;
  if (!header || header.value !== expected) {
    return unauthorized();
  }
  return request;
}
