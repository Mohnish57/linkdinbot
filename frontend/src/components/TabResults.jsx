import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'react-toastify';
import Icon from './Icon';

function TabResults({ apiUrl }) {
  const [jobs, setJobs] = useState([]);
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchResults = useCallback(async () => {
    try {
      const [jobsRes, connRes] = await Promise.all([
        axios.get(`${apiUrl}/api/results/jobs`),
        axios.get(`${apiUrl}/api/results/connections`),
      ]);
      setJobs(jobsRes.data.data || []);
      setConnections(connRes.data.data || []);
    } catch (err) {
      console.error('Failed to fetch results:', err);
    }
    setLoading(false);
  }, [apiUrl]);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  const clearResults = async () => {
    if (window.confirm('Clear all collected data?')) {
      try {
        await axios.post(`${apiUrl}/api/results/clear`);
        setJobs([]);
        setConnections([]);
        toast.success('Cleared!');
      } catch (err) {
        toast.error(`Failed to clear: ${err.message}`);
      }
    }
  };

  if (loading) return <div>Loading...</div>;

  const emailCount = connections.filter(c => c.email).length;
  const sentCount = connections.filter(c => c.email_sent).length;

  return (
    <div>
      <h2 className="heading-with-icon"><Icon name="table" /> Results</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '15px', marginTop: '20px' }}>
        <div style={{ background: 'white', padding: '15px', borderRadius: '4px', textAlign: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ fontSize: '2em', fontWeight: 'bold', color: '#667eea' }}>{jobs.length}</div>
          <div style={{ color: '#666', marginTop: '5px' }}>Jobs matched</div>
        </div>
        <div style={{ background: 'white', padding: '15px', borderRadius: '4px', textAlign: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ fontSize: '2em', fontWeight: 'bold', color: '#667eea' }}>{connections.length}</div>
          <div style={{ color: '#666', marginTop: '5px' }}>Profiles touched</div>
        </div>
        <div style={{ background: 'white', padding: '15px', borderRadius: '4px', textAlign: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ fontSize: '2em', fontWeight: 'bold', color: '#667eea' }}>{emailCount}</div>
          <div style={{ color: '#666', marginTop: '5px' }}>Emails collected</div>
        </div>
        <div style={{ background: 'white', padding: '15px', borderRadius: '4px', textAlign: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ fontSize: '2em', fontWeight: 'bold', color: '#667eea' }}>{sentCount}</div>
          <div style={{ color: '#666', marginTop: '5px' }}>Emails sent</div>
        </div>
      </div>

      <h3 style={{ marginTop: '25px' }}>Jobs</h3>
      {jobs.length === 0 ? (
        <p style={{ color: '#999' }}>No jobs yet — run Stage 1.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9em' }}>
          <thead>
            <tr style={{ background: '#f5f5f5', borderBottom: '1px solid #ddd' }}>
              <th style={{ textAlign: 'left', padding: '8px' }}>Title</th>
              <th style={{ textAlign: 'left', padding: '8px' }}>Company</th>
              <th style={{ textAlign: 'left', padding: '8px' }}>Match score</th>
            </tr>
          </thead>
          <tbody>
            {jobs.slice(0, 10).map((j, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '8px' }}>{j.job_title}</td>
                <td style={{ padding: '8px' }}>{j.company_name}</td>
                <td style={{ padding: '8px' }}>{j.match_score || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 style={{ marginTop: '25px' }}>Recruiters / Hirers</h3>
      {connections.length === 0 ? (
        <p style={{ color: '#999' }}>No connections yet — run Stages 2 & 3.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9em' }}>
          <thead>
            <tr style={{ background: '#f5f5f5', borderBottom: '1px solid #ddd' }}>
              <th style={{ textAlign: 'left', padding: '8px' }}>Name</th>
              <th style={{ textAlign: 'left', padding: '8px' }}>Job Title</th>
              <th style={{ textAlign: 'left', padding: '8px' }}>Email</th>
              <th style={{ textAlign: 'left', padding: '8px' }}>Sent</th>
            </tr>
          </thead>
          <tbody>
            {connections.slice(0, 10).map((c, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '8px' }}>{c.profile_name}</td>
                <td style={{ padding: '8px' }}>{c.job_title}</td>
                <td style={{ padding: '8px' }}>{c.email || '—'}</td>
                <td style={{ padding: '8px' }}>{c.email_sent ? <span className="inline-status"><Icon name="check" size={14} /> Sent</span> : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <button
        onClick={clearResults}
        style={{
          marginTop: '20px',
          padding: '10px 20px',
          background: '#d32f2f',
          color: 'white',
          border: 'none',
          borderRadius: '4px',
          cursor: 'pointer',
        }}
      >
        <span className="button-with-icon"><Icon name="trash" size={16} /> Clear all data</span>
      </button>
    </div>
  );
}

export default TabResults;
