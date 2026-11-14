import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import KpiCard from '../components/KpiCard';
import BarChart from '../components/BarChart';
import { CheckCircle2, ShieldAlert, Clock, DollarSign, Target, Sparkles } from 'lucide-react';

export default function OverviewView() {
  const [overview, setOverview] = useState(null);
  const [quality, setQuality] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [o, q] = await Promise.all([
        api.getOverview(),
        api.getQuality(),
      ]);
      setOverview(o);
      setQuality(q);
    } catch (e) {
      console.error('Failed to load overview telemetry:', e);
      setError(e.message || 'Failed to load overview telemetry.');
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

  if (error || !overview || !quality) {
    return (
      <div className="p-6 rounded-2xl border border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300">
        <p className="text-sm font-semibold">{error || 'Overview data is unavailable.'}</p>
        <button
          onClick={loadData}
          className="mt-3 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold"
        >
          Retry
        </button>
      </div>
    );
  }

  const goodCount = overview.quality_distribution?.Good ?? 0;
  const totalQuality = Object.values(overview.quality_distribution || {}).reduce((a, b) => a + b, 0) || 1;
  const goodPct = ((goodCount / totalQuality) * 100).toFixed(1);
  const costByCurrency = Object.entries(overview.cost_by_currency || {});
  const costLabel = overview.total_cost != null && overview.currency
    ? `${overview.total_cost.toFixed(4)} ${overview.currency}`
    : costByCurrency.length > 0
      ? 'Multiple currencies'
      : 'Unavailable';
  const costHint = overview.avg_cost_per_interaction != null && overview.currency
    ? `Avg ${overview.avg_cost_per_interaction.toFixed(4)} ${overview.currency}/call`
    : costByCurrency.map(([currency, amount]) => `${amount.toFixed(4)} ${currency}`).join(' | ') || 'No cost metrics';
  const sentimentAndEmotion = {
    ...Object.fromEntries(
      Object.entries(quality.sentiment || {}).map(([label, count]) => [`Sentiment: ${label}`, count])
    ),
    ...Object.fromEntries(
      Object.entries(quality.emotion || {}).map(([label, count]) => [`Emotion: ${label}`, count])
    ),
  };

  return (
    <div className="space-y-6">
      {/* Primary KPI Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <KpiCard
          title="Total Calls"
          value={overview.total_interactions}
          hint={`${overview.completed_interactions} Completed | ${overview.abandoned_interactions} Drops`}
          variant="cyan"
          icon={Sparkles}
        />
        <KpiCard
          title="Success Rate"
          value={`${overview.successful_outcomes_percentage}%`}
          hint={`${overview.successful_outcomes} callbacks booked`}
          variant="emerald"
          icon={Target}
        />
        <KpiCard
          title="Quality Score"
          value={`${goodPct}%`}
          hint={`${goodCount} Good calls`}
          variant="emerald"
          icon={CheckCircle2}
        />
        <KpiCard
          title="Compliance Violations"
          value={overview.compliance_findings?.FAILED ?? 0}
          hint="Deterministic never-rules"
          variant={(overview.compliance_findings?.FAILED ?? 0) > 0 ? "rose" : "purple"}
          icon={ShieldAlert}
        />
        <KpiCard
          title="Turn Latency"
          value={overview.avg_latency_s == null ? 'N/A' : `${overview.avg_latency_s}s`}
          badge={`p95: ${overview.p95_latency_s == null ? 'N/A' : `${overview.p95_latency_s}s`}`}
          hint="Avg turnaround time"
          variant="cyan"
          icon={Clock}
        />
        <KpiCard
          title="Total Cost"
          value={costLabel}
          badge={overview.currency || (costByCurrency.length > 1 ? 'Mixed' : 'N/A')}
          hint={costHint}
          variant="amber"
          icon={DollarSign}
        />
      </div>

      {/* Analytics Distributions Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <BarChart
          title="Outcome Intent Distribution"
          data={quality?.outcomes}
          variant="cyan"
        />
        <BarChart
          title="Customer Sentiment & Emotion"
          data={sentimentAndEmotion}
          variant="emerald"
        />
        <BarChart
          title="Failure & Interruption Analysis"
          data={{
            'Late Agent Opening': quality.technical_failures?.LATE_AGENT_OPENING ?? 0,
            'No Agent Audio': quality.technical_failures?.NO_AGENT_AUDIO ?? 0,
            'Cut Interruption': quality.conversational_failures?.CUSTOMER_INTERRUPTION ?? 0,
            'Customer Drop': quality.conversational_failures?.CUSTOMER_DISCONNECT ?? 0,
          }}
          variant="rose"
        />
      </div>
    </div>
  );
}

