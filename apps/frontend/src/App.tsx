import { type ReactNode, useEffect, useState } from 'react';
import { fetchVisualization } from './api/client';
import type { VisualizationResponse } from './api/types';
import { AssetsTable } from './components/AssetsTable';
import { EmptyState } from './components/EmptyState';
import { Hero } from './components/Hero';
import { MetricToggle } from './components/MetricToggle';
import { PeriodSelector } from './components/PeriodSelector';
import { PortfolioChart } from './components/PortfolioChart';
import { ProductsChart } from './components/ProductsChart';
import type { Metric } from './lib/metrics';
import { filterByRange, type PeriodRange } from './lib/series';

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <header className="border-b border-neutral-200 dark:border-neutral-800">
        <div className="mx-auto max-w-5xl px-4 py-4">
          <h1 className="text-lg font-semibold">idash — iDeCo 運用ダッシュボード</h1>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  );
}

function Card({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function App() {
  const [data, setData] = useState<VisualizationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<PeriodRange>('ALL');
  const [metric, setMetric] = useState<Metric>('valuation');

  useEffect(() => {
    fetchVisualization()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Shell>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">読み込み中…</p>
      </Shell>
    );
  }
  if (error) {
    return (
      <Shell>
        <EmptyState message={`データの取得に失敗しました: ${error}`} />
      </Shell>
    );
  }
  if (!data?.summary || data.series.length === 0) {
    return (
      <Shell>
        <EmptyState message="まだ運用データが収集されていません。" />
      </Shell>
    );
  }

  const summary = data.summary;
  const filtered = filterByRange(data.series, period);

  return (
    <Shell>
      <div className="flex flex-col gap-6">
        <Hero summary={summary} />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <PeriodSelector value={period} onChange={setPeriod} />
          <MetricToggle value={metric} onChange={setMetric} />
        </div>

        <Card title="ポートフォリオ全体（評価額 × 拠出累計）">
          <PortfolioChart series={filtered} />
        </Card>

        <Card title="商品別の推移">
          <ProductsChart series={filtered} metric={metric} />
        </Card>

        <Card title="商品別の日別推移">
          <AssetsTable series={filtered} metric={metric} />
        </Card>
      </div>
    </Shell>
  );
}
