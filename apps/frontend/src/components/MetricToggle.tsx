import { METRICS, type Metric } from '../lib/metrics';
import { SegmentedControl } from './SegmentedControl';

const OPTIONS = METRICS.map(({ key, label }) => ({ key, label }));

export function MetricToggle({
  value,
  onChange,
}: {
  value: Metric;
  onChange: (metric: Metric) => void;
}) {
  return (
    <SegmentedControl options={OPTIONS} value={value} onChange={onChange} ariaLabel="表示指標" />
  );
}
