import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'react-toastify';
import Icon from './Icon';

function TabPosts({ config, saveConfig, status, apiUrl }) {
  const settings = config.settings || {};
  const postSearch = settings.postSearch || {};
  const [keywords, setKeywords] = useState((postSearch.keywords || []).join(', '));
  const [postLimit, setPostLimit] = useState(Math.min(Math.max(postSearch.maxPostsPerKeyword || 20, 20), 50));
  const [recent24Hours, setRecent24Hours] = useState(postSearch.recent24Hours ?? true);
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
      const limit = Math.min(Math.max(parseInt(postLimit, 10) || 20, 20), 50);
      await saveConfig({
        settings: {
          postSearch: {
            keywords: kw,
            maxPostsPerKeyword: limit,
            recent24Hours,
          },
        },
      });
      const creds = {
        keywords: kw,
        max_per_keyword: limit,
        recent_24_hours: recent24Hours,
        linkedin_email: localStorage.getItem('linkedin_email'),
        linkedin_password: localStorage.getItem('linkedin_password'),
      };
      await axios.post(`${apiUrl}/api/bot/search-posts`, creds);
      toast.info('Post search started — results will refresh shortly.');
      setTimeout(fetchPosts, 3000); // Refresh after 3 seconds
    } catch (err) {
      toast.error(`Failed to search posts: ${err.message}`);
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
      toast.info(dryRunMode ? 'Dry run started.' : 'Sending emails — results will refresh shortly.');
      if (!dryRunMode) {
        setTimeout(fetchPosts, 3000); // Refresh after 3 seconds
      }
    } catch (err) {
      toast.error(`Failed to send emails: ${err.message}`);
    }
  };

  const isSent = (v) => v === true || String(v).toLowerCase() === 'true';

  const renderConnect = (statusRaw, noteSent) => {
    const status = (statusRaw || '').toString().toLowerCase();
    if (!status) return '—';
    if (status === 'pending') return isSent(noteSent) ? '✉️ Invited (note)' : '✉️ Invited';
    if (status === 'connected' || status === 'already-contacted') return '✔ Connected';
    if (status === 'limit') return '⛔ Weekly limit';
    if (status === 'error') return '⚠️ Failed';
    return status;
  };

  // Unique email addresses across all collected rows (case-insensitive).
  const uniqueEmails = [...new Set(
    posts.map(p => (p.email || '').toString().trim().toLowerCase()).filter(e => e.includes('@'))
  )];
  const uniqueEmailCount = uniqueEmails.length;
  const unsentEmailCount = [...new Set(
    posts.filter(p => !isSent(p.email_sent)).map(p => (p.email || '').toString().trim().toLowerCase()).filter(e => e.includes('@'))
  )].length;

  const sendEmailsWithConfirm = (dryRunMode) => {
    if (!dryRunMode) {
      const ok = window.confirm(`Send your email to ${unsentEmailCount} unique address(es)? Already-emailed contacts are skipped.`);
      if (!ok) return;
    }
    sendEmails(dryRunMode);
  };

  return (
    <div>
      <h2 className="heading-with-icon"><Icon name="document" /> Search posts & outreach</h2>
      <p>Search recent LinkedIn posts by keyword. The bot collects <strong>every email</strong> mentioned in each post plus the person who posted it, parses the role &amp; company, and <strong>automatically sends each poster a connection request with a note</strong>. Then email all collected addresses below.</p>

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
        <label><strong>Best-match posts to review</strong></label>
        <input
          type="number"
          min="20"
          max="50"
          value={postLimit}
          onChange={(e) => setPostLimit(e.target.value)}
          style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
        />
      </div>

      <label style={{ marginTop: '15px', display: 'block' }}>
        <input
          type="checkbox"
          checked={recent24Hours}
          onChange={(e) => setRecent24Hours(e.target.checked)}
        />
        Only recent posts from the last 24 hours
      </label>

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
          <span className="button-with-icon"><Icon name="search" size={16} /> Search posts</span>
        </button>
      </div>

      {posts.length > 0 && (
        <div style={{ marginTop: '25px' }}>
          <h3>Collected emails ({uniqueEmailCount} unique) · {posts.length} rows</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9em' }}>
            <thead>
              <tr style={{ background: '#f5f5f5', borderBottom: '1px solid #ddd' }}>
                <th style={{ textAlign: 'left', padding: '8px' }}>Profile</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Role</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Company</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Email</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Connect</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Emailed</th>
              </tr>
            </thead>
            <tbody>
              {posts.slice(0, 20).map((p, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '8px' }}>
                    {p.profile_link
                      ? <a href={p.profile_link} target="_blank" rel="noreferrer">{p.profile_name || 'Profile'}</a>
                      : (p.profile_name || '—')}
                  </td>
                  <td style={{ padding: '8px' }}>{p.role || '—'}</td>
                  <td style={{ padding: '8px' }}>{p.company || '—'}</td>
                  <td style={{ padding: '8px' }}>{p.email || '—'}</td>
                  <td style={{ padding: '8px' }}>{renderConnect(p.connect_status, p.note_sent)}</td>
                  <td style={{ padding: '8px' }}>{isSent(p.email_sent) ? <span className="inline-status"><Icon name="check" size={14} /> Sent</span> : '—'}</td>
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
            onClick={() => sendEmailsWithConfirm(true)}
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
            <span className="button-with-icon"><Icon name="eye" size={16} /> Dry run</span>
          </button>
          <button
            onClick={() => sendEmailsWithConfirm(false)}
            disabled={status.state === 'running' || !localStorage.getItem('gmail_user') || unsentEmailCount === 0}
            style={{
              padding: '10px',
              background: '#388e3c',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: status.state === 'running' || !localStorage.getItem('gmail_user') || unsentEmailCount === 0 ? 'not-allowed' : 'pointer',
              opacity: status.state === 'running' || !localStorage.getItem('gmail_user') || unsentEmailCount === 0 ? 0.6 : 1,
              fontWeight: 'bold',
            }}
          >
            <span className="button-with-icon"><Icon name="send" size={16} /> Send to all emails ({unsentEmailCount})</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default TabPosts;
