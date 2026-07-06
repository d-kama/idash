// 相互排他トグルのセグメントコントロール（期間セレクタ・指標トグルで共用）。
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: readonly { key: T; label: string }[];
  value: T;
  onChange: (key: T) => void;
  ariaLabel: string;
}) {
  return (
    // biome-ignore lint/a11y/useSemanticElements: セグメント化トグル群は role="group" + aria-label が適切（fieldset/legend は過剰）
    <div
      className="inline-flex rounded-lg border border-neutral-200 dark:border-neutral-700"
      role="group"
      aria-label={ariaLabel}
    >
      {options.map(({ key, label }) => (
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
