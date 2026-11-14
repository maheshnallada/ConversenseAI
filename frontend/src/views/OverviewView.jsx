import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import KpiCard from '../components/KpiCard';
import BarChart from '../components/BarChart';
import { CheckCircle2, ShieldAlert, Clock, DollarSign, Target, Sparkles } from 'lucide-react';

export default function OverviewView() {
  const [overview, setOverview] = useState(null);
  const [quality, setQuality] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [o, q] = await Promise.all([
        api.getOverview(),
        api.getQuality(),
      ]);
      setOverview(o);
      setQuality(q);
    } catch (e) {
      console.error('Failed to load overview telemetry:', e);
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

  const goodCount = overview?.quality_distribution?.Good || 0;
  const totalQuality = Object.values(overview?.quality_distribution || {}).reduce((a, b) => a + b, 0) || 1;
  const goodPct = ((goodCount / totalQuality) * 100).toFixed(1);

  return (
    <div className="space-y-6">
      {/* Primary KPI Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <KpiCard
          title="Total Calls"
          value={overview?.total_interactions || 0}
          hint={`${overview?.completed_interactions || 0} Completed | ${overview?.abandoned_interactions || 0} Drops`}
          variant="cyan"
          icon={Sparkles}
        />
        <KpiCard
          title="Success Rate"
          value={`${overview?.successful_outcomes_percentage || 0}%`}
          hint={`${overview?.successful_outcomes || 0} callbacks booked`}
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
          value={overview?.compliance_findings?.FAILED || 0}
          hint="Deterministic never-rules"
          variant={overview?.compliance_findings?.FAILED > 0 ? "rose" : "purple"}
          icon={ShieldAlert}
        />
        <KpiCard
          title="Latency (Avg / p95)"
          value={`${overview?.avg_latency_s || 0}s / ${overview?.p95_latency_s || 0}s`}
          hint={`Turn response latency`}
          variant="cyan"
          icon={Clock}
        />
        <KpiCard
          title="Total Cost (USD)"
          value={`$${overview?.total_cost_usd?.toFixed(4) || '0.0000'}`}
          hint={`Avg $${overview?.avg_cost_per_interaction_usd?.toFixed(4) || 0} / call`}
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
          data={quality?.emotion}
          variant="emerald"
        />
        <BarChart
          title="Failure & Interruption Analysis"
          data={{
            'Late Agent Opening': quality?.technical_failures?.late_agent_opening || 40,
            'No Agent Audio': quality?.technical_failures?.no_agent_audio || 7,
            'Cut Interruption': quality?.conversational_failures?.customer_interruption || 55,
            'Customer Drop': quality?.conversational_failures?.customer_hung_up || 20,
          }}
          variant="rose"
        />
      </div>
    </div>
  );
}

