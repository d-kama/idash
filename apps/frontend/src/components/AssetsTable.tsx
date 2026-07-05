import type { SeriesPoint } from '../api/types';
import { seriesColor } from '../lib/colors';
import { formatSigned, formatYen } from '../lib/format';
import { type Metric, pickMetric } from '../lib/metrics';
import { productUnion } from '../lib/series';

// 商品毎の日別推移テーブル。行=基準日（降順）・列=商品（和集合）＋合計。選択指標のみ表示。
// グラフと同一の色スウォッチで識別を担保し、色覚多様性/低コントラスト時の relief（表ビュー）も兼ねる。
export function AssetsTable({ series, metric }: { series: SeriesPoint[]; metric: Metric }) {
  const products = productUnion(series);
  const rows = [...series].reverse(); // 基準日降順
  const format = metric === 'profit_loss' ? formatSigned : formatYen;

  return (
    <div className="max-h-96 overflow-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
      <table className="min-w-full border-collapse text-right text-sm">
        <thead className="sticky top-0 bg-neutral-50 dark:bg-neutral-900">
          <tr>
            <th className="px-3 py-2 text-left font-medium text-neutral-500 dark:text-neutral-400">
              基準日
            </th>
            {products.map((name, index) => (
              <th
                key={name}
                className="px-3 py-2 font-medium text-neutral-700 dark:text-neutral-200"
              >
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                    style={{ backgroundColor: seriesColor(index) }}
                  />
                  {name}
                </span>
              </th>
            ))}
            <th className="px-3 py-2 font-semibold text-neutral-700 dark:text-neutral-200">合計</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((point) => {
            const byName = new Map(point.products.map((product) => [product.name, product]));
            return (
              <tr
                key={point.base_date}
                className="border-t border-neutral-100 dark:border-neutral-800"
              >
                <td className="px-3 py-1.5 text-left tabular-nums text-neutral-500 dark:text-neutral-400">
                  {point.base_date}
                </td>
                {products.map((name) => {
                  const product = byName.get(name);
                  return (
                    <td
                      key={name}
                      className="px-3 py-1.5 tabular-nums text-neutral-800 dark:text-neutral-100"
                    >
                      {product ? format(pickMetric(product, metric)) : '—'}
                    </td>
                  );
                })}
                <td className="px-3 py-1.5 font-medium tabular-nums text-neutral-900 dark:text-white">
                  {format(pickMetric(point.total, metric))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
