// 系列色の割り当て。カテゴリ配色は固定順（商品=エンティティに追従し、順位で塗り替えない）。
// スロットは検証済み8色。9件以上は muted に畳む（色は循環させない=データビズ非交渉ルール）。

const SLOT_COUNT = 8;

export function seriesColor(index: number): string {
  if (index < 0 || index >= SLOT_COUNT) return 'var(--series-muted)';
  return `var(--series-${index + 1})`;
}

export const STATUS_GOOD = 'var(--status-good)';
export const STATUS_CRITICAL = 'var(--status-critical)';

/** 損益極性の色（含み益=good / 元本割れ=critical）。0 は good 扱い（±0）。 */
export function profitColor(yen: number): string {
  return yen < 0 ? STATUS_CRITICAL : STATUS_GOOD;
}
