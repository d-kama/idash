import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { SeriesPoint } from '../api/types';
import { AXIS_TICK, axisYen, GRID_STROKE, shortDate, TOOLTIP_STYLE } from '../lib/chart';
import { seriesColor } from '../lib/colors';
import { formatYen } from '../lib/format';

// ポートフォリオ全体: 評価額（面）に拠出累計（線）を重ね、差分（=評価損益）を面で読ませる。
// 単一 Y 軸（両者とも円）。欠測は connectNulls=false で途切れさせる。
export function PortfolioChart({ series }: { series: SeriesPoint[] }) {
  const data = series.map((point) => ({
    base_date: point.base_date,
    valuation: point.total.valuation,
    contribution: point.total.contribution,
  }));

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
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
            formatter={(value) => formatYen(Number(value))}
            labelFormatter={(label) => String(label)}
          />
          <Legend />
          <Area
            type="monotone"
            dataKey="valuation"
            name="評価額"
            stroke={seriesColor(0)}
            fill={seriesColor(0)}
            fillOpacity={0.15}
            strokeWidth={2}
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="contribution"
            name="拠出累計"
            stroke={seriesColor(1)}
            strokeWidth={2}
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
