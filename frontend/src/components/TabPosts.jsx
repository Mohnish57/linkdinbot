import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'react-toastify';
import Icon from './Icon';

const card = {
  border: '1px solid #e0e0e0',
  borderRadius: '8px',
  padding: '24px',
  marginTop: '24px',
  background: '#fff',
};

// Shared spacing helpers so fields don't crowd each other.
const group = { marginTop: '22px' };
const lbl = { display: 'block', fontWeight: 600, marginBottom: '8px' };
const lblSub = { color: '#888', fontWeight: 400 };

const DEFAULT_NOTE = "Hi {name}, I'm {candidate_first_name} — {candidate_bio}. "
  + "Saw your post about the {job_title} role at {company}; I'd love to connect. Resume: {resume_link}";

function TabPosts({ config, saveConfig, status, apiUrl }) {
  const settings = config.settings || {};
  const candidate = config.candidate || {};
  const postSearch = settings.postSearch || {};
  const [keywords, setKeywords] = useState((postSearch.keywords || []).join(', '));
  const [postLimit, setPostLimit] = useState(Math.min(Math.max(postSearch.maxPostsPerKeyword || 20, 20), 50));
  const [recent24Hours, setRecent24Hours] = useState(postSearch.recent24Hours ?? true);
  const [noteTemplate, setNoteTemplate] = useState(settings.postInviteNoteTemplate || DEFAULT_NOTE);
  const [posts, setPosts] = useState([]);
  const [subjectTemplate, setSubjectTemplate] = useState(settings.emailSubjectTemplate || '');
  const [bodyTemplate, setBodyTemplate] = useState(settings.emailBodyTemplate || '');
  const [showPreview, setShowPreview] = useState(true);

  const fetchPosts = useCallback(async () => {
    try {
      const res = await axios.get(`${apiUrl}/api/results/posts`);
      setPosts(res.data.data || []);
    } catch (err) {
      console.error('Failed to fetch posts:', err);
    }
  }, [apiUrl]);

  useEffect(() => { fetchPosts(); }, [fetchPosts]);

  // Auto-refresh results while the bot is running.
  useEffect(() => {
    if (status.state !== 'running') return undefined;
    const id = setInterval(fetchPosts, 4000);
    return () => clearInterval(id);
  }, [status.state, fetchPosts]);

  const searchPosts = async () => {
    try {
      const kw = keywords.split(',').map(k => k.trim()).filter(k => k);
      const limit = Math.min(Math.max(parseInt(postLimit, 10) || 20, 20), 50);
      await saveConfig({
        settings: {
          postSearch: { keywords: kw, maxPostsPerKeyword: limit, recent24Hours },
          postInviteNoteTemplate: noteTemplate,
        },
      });
      await axios.post(`${apiUrl}/api/bot/search-posts`, {
        keywords: kw,
        max_per_keyword: limit,
        recent_24_hours: recent24Hours,
        linkedin_email: localStorage.getItem('linkedin_email'),
        linkedin_password: localStorage.getItem('linkedin_password'),
      });
      toast.info('Post search started — results refresh automatically.');
      setTimeout(fetchPosts, 3000);
    } catch (err) {
      toast.error(`Failed to search posts: ${err.message}`);
    }
  };

  const sendEmails = async (dryRunMode) => {
    try {
      await axios.post(`${apiUrl}/api/bot/send-emails-posts`, {
        subject_template: subjectTemplate,
        body_template: bodyTemplate,
        dry_run: dryRunMode,
        only_unsent: true,
        gmail_user: localStorage.getItem('gmail_user'),
        gmail_app_password: localStorage.getItem('gmail_password'),
      });
      toast.info(dryRunMode ? 'Dry run started.' : 'Sending emails — results refresh shortly.');
      if (!dryRunMode) setTimeout(fetchPosts, 3000);
    } catch (err) {
      toast.error(`Failed to send emails: ${err.message}`);
    }
  };

  const isTrue = (v) => v === true || String(v).toLowerCase() === 'true';

  const renderConnect = (statusRaw, noteSent) => {
    const s = (statusRaw || '').toString().toLowerCase();
    if (!s) return '—';
    if (s === 'pending') return isTrue(noteSent) ? '✉️ Invited + note' : '✉️ Invited';
    if (s === 'connected' || s === 'already-contacted') return '✔ Connected';
    if (s === 'limit') return '⛔ Weekly limit';
    if (s === 'skipped' || s === 'pending-no-button') return '∅ No connect';
    if (s === 'error') return '⚠️ Failed';
    return s;
  };

  // ---- Derived summary counts -------------------------------------------------
  const distinct = (arr) => [...new Set(arr.filter(Boolean))];
  const posterKey = (p) => (p.profile_link || p.profile_name || '').toString().toLowerCase();
  const postsFound = distinct(posts.map(posterKey)).length;
  const notesSent = distinct(posts.filter(p => isTrue(p.note_sent)).map(posterKey)).length;
  const invitesSent = distinct(
    posts.filter(p => ['pending'].includes((p.connect_status || '').toLowerCase())).map(posterKey)
  ).length;
  const uniqueEmails = distinct(posts.map(p => (p.email || '').toString().trim().toLowerCase()).filter(e => e.includes('@')));
  const unsentEmails = distinct(
    posts.filter(p => !isTrue(p.email_sent)).map(p => (p.email || '').toString().trim().toLowerCase()).filter(e => e.includes('@'))
  );
  const sentEmailsCount = uniqueEmails.length - unsentEmails.length;

  const sendEmailsWithConfirm = (dryRunMode) => {
    if (!dryRunMode) {
      if (!window.confirm(`Send this email to ${unsentEmails.length} unique address(es)? Already-emailed contacts are skipped.`)) return;
    }
    sendEmails(dryRunMode);
  };

  // ---- Live preview (substitute placeholders with a sample row) ---------------
  const sample = posts.find(p => (p.email || '').includes('@')) || posts[0] || {};
  const fill = (tpl) => (tpl || '')
    .replace(/\{name\}/g, (sample.profile_name || 'there').split(' ')[0])
    .replace(/\{role\}/g, sample.role || 'this role')
    .replace(/\{job_title\}/g, sample.role || 'this role')
    .replace(/\{company\}/g, sample.company || 'your company')
    .replace(/\{candidate_name\}/g, candidate.name || '')
    .replace(/\{candidate_first_name\}/g, candidate.first_name || '')
    .replace(/\{candidate_email\}/g, candidate.email || '')
    .replace(/\{candidate_bio_long\}/g, candidate.bio_fullstack || '')
    .replace(/\{candidate_bio\}/g, candidate.bio_fullstack || '')
    .replace(/\{resume_link\}/g, settings.resumeDriveLink || '');

  const namePlaceholderWarn =
    (noteTemplate.includes('{candidate_first_name}') && !candidate.first_name)
    || ((subjectTemplate + bodyTemplate).includes('{candidate_name}') && !candidate.name);

  const gmailReady = !!localStorage.getItem('gmail_user');
  const running = status.state === 'running';

  const Stat = ({ label, value, color }) => (
    <div style={{ flex: 1, textAlign: 'center', padding: '12px', background: '#f7f8fc', borderRadius: '8px' }}>
      <div style={{ fontSize: '1.8em', fontWeight: 700, color: color || '#333' }}>{value}</div>
      <div style={{ fontSize: '0.8em', color: '#666' }}>{label}</div>
    </div>
  );

  return (
    <div>
      <h2 className="heading-with-icon"><Icon name="document" /> LinkedIn post outreach</h2>

      {/* ============================ SECTION 1: SEARCH ======================== */}
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>1 · Search hiring posts</h3>
        <p style={{ color: '#666', fontSize: '0.9em', marginTop: 0 }}>
          Finds posts containing <strong>“hiring”</strong> or <strong>“looking for”</strong>, collects every email
          mentioned plus the poster (role &amp; company), and sends each poster a connection request <strong>with your note</strong>.
        </p>

        <div style={group}>
          <label style={lbl}>Keywords (comma-separated)</label>
          <textarea
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            style={{ width: '100%', height: '64px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder="frontend developer, full stack developer, ..."
          />
        </div>

        <div style={{ display: 'flex', gap: '20px', alignItems: 'center', marginTop: '20px', flexWrap: 'wrap' }}>
          <label>
            Posts per keyword{' '}
            <input type="number" min="20" max="50" value={postLimit}
              onChange={(e) => setPostLimit(e.target.value)}
              style={{ width: '70px', padding: '6px', borderRadius: '4px', border: '1px solid #ddd' }} />
          </label>
          <label>
            <input type="checkbox" checked={recent24Hours} onChange={(e) => setRecent24Hours(e.target.checked)} />
            {' '}Only last 24 hours
          </label>
          <button
            onClick={searchPosts}
            disabled={running}
            style={{ padding: '10px 18px', background: '#667eea', color: '#fff', border: 'none', borderRadius: '4px',
              cursor: running ? 'not-allowed' : 'pointer', opacity: running ? 0.6 : 1, marginLeft: 'auto' }}
          >
            <span className="button-with-icon"><Icon name="search" size={16} /> {running ? 'Running…' : 'Search & connect'}</span>
          </button>
        </div>

        <div style={group}>
          <label style={lbl}>Connection request note <span style={lblSub}>(max 300 chars · sent with each invite)</span></label>
          <textarea
            value={noteTemplate}
            onChange={(e) => setNoteTemplate(e.target.value)}
            maxLength={300}
            style={{ width: '100%', height: '84px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder={DEFAULT_NOTE}
          />
          <div style={{ fontSize: '0.78em', color: '#888', marginTop: '6px' }}>
            Placeholders: <code>{'{name} {job_title} {company} {candidate_first_name} {candidate_bio} {resume_link}'}</code> · {noteTemplate.length}/300
          </div>
          <div style={{ marginTop: '12px', border: '1px solid #d0d7e2', borderRadius: '6px', background: '#f7f8fc', padding: '12px', fontSize: '0.9em', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
            <span style={{ color: '#888', fontSize: '0.85em' }}>Preview: </span>{fill(noteTemplate).slice(0, 300)}
          </div>
          {namePlaceholderWarn && (
            <p style={{ color: '#c0392b', fontSize: '0.82em', marginTop: '10px' }}>
              ⚠ Your name/bio is empty — set it in the <strong>Setup</strong> tab, or it'll read "I'm Your".
            </p>
          )}
        </div>
      </div>

      {/* ============================ SECTION 2: RESULTS ======================= */}
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>2 · Results</h3>
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <Stat label="Posts found" value={postsFound} color="#667eea" />
          <Stat label="Invites sent" value={invitesSent} color="#0a66c2" />
          <Stat label="Notes attached" value={notesSent} color="#388e3c" />
          <Stat label="Emails collected" value={uniqueEmails.length} color="#b8860b" />
          <Stat label="Emails sent" value={sentEmailsCount} color="#388e3c" />
        </div>

        {posts.length > 0 ? (
          <div style={{ marginTop: '18px', overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88em' }}>
              <thead>
                <tr style={{ background: '#f5f5f5', borderBottom: '1px solid #ddd' }}>
                  <th style={{ textAlign: 'left', padding: '8px' }}>Poster</th>
                  <th style={{ textAlign: 'left', padding: '8px' }}>Role</th>
                  <th style={{ textAlign: 'left', padding: '8px' }}>Company</th>
                  <th style={{ textAlign: 'left', padding: '8px' }}>Email</th>
                  <th style={{ textAlign: 'left', padding: '8px' }}>Connection</th>
                  <th style={{ textAlign: 'left', padding: '8px' }}>Emailed</th>
                </tr>
              </thead>
              <tbody>
                {posts.slice(0, 50).map((p, i) => (
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
                    <td style={{ padding: '8px' }}>{isTrue(p.email_sent) ? <span className="inline-status"><Icon name="check" size={14} /> Sent</span> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {posts.length > 50 && <p style={{ fontSize: '0.85em', color: '#666' }}>Showing 50 of {posts.length} rows.</p>}
          </div>
        ) : (
          <p style={{ color: '#888', marginTop: '14px' }}>No results yet — run a search above.</p>
        )}
      </div>

      {/* ====================== SECTION 3: EMAIL OUTREACH ====================== */}
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>3 · Email everyone collected</h3>
        <p style={{ color: '#666', fontSize: '0.9em', marginTop: 0 }}>
          Compose once and send to all <strong>{unsentEmails.length}</strong> not-yet-emailed address(es).
          Placeholders: <code>{'{name} {role} {company} {candidate_name} {resume_link}'}</code>
        </p>

        <div style={group}>
          <label style={lbl}>Subject</label>
          <input
            type="text" value={subjectTemplate} onChange={(e) => setSubjectTemplate(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder="Referral request: {role} at {company}"
          />
        </div>

        <div style={group}>
          <label style={lbl}>Body</label>
          <textarea
            value={bodyTemplate} onChange={(e) => setBodyTemplate(e.target.value)}
            style={{ width: '100%', height: '170px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder="Hi {name}, I saw your {role} post at {company}..."
          />
        </div>

        <label style={{ display: 'block', marginTop: '16px' }}>
          <input type="checkbox" checked={showPreview} onChange={(e) => setShowPreview(e.target.checked)} />
          {' '}Show preview
        </label>

        {showPreview && (
          <div style={{ marginTop: '10px', border: '1px solid #d0d7e2', borderRadius: '8px', overflow: 'hidden' }}>
            <div style={{ background: '#f0f3fa', padding: '8px 12px', fontSize: '0.8em', color: '#555' }}>
              Preview {sample.profile_name ? `(for ${sample.profile_name})` : '(sample)'}
            </div>
            <div style={{ padding: '12px' }}>
              <div style={{ fontWeight: 600, marginBottom: '8px' }}>{fill(subjectTemplate) || <em style={{ color: '#999' }}>No subject</em>}</div>
              <div style={{ whiteSpace: 'pre-wrap', fontSize: '0.9em', color: '#333' }}>
                {fill(bodyTemplate) || <em style={{ color: '#999' }}>No body</em>}
              </div>
            </div>
          </div>
        )}

        {!gmailReady && (
          <p style={{ color: '#c0392b', fontSize: '0.85em', marginTop: '10px' }}>
            ⚠ Set your Gmail user + app password in the sidebar to enable sending.
          </p>
        )}

        <div style={{ display: 'flex', gap: '10px', marginTop: '14px' }}>
          <button
            onClick={() => sendEmailsWithConfirm(true)}
            disabled={running}
            style={{ padding: '10px 16px', background: '#ffa500', color: '#fff', border: 'none', borderRadius: '4px',
              cursor: running ? 'not-allowed' : 'pointer', opacity: running ? 0.6 : 1 }}
          >
            <span className="button-with-icon"><Icon name="eye" size={16} /> Dry run</span>
          </button>
          <button
            onClick={() => sendEmailsWithConfirm(false)}
            disabled={running || !gmailReady || unsentEmails.length === 0}
            style={{ padding: '10px 16px', background: '#388e3c', color: '#fff', border: 'none', borderRadius: '4px', fontWeight: 'bold',
              cursor: (running || !gmailReady || unsentEmails.length === 0) ? 'not-allowed' : 'pointer',
              opacity: (running || !gmailReady || unsentEmails.length === 0) ? 0.6 : 1 }}
          >
            <span className="button-with-icon"><Icon name="send" size={16} /> Send to all ({unsentEmails.length})</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default TabPosts;
