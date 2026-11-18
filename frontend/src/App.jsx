import React, { useState, useEffect } from 'react';
import { ThemeProvider } from './context/ThemeContext';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import OverviewView from './views/OverviewView';
import InteractionsView from './views/InteractionsView';
import DrillDownView from './views/DrillDownView';
import BenchmarkView from './views/BenchmarkView';
import CallImportView from './views/CallImportView';
import ScalingView from './views/ScalingView';
import { getRouteFromLocation, pushRoute } from './router';

function AppContent() {
  const initialRoute = getRouteFromLocation();
  const [activeTab, setActiveTab] = useState(initialRoute.tab);
  const [selectedCallId, setSelectedCallId] = useState(initialRoute.callId);
  const [refreshKey, setRefreshKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('conversense_sidebar_collapsed') === 'true';
  });

  // Sync state on browser back/forward or external route changes
  useEffect(() => {
    const handlePopState = () => {
      const { tab, callId } = getRouteFromLocation();
      setActiveTab(tab);
      if (callId) setSelectedCallId(callId);
    };

    window.addEventListener('popstate', handlePopState);
    window.addEventListener('conversense:routechange', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
      window.removeEventListener('conversense:routechange', handlePopState);
    };
  }, []);

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

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setMobileMenuOpen(false);
    pushRoute(tab, tab === 'drilldown' ? selectedCallId : '');
  };

  const handleInspectCall = (callId) => {
    setSelectedCallId(callId);
    setActiveTab('drilldown');
    pushRoute('drilldown', callId);
  };

  const handleSelectCallId = (callId) => {
    setSelectedCallId(callId);
    if (activeTab === 'drilldown') {
      pushRoute('drilldown', callId, true);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-[#060a12] text-slate-900 dark:text-slate-100 overflow-hidden font-sans transition-colors duration-150">
      {/* Sidebar with Mobile Drawer & Desktop Collapse support */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={handleTabChange}
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
          onToggleMobileMenu={() => setMobileMenuOpen(!mobileMenuOpen)}
          isRefreshing={isRefreshing}
        />

        {/* View Scroll Container */}
        <main
          className={`flex-1 min-w-0 ${
            activeTab === 'drilldown'
              ? 'overflow-hidden p-3 sm:p-4 flex flex-col'
              : 'overflow-y-auto p-4 sm:p-6 lg:p-8'
          }`}
        >
          <div
            key={refreshKey}
            className={`w-full mx-auto ${
              activeTab === 'drilldown'
                ? 'h-full flex flex-col min-h-0'
                : 'max-w-7xl pb-12'
            }`}
          >
            {activeTab === 'overview' && (
              <OverviewView onInspectCall={handleInspectCall} />
            )}
            {activeTab === 'interactions' && (
              <InteractionsView onInspectCall={handleInspectCall} />
            )}
            {activeTab === 'drilldown' && (
              <DrillDownView
                initialCallId={selectedCallId}
                onSelectCallId={handleSelectCallId}
              />
            )}
            {activeTab === 'benchmark' && <BenchmarkView />}
            {activeTab === 'import-calls' && (
              <CallImportView onInspectCall={handleInspectCall} />
            )}
            {activeTab === 'scaling' && (
              <ScalingView onInspectCall={handleInspectCall} />
            )}
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
