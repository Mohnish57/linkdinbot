import React from 'react';
import Icon from './Icon';

function TabNotes({ config, saveConfig }) {
  const settings = config.settings || {};

  return (
    <div>
      <h2 className="heading-with-icon"><Icon name="message" /> Invite Note Templates</h2>
      <p>Placeholders: {'{name}'}, {'{job_title}'}, {'{company}'}, {'{resume_link}'}, {'{candidate_first_name}'}, {'{candidate_bio}'}. LinkedIn cap: 300 chars.</p>

      <div style={{ marginTop: '20px' }}>
        <h3>Recruiter invites</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          <div>
            <label><strong>Full Stack</strong></label>
            <textarea
              defaultValue={settings.inviteNoteTemplate || ''}
              style={{ width: '100%', height: '150px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            />
          </div>
          <div>
            <label><strong>Frontend</strong></label>
            <textarea
              defaultValue={settings.inviteNoteTemplateFrontend || ''}
              style={{ width: '100%', height: '150px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            />
          </div>
        </div>
      </div>

      <div style={{ marginTop: '20px' }}>
        <h3>Hirer (job poster) invites</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          <div>
            <label><strong>Full Stack</strong></label>
            <textarea
              defaultValue={settings.inviteNoteTemplateHirer || ''}
              style={{ width: '100%', height: '150px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            />
          </div>
          <div>
            <label><strong>Frontend</strong></label>
            <textarea
              defaultValue={settings.inviteNoteTemplateHirerFrontend || ''}
              style={{ width: '100%', height: '150px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            />
          </div>
        </div>
      </div>

      <button onClick={() => alert('Saved!')} style={{ marginTop: '20px', padding: '10px 20px', background: '#667eea', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
        <span className="button-with-icon"><Icon name="check" size={16} /> Save</span>
      </button>
    </div>
  );
}

export default TabNotes;
