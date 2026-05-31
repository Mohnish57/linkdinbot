import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

function TabPosts({ config, status, apiUrl }) {
  const settings = config.settings || {};
  const postSearch = settings.postSearch || {};
  const [keywords, setKeywords] = useState((postSearch.keywords || []).join(', '));
  const [maxPerKeyword, setMaxPerKeyword] = useState(postSearch.maxPostsPerKeyword || 20);
  const [posts, setPosts] = useState([]);
  const [subjectTemplate, setSubjectTemplate] = useState(settings.emailSubjectTemplate || '');
  const [bodyTemplate, setBodyTemplate] = useState(settings.emailBodyTemplate || '');
  const [dryRun, setDryRun] = useState(true);

  const fetchPosts = useCallback(async () => {
    try {
      const res = await axios.get(`${apiUrl}/api/results/posts`);
      setPosts(res.data.data || []);
    } catch (err) {
      console.error('Failed to fetch posts:', err);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchPosts();
  }, [fetchPosts]);

  const searchPosts = async () => {
    try {
      const kw = keywords.split(',').map(k => k.trim()).filter(k => k);
      const creds = {
        keywords: kw,
        max_per_keyword: parseInt(maxPerKeyword),
        linkedin_email: localStorage.getItem('linkedin_email'),
        linkedin_password: localStorage.getItem('linkedin_password'),
      };
      await axios.post(`${apiUrl}/api/bot/search-posts`, creds);
      setTimeout(fetchPosts, 3000); // Refresh after 3 seconds
    } catch (err) {
      alert(`Failed to search posts: ${err.message}`);
    }
  };

  const sendEmails = async (dryRunMode) => {
    try {
      const creds = {
        subject_template: subjectTemplate,
        body_template: bodyTemplate,
        dry_run: dryRunMode,
        only_unsent: true,
        gmail_user: localStorage.getItem('gmail_user'),
        gmail_app_password: localStorage.getItem('gmail_password'),
      };
      await axios.post(`${apiUrl}/api/bot/send-emails-posts`, creds);
      if (!dryRunMode) {
        setTimeout(fetchPosts, 3000); // Refresh after 3 seconds
      }
    } catch (err) {
      alert(`Failed to send emails: ${err.message}`);
    }
  };

  return (
    <div>
      <h2>📰 Search posts & outreach</h2>
      <p>Search public LinkedIn posts by keyword, collect emails found, and send outreach.</p>

      <div style={{ marginTop: '20px' }}>
        <label><strong>Keywords (comma-separated)</strong></label>
        <textarea
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          style={{ width: '100%', height: '80px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          placeholder="python developer, remote backend, ..."
        />
      </div>

      <div style={{ marginTop: '15px' }}>
        <label><strong>Max posts per keyword</strong></label>
        <input
          type="number"
          min="1"
          max="500"
          value={maxPerKeyword}
          onChange={(e) => setMaxPerKeyword(e.target.value)}
          style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '15px' }}>
        <button
          onClick={searchPosts}
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
          🔎 Search posts
        </button>
      </div>

      {posts.length > 0 && (
        <div style={{ marginTop: '25px' }}>
          <h3>Collected posts & emails ({posts.length})</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9em' }}>
            <thead>
              <tr style={{ background: '#f5f5f5', borderBottom: '1px solid #ddd' }}>
                <th style={{ textAlign: 'left', padding: '8px' }}>Keyword</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Profile</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Email</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Sent</th>
              </tr>
            </thead>
            <tbody>
              {posts.slice(0, 20).map((p, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '8px' }}>{p.keyword}</td>
                  <td style={{ padding: '8px' }}>{p.profile_name}</td>
                  <td style={{ padding: '8px' }}>{p.email || '—'}</td>
                  <td style={{ padding: '8px' }}>{p.email_sent ? '✅' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {posts.length > 20 && <p style={{ marginTop: '10px', fontSize: '0.9em', color: '#666' }}>Showing 20 of {posts.length}</p>}
        </div>
      )}

      <div style={{ marginTop: '25px', borderTop: '1px solid #e0e0e0', paddingTop: '20px' }}>
        <h3>Send outreach emails</h3>
        <div style={{ marginTop: '15px' }}>
          <label><strong>Email subject</strong></label>
          <input
            type="text"
            value={subjectTemplate}
            onChange={(e) => setSubjectTemplate(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder="Hello {name}..."
          />
        </div>

        <div style={{ marginTop: '15px' }}>
          <label><strong>Email body</strong></label>
          <textarea
            value={bodyTemplate}
            onChange={(e) => setBodyTemplate(e.target.value)}
            style={{ width: '100%', height: '200px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder="Hi {name}, I am {candidate_name}..."
          />
        </div>

        <label style={{ marginTop: '15px', display: 'block' }}>
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
          />
          Dry run (don't actually send)
        </label>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '15px' }}>
          <button
            onClick={() => sendEmails(true)}
            disabled={status.state === 'running'}
            style={{
              padding: '10px',
              background: '#ffa500',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: status.state === 'running' ? 'not-allowed' : 'pointer',
              opacity: status.state === 'running' ? 0.6 : 1,
            }}
          >
            👀 Dry run
          </button>
          <button
            onClick={() => sendEmails(false)}
            disabled={status.state === 'running' || !localStorage.getItem('gmail_user')}
            style={{
              padding: '10px',
              background: '#388e3c',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: status.state === 'running' || !localStorage.getItem('gmail_user') ? 'not-allowed' : 'pointer',
              opacity: status.state === 'running' || !localStorage.getItem('gmail_user') ? 0.6 : 1,
              fontWeight: 'bold',
            }}
          >
            📨 Send NOW
          </button>
        </div>
      </div>
    </div>
  );
}

export default TabPosts;
