import React from 'react';

export default function ConfusionMatrix({ title, matrixData }) {
  if (!matrixData || !matrixData.labels || !matrixData.matrix) {
    return (
      <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/40 text-slate-500 text-xs shadow-sm">
        No matrix data available for {title}
      </div>
    );
  }

  const { labels, matrix } = matrixData;

  return (
    <div className="p-4 sm:p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 backdrop-blur-md shadow-sm dark:shadow-none transition-colors">
      <h4 className="text-sm font-bold text-slate-900 dark:text-slate-200 mb-1">{title}</h4>
      <p className="text-[11px] font-mono text-slate-500 mb-4">
        Rows: Ground Truth (Actual) &bull; Columns: AI Model Predictions
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono border-collapse min-w-[340px]">
          <thead>
            <tr>
              <th className="p-2 border-b border-slate-200 dark:border-slate-800 text-left text-slate-600 dark:text-slate-400 font-bold bg-slate-50 dark:bg-slate-950/60">
                Actual \ Pred
              </th>
              {labels.map((lbl) => (
                <th
                  key={lbl}
                  className="p-2 border-b border-slate-200 dark:border-slate-800 text-center text-cyan-700 dark:text-cyan-400 font-bold bg-slate-50/70 dark:bg-slate-950/40 truncate max-w-[120px]"
                  title={lbl}
                >
                  {lbl}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map((actual) => (
              <tr key={actual} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                <td className="p-2 border-b border-slate-200 dark:border-slate-800/80 font-semibold text-slate-800 dark:text-slate-300 bg-slate-50/40 dark:bg-slate-950/30 truncate max-w-[140px]" title={actual}>
                  {actual}
                </td>
                {labels.map((pred) => {
                  const count = (matrix[actual] && matrix[actual][pred]) || 0;
                  const isMatch = actual === pred;
                  const hasErrors = !isMatch && count > 0;

                  return (
                    <td
                      key={pred}
                      className={`p-2.5 border-b border-slate-200 dark:border-slate-800/60 text-center font-bold transition-all ${
                        isMatch && count > 0
                          ? 'bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-500/20 shadow-inner'
                          : hasErrors
                          ? 'bg-rose-50 text-rose-700 font-semibold dark:bg-rose-950/40 dark:text-rose-300'
                          : 'text-slate-400 dark:text-slate-600'
                      }`}
                    >
                      {count}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
