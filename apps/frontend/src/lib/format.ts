// 表示整形（円整数・生比率 → 日本語表示）。DTO は円整数/生比率で、`¥`・符号・`%` の付与は
// フロント側の責務（domain の Money.format / Money.signed / render_summary の +.2f 相当）。
// 桁区切りは Intl.NumberFormat("ja-JP")。

const grouping = new Intl.NumberFormat('ja-JP');

// 常に符号を出す2桁固定の百分率フォーマッタ（domain の `{:+.2f}` と一致させる）。
const percent = new Intl.NumberFormat('ja-JP', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: 'always',
});

/** 円整数を `¥1,234,567` / `-¥80,000` / `¥0` 形式へ。 */
export function formatYen(yen: number): string {
  const sign = yen < 0 ? '-' : '';
  return `${sign}¥${grouping.format(Math.abs(yen))}`;
}

/** 損益向け。正値に明示的な `+` を付す（`+¥180,000`）。0・負は formatYen と同じ。 */
export function formatSigned(yen: number): string {
  if (yen > 0) return `+¥${grouping.format(yen)}`;
  return formatYen(yen);
}

/** 生比率（0.0783）を符号付き2桁% へ（`+7.83%` / `-3.21%` / `+0.00%`）。 */
export function formatPercent(rate: number): string {
  return `${percent.format(rate * 100)}%`;
}
