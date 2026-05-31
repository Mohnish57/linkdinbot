import React, { useState } from 'react';
import axios from 'axios';

function TabRun({ config, status, apiUrl }) {
  const [headless, setHeadless] = useState(false);

  const runStage = async (stage) => {
    try {
      const creds = {
        linkedin_email: localStorage.getItem('linkedin_email'),
        linkedin_password: localStorage.getItem('linkedin_password'),
        gemini_key: localStorage.getItem('gemini_key'),
        gmail_user: localStorage.getItem('gmail_user'),
        gmail_app_password: localStorage.getItem('gmail_password'),
        headless,
      };
      await axios.post(`${apiUrl}/api/bot/${stage}`, creds);
    } catch (err) {
      alert(`Failed to start ${stage}: ${err.message}`);
    }
  };

  return (
    <div>
      <h2>▶️ Run the Bot</h2>
      <p><strong>Stage 1</strong> — find matching jobs. <strong>Stage 2</strong> — invite hirer + recruiters. <strong>Stage 3</strong> — scrape emails.</p>

      <div style={{ marginTop: '20px' }}>
        <label>
          <input
            type="checkbox"
            checked={headless}
            onChange={(e) => setHeadless(e.target.checked)}
          />
          Run Chrome headless (no visible browser)
        </label>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '10px', marginTop: '20px' }}>
        <button
          onClick={() => runStage('stage1')}
          disabled={status.state === 'running'}
          style={{
            padding: '10px',
            background: '#667eea',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: status.state === 'running' ? 'not-allowed' : 'pointer',
            opacity: status.state === 'running' ? 0.6 : 1,
          }}
        >
          🔍 Stage 1 — Jobs
        </button>
        <button
          onClick={() => runStage('stage2')}
          disabled={status.state === 'running'}
          style={{
            padding: '10px',
            background: '#667eea',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: status.state === 'running' ? 'not-allowed' : 'pointer',
            opacity: status.state === 'running' ? 0.6 : 1,
          }}
        >
          🤝 Stage 2 — Invites
        </button>
        <button
          onClick={() => runStage('stage3')}
          disabled={status.state === 'running'}
          style={{
            padding: '10px',
            background: '#667eea',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: status.state === 'running' ? 'not-allowed' : 'pointer',
            opacity: status.state === 'running' ? 0.6 : 1,
          }}
        >
          📇 Stage 3 — Emails
        </button>
        <button
          onClick={() => { runStage('stage1'); setTimeout(() => runStage('stage2'), 2000); }}
          disabled={status.state === 'running'}
          style={{
            padding: '10px',
            background: '#764ba2',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: status.state === 'running' ? 'not-allowed' : 'pointer',
            opacity: status.state === 'running' ? 0.6 : 1,
            fontWeight: 'bold',
          }}
        >
          ⚡ Stages 1 → 2
        </button>
      </div>

      {status.state === 'running' && (
        <p style={{ marginTop: '20px', color: '#1976d2' }}>⏳ {status.message}</p>
      )}
      {status.state === 'done' && (
        <p style={{ marginTop: '20px', color: '#388e3c' }}>✅ {status.message}</p>
      )}
      {status.state === 'error' && (
        <p style={{ marginTop: '20px', color: '#d32f2f' }}>❌ {status.message}</p>
      )}
    </div>
  );
}

export default TabRun;
