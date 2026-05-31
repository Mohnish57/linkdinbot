import React, { useState } from 'react';
import './Sidebar.css';

function Sidebar({ config, saveConfig }) {
  const candidate = config.candidate || {};

  const [linkedinEmail, setLinkedinEmail] = useState(localStorage.getItem('linkedin_email') || '');
  const [linkedinPassword, setLinkedinPassword] = useState(localStorage.getItem('linkedin_password') || '');
  const [geminiKey, setGeminiKey] = useState(localStorage.getItem('gemini_key') || '');
  const [gmailUser, setGmailUser] = useState(localStorage.getItem('gmail_user') || '');
  const [gmailPassword, setGmailPassword] = useState(localStorage.getItem('gmail_password') || '');

  const saveCredentials = () => {
    localStorage.setItem('linkedin_email', linkedinEmail);
    localStorage.setItem('linkedin_password', linkedinPassword);
    localStorage.setItem('gemini_key', geminiKey);
    localStorage.setItem('gmail_user', gmailUser);
    localStorage.setItem('gmail_password', gmailPassword);
    alert('Credentials saved locally (browser storage)');
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-content">
        <h2>👤 You</h2>
        <input
          type="text"
          placeholder="Full name"
          defaultValue={candidate.name || ''}
          onChange={(e) => saveConfig({ candidate: { ...candidate, name: e.target.value } })}
          className="input"
        />
        <input
          type="text"
          placeholder="First name"
          defaultValue={candidate.first_name || ''}
          onChange={(e) => saveConfig({ candidate: { ...candidate, first_name: e.target.value } })}
          className="input"
        />
        <input
          type="email"
          placeholder="Your email"
          defaultValue={candidate.email || ''}
          onChange={(e) => saveConfig({ candidate: { ...candidate, email: e.target.value } })}
          className="input"
        />

        <hr />

        <h3>🔑 LinkedIn login</h3>
        <input
          type="email"
          placeholder="LinkedIn email"
          value={linkedinEmail}
          onChange={(e) => setLinkedinEmail(e.target.value)}
          className="input"
        />
        <input
          type="password"
          placeholder="LinkedIn password"
          value={linkedinPassword}
          onChange={(e) => setLinkedinPassword(e.target.value)}
          className="input"
        />

        <hr />

        <h3>🤖 Gemini</h3>
        <input
          type="password"
          placeholder="Gemini API key"
          value={geminiKey}
          onChange={(e) => setGeminiKey(e.target.value)}
          className="input"
        />

        <hr />

        <h3>📨 Gmail</h3>
        <input
          type="email"
          placeholder="Gmail address"
          value={gmailUser}
          onChange={(e) => setGmailUser(e.target.value)}
          className="input"
        />
        <input
          type="password"
          placeholder="App Password (16 chars)"
          value={gmailPassword}
          onChange={(e) => setGmailPassword(e.target.value)}
          className="input"
        />
        <p style={{ fontSize: '0.85em', marginTop: '8px' }}>
          Create at <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">myaccount.google.com/apppasswords</a>
        </p>

        <hr />

        <button onClick={saveCredentials} className="btn btn-primary">
          💾 Save credentials
        </button>
      </div>
    </aside>
  );
}

export default Sidebar;
