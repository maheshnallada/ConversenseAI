import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import OverviewView from './views/OverviewView';
import InteractionsView from './views/InteractionsView';
import DrillDownView from './views/DrillDownView';
import IngestView from './views/IngestView';
import BenchmarkView from './views/BenchmarkView';
import EvaluatorsView from './views/EvaluatorsView';

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedCallId, setSelectedCallId] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = () => {
    setIsRefreshing(true);
    setRefreshKey((prev) => prev + 1);
    setTimeout(() => setIsRefreshing(false), 500);
  };

  const handleInspectCall = (callId) => {
    setSelectedCallId(callId);
    setActiveTab('drilldown');
  };

  return (
    <div className="flex h-screen bg-[#060a12] text-slate-100 overflow-hidden font-sans">
      {/* Sidebar */}
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Topbar */}
        <Topbar
          activeTab={activeTab}
          onRefresh={handleRefresh}
          onIngestClick={() => setActiveTab('ingest')}
          isRefreshing={isRefreshing}
        />

        {/* View Scroll Container */}
        <main className="flex-1 overflow-y-auto p-8">
          <div key={refreshKey} className="max-w-7xl mx-auto pb-12">
            {activeTab === 'overview' && (
              <OverviewView onInspectCall={handleInspectCall} />
            )}
            {activeTab === 'interactions' && (
              <InteractionsView onInspectCall={handleInspectCall} />
            )}
            {activeTab === 'drilldown' && (
              <DrillDownView
                initialCallId={selectedCallId}
                onSelectCallId={setSelectedCallId}
              />
            )}
            {activeTab === 'ingest' && (
              <IngestView onNavigateToDrillDown={handleInspectCall} />
            )}
            {activeTab === 'benchmark' && <BenchmarkView />}
            {activeTab === 'evaluators' && <EvaluatorsView />}
          </div>
        </main>
      </div>
    </div>
  );
}
