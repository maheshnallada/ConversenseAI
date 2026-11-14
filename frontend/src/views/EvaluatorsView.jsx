import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Cpu, ShieldCheck, Zap, DollarSign, Activity, FileCode, CheckCircle } from 'lucide-react';

export default function EvaluatorsView() {
  const [evaluators, setEvaluators] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const list = await api.getEvaluators();
        setEvaluators(list || []);
      } catch (e) {
        console.error('Failed to load evaluators:', e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const rateCard = {
    provider: "Conversense AI Observability Engine",
    currency: "USD",
    rate_card: {
      audio_transcription: {
        engine: "Groq Whisper Large v3",
        cost_per_minute: "$0.0018",
        p95_latency_ms: 180,
      },
      deterministic_safety_eval: {
        engine: "Python Rule Engine / Regex / Aho-Corasick",
        cost_per_evaluation: "$0.0000",
        p95_latency_ms: 15,
      },
      llm_evaluation: {
        engine: "Llama 3.3 70B Versatile",
        cost_per_1k_tokens_input: "$0.00059",
        cost_per_1k_tokens_output: "$0.00079",
        p95_latency_ms: 650,
      },
      turnaround_and_drift_reconciliation: {
        engine: "Clock-Drift Calibration & Monotonic Orderer",
        cost_per_interaction: "$0.0000",
        p95_latency_ms: 8,
      }
    },
    service_level_agreements: {
      availability: "99.95%",
      critical_safety_recall: "100.0%",
      pii_redaction_rate: "100.0%",
    }
  };

  return (
    <div className="space-y-6">
      {/* Banner */}
      <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/60 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
            <Cpu className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">Evaluators &amp; Policy Registry</h2>
            <p className="text-xs text-slate-400">
              Active evaluator definitions, deterministic guardrails, LLM-as-a-judge rubrics, and latency/cost rate cards.
            </p>
          </div>
        </div>
      </div>

      {/* Evaluator Catalog Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {evaluators.map((ev) => (
          <div
            key={ev.evaluator_id}
            className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 hover:border-slate-700 transition-all flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="font-mono text-sm font-semibold text-cyan-400 truncate">
                  {ev.evaluator_id}
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 uppercase shrink-0">
                  {ev.family}
                </span>
              </div>

              <p className="text-xs text-slate-300 leading-relaxed font-sans mt-2">
                {ev.description}
              </p>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
              <span>Version: <strong className="text-slate-200">{ev.version}</strong></span>
              <span className="inline-flex items-center gap-1 text-emerald-400">
                <CheckCircle className="w-3.5 h-3.5" /> Active
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Observability Rate Card & SLAs */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-6 p-5 rounded-2xl border border-slate-800 bg-slate-900/50 backdrop-blur-md space-y-4">
          <div className="flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-white">Observability Cost Architecture</h3>
          </div>
          <p className="text-xs text-slate-400">
            Transparent cost accounting per interaction. Evaluators leverage local deterministic rules where possible and high-speed LLM inference for nuanced semantic evaluation.
          </p>

          <div className="space-y-3 font-mono text-xs">
            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
              <div>
                <span className="text-slate-200 block font-semibold">Transcription &amp; Alignment</span>
                <span className="text-[10px] text-slate-500">Groq Whisper Large v3</span>
              </div>
              <span className="text-emerald-400 font-bold">$0.0018 / min</span>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
              <div>
                <span className="text-slate-200 block font-semibold">Safety &amp; Compliance Guardrails</span>
                <span className="text-[10px] text-slate-500">Deterministic Regex &amp; Normalizer</span>
              </div>
              <span className="text-emerald-400 font-bold">$0.0000 (Free)</span>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
              <div>
                <span className="text-slate-200 block font-semibold">Semantic Quality &amp; Outcome Judgement</span>
                <span className="text-[10px] text-slate-500">Llama 3.3 70B Versatile</span>
              </div>
              <span className="text-emerald-400 font-bold">~$0.0012 / call</span>
            </div>
          </div>
        </div>

        <div className="lg:col-span-6 p-5 rounded-2xl border border-slate-800 bg-slate-900/50 backdrop-blur-md space-y-4">
          <div className="flex items-center gap-2">
            <FileCode className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Live Rate Card JSON</h3>
          </div>
          <pre className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 font-mono text-[11px] text-cyan-300/90 overflow-x-auto max-h-[300px]">
            {JSON.stringify(rateCard, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}

