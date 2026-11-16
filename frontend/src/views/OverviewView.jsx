import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import KpiCard from '../components/KpiCard';
import { Activity, AlertTriangle, Clock, DollarSign, Gauge, Layers, Zap } from 'lucide-react';

const formatNumber = (value, digits = 2) =>
  value == null ? 'Unavailable' : Number(value).toFixed(digits);

function Distribution({ title, data }) {
  const entries = Object.entries(data || {});
  return (
    <section className="p-4 rounded-2xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200 mb-3">
        {title}
      </h3>
      {entries.length === 0 ? (
        <p className="text-xs text-slate-500">Unavailable</p>
      ) : (
        <ul className="space-y-2">
          {entries.map(([label, count]) => (
            <li key={label} className="flex justify-between gap-3 text-xs">
              <span className="text-slate-600 dark:text-slate-300">{label}</span>
              <strong className="text-slate-900 dark:text-slate-100">{count}</strong>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function OverviewView() {
  const [overview, setOverview] = useState(null);
  const [reliability, setReliability] = useState(null);
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [operationalOverview, reliabilityData, usageData] = await Promise.all([
        api.getOverview(),
        api.getReliability(),
        api.getUsage(),
      ]);
      setOverview(operationalOverview);
      setReliability(reliabilityData);
      setUsage(usageData);
    } catch (e) {
      console.error('Failed to load observability analytics:', e);
      setError(e.message || 'Failed to load observability analytics.');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-brand-cyan/20 border-t-brand-cyan animate-spin"></div>
      </div>
    );
  }

  if (error || !overview || !reliability || !usage) {
    return (
      <div className="p-6 rounded-2xl border border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300">
        <p className="text-sm font-semibold">{error || 'Observability data is unavailable.'}</p>
        <button
          onClick={loadData}
          className="mt-3 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold"
        >
          Retry
        </button>
      </div>
    );
  }

  const statuses = reliability.interaction_status_counts || {};
  const cost = usage.estimated_cost == null
    ? 'Unavailable'
    : `${formatNumber(usage.estimated_cost, 4)} ${usage.currency || ''}`.trim();

  return (
    <div className="space-y-7">
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
          <h2 className="text-sm font-bold text-slate-900 dark:text-white">Operational observability</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <KpiCard title="Interactions" value={overview.total_interactions} hint="Canonical interactions" icon={Layers} />
          <KpiCard title="Metrics available" value={overview.metrics_available_interactions} hint="Interactions with persisted observability metrics" variant="purple" icon={Gauge} />
          <KpiCard title="Recording duration" value={`${formatNumber(overview.average_recording_duration_s)} s`} hint="Average, when measured" variant="cyan" icon={Clock} />
          <KpiCard title="Response latency" value={`${formatNumber(overview.average_response_latency_s)} s`} badge={`p95 ${formatNumber(overview.p95_response_latency_s)} s`} hint="Measured response samples only" variant="amber" icon={Zap} />
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400" />
          <h2 className="text-sm font-bold text-slate-900 dark:text-white">Reliability</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <KpiCard title="Interactions with failures" value={reliability.interactions_with_failures} hint="Based on supplied failure evidence" variant="rose" icon={AlertTriangle} />
          <Distribution title="Processing status" data={statuses} />
          <Distribution title="Technical failures" data={reliability.technical_failures} />
          <Distribution title="Conversational failures" data={reliability.conversational_failures} />
          <Distribution title="Supplied failure events" data={reliability.supplied_event_failures} />
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          <h2 className="text-sm font-bold text-slate-900 dark:text-white">Usage</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard title="Input tokens" value={usage.input_tokens ?? 'Unavailable'} hint="Interaction and evaluation usage" icon={Zap} />
          <KpiCard title="Output tokens" value={usage.output_tokens ?? 'Unavailable'} hint="Interaction and evaluation usage" icon={Zap} />
          <KpiCard title="Estimated cost" value={cost} badge={usage.cost_availability} hint={`Rate cards: ${(usage.rate_card_versions || []).join(', ') || 'Unavailable'}`} variant="amber" icon={DollarSign} />
        </div>
      </section>
    </div>
  );
}
