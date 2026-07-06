import type { AssetAmounts } from '../api/types';

/** テーブル・グラフでトグルする指標。DTO の3金額に対応。 */
export type Metric = 'valuation' | 'profit_loss' | 'contribution';

export const METRICS: readonly { key: Metric; label: string }[] = [
  { key: 'valuation', label: '評価額' },
  { key: 'profit_loss', label: '評価損益' },
  { key: 'contribution', label: '拠出累計' },
] as const;

export const METRIC_LABEL: Record<Metric, string> = {
  valuation: '評価額',
  profit_loss: '評価損益',
  contribution: '拠出累計',
};

/** AssetAmounts / ProductSnapshot（AssetAmounts 派生）から指標値を取り出す。 */
export function pickMetric(amounts: AssetAmounts, metric: Metric): number {
  return amounts[metric];
}
