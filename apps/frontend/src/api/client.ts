import type { VisualizationResponse } from './types';

// BFF は CloudFront/dev-proxy 経由で同一オリジンの `/api/*` に載る。認証ヘッダは CloudFront が
// 担うためクライアントからは付けない（origin-verify も CloudFront Function が注入する）。
export async function fetchVisualization(): Promise<VisualizationResponse> {
  const res = await fetch('/api/visualization');
  if (!res.ok) {
    throw new Error(`可視化 API がエラー応答を返しました (HTTP ${res.status})`);
  }
  return (await res.json()) as VisualizationResponse;
}
