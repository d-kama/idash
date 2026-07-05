import type { PeriodRange } from '../lib/series';

const RANGES: readonly { key: PeriodRange; label: string }[] = [
  { key: '1M', label: '1ヶ月' },
  { key: '3M', label: '3ヶ月' },
  { key: '6M', label: '6ヶ月' },
  { key: '1Y', label: '1年' },
  { key: 'ALL', label: '全期間' },
] as const;

export function PeriodSelector({
  value,
  onChange,
}: {
  value: PeriodRange;
  onChange: (range: PeriodRange) => void;
}) {
  return (
    // biome-ignore lint/a11y/useSemanticElements: セグメント化トグル群は role="group" + aria-label が適切（fieldset/legend は過剰）
    <div
      className="inline-flex rounded-lg border border-neutral-200 dark:border-neutral-700"
      role="group"
      aria-label="表示期間"
    >
      {RANGES.map(({ key, label }) => (
        <button
          type="button"
          key={key}
          onClick={() => onChange(key)}
          aria-pressed={value === key}
          className={`px-3 py-1.5 text-sm first:rounded-l-lg last:rounded-r-lg ${
            value === key
              ? 'bg-neutral-900 text-white dark:bg-white dark:text-neutral-900'
              : 'text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
