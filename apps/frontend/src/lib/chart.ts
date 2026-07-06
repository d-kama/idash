// Recharts の共通スタイル・軸整形。テーマ変数（CSS var）を渡し、ライト/ダーク両対応にする。

export const TOOLTIP_STYLE = {
  contentStyle: {
    background: 'var(--surface-1)',
    border: '1px solid var(--grid)',
    borderRadius: 8,
    fontSize: 12,
  },
  labelStyle: { color: 'var(--text-2)' },
  itemStyle: { color: 'var(--text-1)' },
} as const;

export const AXIS_TICK = { fill: 'var(--text-2)', fontSize: 12 } as const;
export const GRID_STROKE = 'var(--grid)';

/** `2026-07-03` → `7/3`（X 軸ラベルの圧縮）。 */
export function shortDate(iso: string): string {
  const [, month, day] = iso.split('-');
  return `${Number(month)}/${Number(day)}`;
}

/** Y 軸向けの圧縮円表示（万単位）。ツールチップは formatYen で厳密表示するため軸は概算でよい。 */
export function axisYen(yen: number): string {
  if (yen === 0) return '0';
  return `${Math.round(yen / 10000).toLocaleString('ja-JP')}万`;
}
