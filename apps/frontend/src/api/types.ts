// 生成型（Pydantic → OpenAPI → openapi-typescript）への薄い別名。
// 生成物 `./generated/schema` は非コミット（task gen-types が生成）。import type のみなので
// ランタイムには残らず、tsc は gen-types 後に解決する。UI/ロジックはこの別名を単一の入口にする。
import type { components } from './generated/schema';

export type VisualizationResponse = components['schemas']['VisualizationResponse'];
export type VisualizationSummary = components['schemas']['VisualizationSummary'];
export type SeriesPoint = components['schemas']['SeriesPoint'];
export type ProductSnapshot = components['schemas']['ProductSnapshot'];
export type AssetAmounts = components['schemas']['AssetAmounts'];
