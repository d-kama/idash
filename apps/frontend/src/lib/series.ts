// 期間フィルタ・商品和集合の純粋ロジック。BFF は常に全期間を返し、期間の絞り込みと
// 「表示期間内に登場する全商品の和集合」の算出はフロント側で行う（設計判断どおり）。
import type { SeriesPoint } from '../api/types';

/** 表示範囲セレクタ。粒度リサンプリングはせず、最新基準日からの範囲で絞る。 */
export type PeriodRange = '1M' | '3M' | '6M' | '1Y' | 'ALL';

const RANGE_MONTHS: Record<Exclude<PeriodRange, 'ALL'>, number> = {
  '1M': 1,
  '3M': 3,
  '6M': 6,
  '1Y': 12,
};

/**
 * UTC で N ヶ月前の日付を返す。桁あふれを避けるため日を 1 に寄せてから月を動かし、最後に対象月の
 * 末日へクランプする（例: 2026-05-31 の 3M → 2026-02-28。素朴な setUTCMonth だと 03-03 にずれる）。
 */
function subMonthsUTC(date: Date, months: number): Date {
  const day = date.getUTCDate();
  const result = new Date(date);
  result.setUTCDate(1);
  result.setUTCMonth(result.getUTCMonth() - months);
  const lastDay = new Date(
    Date.UTC(result.getUTCFullYear(), result.getUTCMonth() + 1, 0),
  ).getUTCDate();
  result.setUTCDate(Math.min(day, lastDay));
  return result;
}

/**
 * 期間セレクタで系列を絞る。基準は「今日」ではなく**データ内の最新基準日**（= series 末尾、
 * 昇順前提）から N ヶ月遡った閉区間。ALL・空系列はそのまま返す。UTC で日付演算し TZ 差を避ける。
 */
export function filterByRange(series: SeriesPoint[], range: PeriodRange): SeriesPoint[] {
  if (range === 'ALL' || series.length === 0) return series;
  const latest = new Date(series[series.length - 1].base_date);
  const cutoff = subMonthsUTC(latest, RANGE_MONTHS[range]);
  return series.filter((point) => new Date(point.base_date) >= cutoff);
}

/**
 * 系列に登場する全商品名の和集合を**初出順**（昇順系列を走査した順）で返す。テーブルの列・
 * グラフの系列に使う。データがない基準日は各コンポーネント側で欠測（空欄/線の途切れ）にする。
 */
export function productUnion(series: SeriesPoint[]): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const point of series) {
    for (const product of point.products) {
      if (!seen.has(product.name)) {
        seen.add(product.name);
        names.push(product.name);
      }
    }
  }
  return names;
}
