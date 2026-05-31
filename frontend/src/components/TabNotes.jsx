import React, { useState } from 'react';
import Icon from './Icon';

const DEFAULT_INVITE_NOTE = `Hi {name}, I came across the {job_title} opening at your company and believe my experience aligns well with the role.
I'd love to connect. Resume: {drive_link}`;

function TabNotes({ config, saveConfig }) {
  const settings = config.settings || {};
  const [inviteNote, setInviteNote] = useState(settings.inviteNoteTemplate || DEFAULT_INVITE_NOTE);

  const save = async () => {
    await saveConfig({
      settings: {
        inviteNoteTemplate: inviteNote,
        inviteNoteTemplateFrontend: inviteNote,
        inviteNoteTemplateHirer: inviteNote,
        inviteNoteTemplateHirerFrontend: inviteNote,
        sendInviteNote: true,
      },
    });
    alert('Invite note saved!');
  };

  return (
    <div>
      <h2 className="heading-with-icon"><Icon name="message" /> Invite Note</h2>
      <p>Available placeholders: {'{name}'}, {'{job_title}'}, {'{company}'}, {'{drive_link}'}.</p>

      <div style={{ marginTop: '20px' }}>
        <label><strong>Connection invite message</strong></label>
        <textarea
          value={inviteNote}
          onChange={(e) => setInviteNote(e.target.value)}
          style={{ width: '100%', height: '170px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
        />
      </div>

      <button onClick={save} style={{ marginTop: '20px', padding: '10px 20px', background: '#667eea', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
        <span className="button-with-icon"><Icon name="check" size={16} /> Save invite note</span>
      </button>
    </div>
  );
}

export default TabNotes;
