import React from 'react';

function TabAI({ config, saveConfig }) {
  const settings = config.settings || {};

  return (
    <div>
      <h2>🧠 AI Prompt</h2>
      <p>Used when Gemini evaluates each job. Placeholders: {'{candidate_name}'}, {'{candidate_profile_block}'}, {'{candidate_pitch}'}, {'{resume_link}'}, {'{candidate_email}'}.</p>

      <div style={{ marginTop: '20px' }}>
        <textarea
          defaultValue={settings.aiSystemPromptTemplate || ''}
          style={{ width: '100%', height: '400px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', fontFamily: 'monospace' }}
          placeholder="Enter your AI system prompt template here..."
        />
      </div>

      <button onClick={() => alert('Saved!')} style={{ marginTop: '20px', padding: '10px 20px', background: '#667eea', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
        💾 Save
      </button>
    </div>
  );
}

export default TabAI;
