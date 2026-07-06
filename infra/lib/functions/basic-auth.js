// CloudFront Function（runtime JS 2.0）。両 behavior の viewer-request に適用する。
//
// 注意: JS 2.0 はバインディング省略の catch（`catch {`）非対応。しかもデプロイ時に検証されず
// 実行時に SyntaxError → viewer へ 503 になるため、catch は必ず `catch (_e)` の形で書く。
//
// 1) Basic 認証: KVS の `basic-auth` キー（期待値 = `Basic <base64(user:pass)>` 全体）と
//    Authorization ヘッダを照合。不一致/欠落/KVS 未投入なら 401（フェイルクローズ）。
// 2) origin-verify（CloudFront 経由限定化・ADR-0006）: クライアント偽装を無効化するため
//    `x-origin-verify` を必ず削除し、`/api/*` にのみ KVS の `origin-verify` 値を注入して
//    origin（API Gateway）へ転送する。BFF が SSM の期待値と照合し、CloudFront を迂回した
//    直叩きを 403 で弾く。
//
// 値は CDK では投入しない（public repo 制約）。KVS に basic-auth / origin-verify の2キーを
// デプロイ後に手動投入する（README 参照）。origin-verify は SSM にも同一値を投入する。
import cf from 'cloudfront';

const kvs = cf.kvs();

function unauthorized() {
  return {
    statusCode: 401,
    statusDescription: 'Unauthorized',
    headers: { 'www-authenticate': { value: 'Basic' } },
  };
}

// biome-ignore lint/correctness/noUnusedVariables: CloudFront Functions のエントリポイント（名前規約で呼ばれる・export しない）
async function handler(event) {
  const request = event.request;

  // 1) Basic 認証。
  let expectedAuth;
  try {
    expectedAuth = await kvs.get('basic-auth');
  } catch (_e) {
    // KVS 未投入（キー無し）等は認証不能 → フェイルクローズで 401。
    return unauthorized();
  }
  const header = request.headers.authorization;
  if (!header || header.value !== expectedAuth) {
    return unauthorized();
  }

  // 2) origin-verify。クライアント送信値は常に破棄（ALL_VIEWER_EXCEPT_HOST_HEADER で転送される
  //    ため偽装を無効化）。/api/* のみ KVS の秘密値を上書き注入する。
  delete request.headers['x-origin-verify'];
  if (request.uri.startsWith('/api/')) {
    try {
      const secret = await kvs.get('origin-verify');
      request.headers['x-origin-verify'] = { value: secret };
    } catch (_e) {
      // origin-verify 未投入時はヘッダを付けない → BFF が 403（フェイルクローズ）。
    }
  }

  return request;
}
