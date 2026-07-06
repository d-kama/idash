import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { SeriesPoint } from '../api/types';
import { AXIS_TICK, axisYen, GRID_STROKE, shortDate, TOOLTIP_STYLE } from '../lib/chart';
import { seriesColor } from '../lib/colors';
import { formatSigned, formatYen } from '../lib/format';
import { type Metric, pickMetric } from '../lib/metrics';
import { productUnion } from '../lib/series';

// 商品毎の折れ線（選択指標）。商品=エンティティに色を固定割り当て（初出順）。商品入れ替えで
// データがない基準日は null にして connectNulls=false で線を途切れさせる。
export function ProductsChart({ series, metric }: { series: SeriesPoint[]; metric: Metric }) {
  const products = productUnion(series);
  const data = series.map((point) => {
    const byName = new Map(point.products.map((product) => [product.name, product]));
    const row: Record<string, string | number | null> = { base_date: point.base_date };
    for (const name of products) {
      const product = byName.get(name);
      row[name] = product ? pickMetric(product, metric) : null;
    }
    return row;
  });

  const format = metric === 'profit_loss' ? formatSigned : formatYen;

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="base_date"
            tickFormatter={shortDate}
            tick={AXIS_TICK}
            tickLine={false}
            minTickGap={24}
          />
          <YAxis
            tickFormatter={axisYen}
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={48}
          />
          <Tooltip
            {...TOOLTIP_STYLE}
            formatter={(value) => format(Number(value))}
            labelFormatter={(label) => String(label)}
          />
          <Legend />
          {products.map((name, index) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              name={name}
              stroke={seriesColor(index)}
              strokeWidth={2}
              connectNulls={false}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
