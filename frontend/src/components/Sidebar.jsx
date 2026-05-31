import React, { useState } from 'react';
import './Sidebar.css';
import Icon from './Icon';

function Sidebar() {
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
        <h2 className="heading-with-icon"><Icon name="key" /> LinkedIn login</h2>
        <input
          type="email"
          placeholder="LinkedIn ID or email"
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

        <h3 className="heading-with-icon"><Icon name="ai" /> Gemini</h3>
        <input
          type="password"
          placeholder="Gemini API key"
          value={geminiKey}
          onChange={(e) => setGeminiKey(e.target.value)}
          className="input"
        />

        <hr />

        <h3 className="heading-with-icon"><Icon name="mail" /> Gmail</h3>
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
       

        <hr />

        <button onClick={saveCredentials} className="btn btn-primary">
          <span className="button-with-icon"><Icon name="check" size={16} /> Save credentials</span>
        </button>
      </div>
    </aside>
  );
}

export default Sidebar;
