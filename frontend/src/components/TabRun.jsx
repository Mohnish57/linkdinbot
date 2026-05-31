import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'react-toastify';
import Icon from './Icon';

function TabRun({ status, apiUrl }) {
  const [headless, setHeadless] = useState(false);
  const [resumes, setResumes] = useState({});

  const fetchResumes = useCallback(async () => {
    try {
      const res = await axios.get(`${apiUrl}/api/resumes`);
      setResumes(res.data.resumes || {});
    } catch (err) {
      console.error('Failed to load resumes:', err);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchResumes();
  }, [fetchResumes]);

  const runStage = async (stage) => {
    try {
      const creds = {
        linkedin_email: localStorage.getItem('linkedin_email'),
        linkedin_password: localStorage.getItem('linkedin_password'),
        gemini_key: localStorage.getItem('gemini_key'),
        gmail_user: localStorage.getItem('gmail_user'),
        gmail_app_password: localStorage.getItem('gmail_password'),
        headless,
        resume_fullstack: resumes.fullstack?.path,
        resume_frontend: resumes.frontend?.path,
      };
      await axios.post(`${apiUrl}/api/bot/${stage}`, creds);
      toast.info(`${stage} started.`);
    } catch (err) {
      toast.error(`Failed to start ${stage}: ${err.message}`);
    }
  };

  return (
    <div>
      <h2 className="heading-with-icon"><Icon name="play" /> Run the Bot</h2>
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
          <span className="button-with-icon"><Icon name="search" size={16} /> Stage 1 — Jobs</span>
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
          <span className="button-with-icon"><Icon name="users" size={16} /> Stage 2 — Invites</span>
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
          <span className="button-with-icon"><Icon name="mail" size={16} /> Stage 3 — Emails</span>
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
          <span className="button-with-icon"><Icon name="chevronsRight" size={16} /> Stages 1 → 2</span>
        </button>
      </div>

      {status.state === 'running' && (
        <p className="inline-status" style={{ marginTop: '20px', color: '#1976d2' }}><Icon name="spinner" size={16} /> {status.message}</p>
      )}
      {status.state === 'done' && (
        <p className="inline-status" style={{ marginTop: '20px', color: '#388e3c' }}><Icon name="check" size={16} /> {status.message}</p>
      )}
      {status.state === 'error' && (
        <p className="inline-status" style={{ marginTop: '20px', color: '#d32f2f' }}><Icon name="error" size={16} /> {status.message}</p>
      )}
    </div>
  );
}

export default TabRun;
