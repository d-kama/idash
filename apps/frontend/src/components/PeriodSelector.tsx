import type { PeriodRange } from '../lib/series';
import { SegmentedControl } from './SegmentedControl';

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
    <SegmentedControl options={RANGES} value={value} onChange={onChange} ariaLabel="表示期間" />
  );
}
