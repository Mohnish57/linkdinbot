import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import './App.css';
import Sidebar from './components/Sidebar';
import TabSetup from './components/TabSetup';
import TabNotes from './components/TabNotes';
import TabRun from './components/TabRun';
import TabPosts from './components/TabPosts';
import TabResults from './components/TabResults';
import TabEmail from './components/TabEmail';
import Icon from './components/Icon';

// Local app: the React dev server (port 3000) talks to the Flask bot backend
// on port 5001. Override with REACT_APP_API_URL only if you change the port.
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5001';

function App() {
  const [activeTab, setActiveTab] = useState('setup');
  const [config, setConfig] = useState({});
  const [status, setStatus] = useState({ state: 'idle' });
  const [loading, setLoading] = useState(true);

  // Keep the latest state in a ref so the poller can read it without re-running.
  const stateRef = useRef(status.state);
  stateRef.current = status.state;

  // Load config once, then poll status adaptively: fast only while a job runs,
  // slow when idle (avoids hammering the API every second).
  useEffect(() => {
    fetchConfig();
    let timer;
    const poll = async () => {
      await fetchStatus();
      timer = setTimeout(poll, stateRef.current === 'running' ? 2000 : 10000);
    };
    timer = setTimeout(poll, 1000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    { id: 'setup', label: 'Setup', icon: 'settings', component: TabSetup },
    { id: 'notes', label: 'Notes', icon: 'message', component: TabNotes },
    { id: 'run', label: 'Run', icon: 'play', component: TabRun },
    { id: 'results', label: 'Results', icon: 'table', component: TabResults },
    { id: 'email', label: 'Email', icon: 'mail', component: TabEmail },
    // Post outreach is a separate feature — keep it last.
    { id: 'posts', label: 'Posts', icon: 'document', component: TabPosts },
  ];

  const TabComponent = tabs.find(t => t.id === activeTab)?.component || TabSetup;

  return (
    <div className="app">
      <ToastContainer position="top-right" autoClose={3500} newestOnTop theme="colored" />
      <header className="header">
        <h1><Icon name="briefcase" size={34} /> LinkedIn Referral Bot</h1>
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
                <Icon name={tab.icon} size={16} />
                {tab.label}
              </button>
            ))}
          </div>

          {status.state === 'running' && (
            <div className="status running">
              <Icon name="spinner" size={16} /> {status.message}
            </div>
          )}
          {status.state === 'done' && (
            <div className="status success">
              <Icon name="check" size={16} /> {status.message}
            </div>
          )}
          {status.state === 'error' && (
            <div className="status error">
              <Icon name="error" size={16} /> {status.message}
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
