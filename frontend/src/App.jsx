import React, { useState } from 'react';
import { ThemeProvider } from './context/ThemeContext';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import OverviewView from './views/OverviewView';
import InteractionsView from './views/InteractionsView';
import DrillDownView from './views/DrillDownView';
import IngestView from './views/IngestView';
import BenchmarkView from './views/BenchmarkView';
import EvaluatorsView from './views/EvaluatorsView';

function AppContent() {
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedCallId, setSelectedCallId] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('conversense_sidebar_collapsed') === 'true';
  });

  const handleToggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('conversense_sidebar_collapsed', String(next));
      return next;
    });
  };

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
    <div className="flex h-screen bg-slate-50 dark:bg-[#060a12] text-slate-900 dark:text-slate-100 overflow-hidden font-sans transition-colors duration-150">
      {/* Sidebar with Mobile Drawer & Desktop Collapse support */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={(tab) => {
          setActiveTab(tab);
          setMobileMenuOpen(false);
        }}
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={handleToggleSidebar}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden min-w-0">
        {/* Topbar with Theme Toggle & Mobile Menu Trigger */}
        <Topbar
          activeTab={activeTab}
          onRefresh={handleRefresh}
          onIngestClick={() => setActiveTab('ingest')}
          onToggleMobileMenu={() => setMobileMenuOpen(!mobileMenuOpen)}
          isRefreshing={isRefreshing}
        />

        {/* View Scroll Container */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
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

export default function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}
