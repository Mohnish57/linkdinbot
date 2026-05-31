import React, { useState } from 'react';
import Icon from './Icon';

function TabEmail({ config, status, apiUrl }) {
  const settings = config.settings || {};
  const [subjectTemplate, setSubjectTemplate] = useState(settings.emailSubjectTemplate || '');
  const [bodyTemplate, setBodyTemplate] = useState(settings.emailBodyTemplate || '');

  const send = (dryRun) => {
    alert(`${dryRun ? 'Dry run preview' : 'Send'} — coming soon. Use the Posts tab for email functionality.`);
  };

  return (
    <div>
      <h2 className="heading-with-icon"><Icon name="mail" /> Email recruiters</h2>
      <p>Send personalised emails to collected recruiters from Stages 2 & 3.</p>

      <div style={{ marginTop: '20px' }}>
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
          style={{ width: '100%', height: '250px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          placeholder="Hi {name}, I am {candidate_name}..."
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '20px' }}>
        <button
          onClick={() => send(true)}
          style={{
            padding: '10px',
            background: '#ffa500',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          <span className="button-with-icon"><Icon name="eye" size={16} /> Dry run</span>
        </button>
        <button
          onClick={() => send(false)}
          style={{
            padding: '10px',
            background: '#388e3c',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontWeight: 'bold',
          }}
        >
          <span className="button-with-icon"><Icon name="send" size={16} /> Send now</span>
        </button>
      </div>
    </div>
  );
}

export default TabEmail;
