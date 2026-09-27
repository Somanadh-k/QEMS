import React from 'react';
import { AppProvider, useApp } from './context/AppContext';
import { Sidebar } from './components/Sidebar';
import { Navbar } from './components/Navbar';
import { Toast } from './components/Toast';
import Silk from './components/Silk/Silk';

import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { QAErrors } from './pages/QAErrors';
import { CreateError } from './pages/CreateError';
import { ErrorDetails } from './pages/ErrorDetails';
import { Reports } from './pages/Reports';
import { EscalationInbox } from './pages/EscalationInbox';
import { Profile } from './pages/Profile';

// Mounted once at the root (not per-page) so the WebGL canvas persists across navigation
// instead of re-initializing on every tab switch. Reads theme from context so the silk tone
// follows light/dark mode instead of being fixed.
const AppBackground = () => {
  const { theme } = useApp();
  return (
    <div className="app-background">
      <Silk speed={5} scale={1} color={theme === 'dark' ? '#5A5560' : '#B4AFB8'} noiseIntensity={1.5} rotation={0} />
    </div>
  );
};

const AppContent = () => {
  const { activeTab } = useApp();

  if (activeTab === 'login') {
    return <Login />;
  }

  return (
    <div className="app-container">
      <Sidebar />
      <div className="main-content">
        <Navbar />
        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'qa-errors' && <QAErrors />}
        {activeTab === 'create-error' && <CreateError />}
        {activeTab === 'error-details' && <ErrorDetails />}
        {activeTab === 'escalations' && <EscalationInbox />}
        {activeTab === 'reports' && <Reports />}
        {activeTab === 'profile' && <Profile />}
      </div>
      <Toast />
    </div>
  );
};

export default function App() {
  return (
    <AppProvider>
      <AppBackground />
      <AppContent />
    </AppProvider>
  );
}
