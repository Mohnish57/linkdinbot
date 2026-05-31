import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';
import Sidebar from './components/Sidebar';
import TabSetup from './components/TabSetup';
import TabCandidate from './components/TabCandidate';
import TabNotes from './components/TabNotes';
import TabAI from './components/TabAI';
import TabRun from './components/TabRun';
import TabPosts from './components/TabPosts';
import TabResults from './components/TabResults';
import TabEmail from './components/TabEmail';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

function App() {
  const [activeTab, setActiveTab] = useState('setup');
  const [config, setConfig] = useState({});
  const [status, setStatus] = useState({ state: 'idle' });
  const [loading, setLoading] = useState(true);

  // Load config on mount
  useEffect(() => {
    fetchConfig();
    const interval = setInterval(fetchStatus, 1000); // Poll status every second
    return () => clearInterval(interval);
  }, []);

  const fetchConfig = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/config`);
      setConfig(res.data);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load config:', err);
      setLoading(false);
    }
  };

  const fetchStatus = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/status`);
      setStatus(res.data);
    } catch (err) {
      console.error('Failed to fetch status:', err);
    }
  };

  const saveConfig = async (updates) => {
    try {
      const res = await axios.post(`${API_URL}/api/config`, updates);
      setConfig(res.data.config);
      return true;
    } catch (err) {
      console.error('Failed to save config:', err);
      return false;
    }
  };

  if (loading) {
    return <div style={{ padding: '20px', textAlign: 'center' }}>Loading...</div>;
  }

  const tabs = [
    { id: 'setup', label: '⚙️ Setup', component: TabSetup },
    { id: 'candidate', label: '🪪 Candidate', component: TabCandidate },
    { id: 'notes', label: '💬 Notes', component: TabNotes },
    { id: 'ai', label: '🧠 AI', component: TabAI },
    { id: 'run', label: '▶️ Run', component: TabRun },
    { id: 'posts', label: '📰 Posts', component: TabPosts },
    { id: 'results', label: '📊 Results', component: TabResults },
    { id: 'email', label: '📨 Email', component: TabEmail },
  ];

  const TabComponent = tabs.find(t => t.id === activeTab)?.component || TabSetup;

  return (
    <div className="app">
      <header className="header">
        <h1>🤖 LinkedIn Referral Bot</h1>
        <p>Hirer → recruiters → emails. Resume routing + invite notes.</p>
      </header>

      <div className="main">
        <Sidebar config={config} saveConfig={saveConfig} />

        <div className="content">
          <div className="tabs">
            {tabs.map(tab => (
              <button
                key={tab.id}
                className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {status.state === 'running' && (
            <div className="status running">
              ⏳ {status.message}
            </div>
          )}
          {status.state === 'done' && (
            <div className="status success">
              ✅ {status.message}
            </div>
          )}
          {status.state === 'error' && (
            <div className="status error">
              ❌ {status.message}
            </div>
          )}

          <div className="tab-content">
            <TabComponent
              config={config}
              saveConfig={saveConfig}
              status={status}
              apiUrl={API_URL}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
