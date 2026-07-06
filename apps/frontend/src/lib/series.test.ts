import { describe, expect, it } from 'vitest';
import type { SeriesPoint } from '../api/types';
import { filterByRange, productUnion } from './series';

// 商品名だけを持つ最小の SeriesPoint を組む（金額はロジックに無関係）。
function point(baseDate: string, ...names: string[]): SeriesPoint {
  return {
    base_date: baseDate,
    products: names.map((name) => ({ name, contribution: 0, profit_loss: 0, valuation: 0 })),
    total: { contribution: 0, profit_loss: 0, valuation: 0 },
  };
}

describe('filterByRange', () => {
  // 昇順・最新 2026-07-01 を基準に「最新から N ヶ月」で切り出す（今日ではなくデータ内最新）。
  const series = [
    point('2026-01-15', 'A'),
    point('2026-04-20', 'A'),
    point('2026-06-10', 'A'),
    point('2026-07-01', 'A'),
  ];

  it('ALL は全期間をそのまま返す', () => {
    expect(filterByRange(series, 'ALL')).toEqual(series);
  });

  it('1M は最新から1ヶ月以内（2026-06-01 以降）', () => {
    expect(filterByRange(series, '1M').map((p) => p.base_date)).toEqual([
      '2026-06-10',
      '2026-07-01',
    ]);
  });

  it('3M は最新から3ヶ月以内（2026-04-01 以降）', () => {
    expect(filterByRange(series, '3M').map((p) => p.base_date)).toEqual([
      '2026-04-20',
      '2026-06-10',
      '2026-07-01',
    ]);
  });

  it('1Y は最新から1年以内（2025-07-01 以降）', () => {
    expect(filterByRange(series, '1Y').map((p) => p.base_date)).toEqual([
      '2026-01-15',
      '2026-04-20',
      '2026-06-10',
      '2026-07-01',
    ]);
  });

  it('空系列は空のまま', () => {
    expect(filterByRange([], '3M')).toEqual([]);
  });

  it('月末基準日でも桁あふれせず月末クランプで切り出す（05-31 の 3M → 02-28 以降）', () => {
    const monthEnd = [
      point('2026-02-27', 'A'),
      point('2026-02-28', 'A'),
      point('2026-03-02', 'A'),
      point('2026-05-31', 'A'),
    ];
    // 素朴な setUTCMonth だと cutoff が 03-03 になり 02-28・03-02 が抜ける。クランプで 02-28 以降。
    expect(filterByRange(monthEnd, '3M').map((p) => p.base_date)).toEqual([
      '2026-02-28',
      '2026-03-02',
      '2026-05-31',
    ]);
  });
});

describe('productUnion', () => {
  it('登場順（昇順系列の初出順）で商品名の和集合を返す', () => {
    const series = [
      point('2026-07-01', 'A'),
      point('2026-07-02', 'A', 'B'),
      point('2026-07-03', 'C', 'A'),
    ];
    expect(productUnion(series)).toEqual(['A', 'B', 'C']);
  });

  it('空系列は空配列', () => {
    expect(productUnion([])).toEqual([]);
  });
});
