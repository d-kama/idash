import type { VisualizationSummary } from '../api/types';
import { profitColor, STATUS_CRITICAL, STATUS_GOOD } from '../lib/colors';
import { formatPercent, formatSigned, formatYen } from '../lib/format';

// 最新ポートフォリオのヒーロー: 評価額（主役）＋前回比デルタ＋構成バー（拠出累計を土台に損益を重ねる）。
export function Hero({ summary }: { summary: VisualizationSummary }) {
  const { contribution, profit_loss, valuation } = summary.total;
  const gain = profit_loss >= 0;

  // 構成バー: 損益が正なら [拠出|損益(緑)] で全幅=評価額、負なら [評価額|損失(赤)] で全幅=拠出。
  const track = gain ? valuation : contribution;
  const baseWidth = track === 0 ? 0 : (gain ? contribution : valuation) / track;
  const deltaWidth = track === 0 ? 0 : Math.abs(profit_loss) / track;

  return (
    <section className="rounded-2xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-sm text-neutral-500 dark:text-neutral-400">資産評価額</span>
        <span className="text-xs text-neutral-400 dark:text-neutral-500">
          {summary.base_date} 時点
        </span>
      </div>

      <div className="mt-1 flex flex-wrap items-baseline gap-x-4">
        <span className="text-4xl font-bold tabular-nums text-neutral-900 dark:text-white sm:text-5xl">
          {formatYen(valuation)}
        </span>
        <span
          className="text-lg font-medium tabular-nums"
          style={{ color: profitColor(summary.valuation_change) }}
        >
          前回比 {formatSigned(summary.valuation_change)}
        </span>
      </div>

      {/* 構成バー（拠出=土台 / 損益=重ね）。2px の隙間で分節。色だけに依存せず下にラベルを併記。 */}
      <div className="mt-5 flex h-4 gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
        <div
          className="h-full rounded-l-full bg-neutral-300 dark:bg-neutral-600"
          style={{ width: `${baseWidth * 100}%` }}
        />
        <div
          className="h-full rounded-r-full"
          style={{
            width: `${deltaWidth * 100}%`,
            backgroundColor: gain ? STATUS_GOOD : STATUS_CRITICAL,
          }}
        />
      </div>

      <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-1 text-sm">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-neutral-300 dark:bg-neutral-600" />
          <dt className="text-neutral-500 dark:text-neutral-400">拠出累計</dt>
          <dd className="font-medium tabular-nums text-neutral-800 dark:text-neutral-100">
            {formatYen(contribution)}
          </dd>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: gain ? STATUS_GOOD : STATUS_CRITICAL }}
          />
          <dt className="text-neutral-500 dark:text-neutral-400">評価損益</dt>
          <dd className="font-medium tabular-nums" style={{ color: profitColor(profit_loss) }}>
            {formatSigned(profit_loss)}（{formatPercent(summary.profit_rate)}）
          </dd>
        </div>
      </dl>
    </section>
  );
}
