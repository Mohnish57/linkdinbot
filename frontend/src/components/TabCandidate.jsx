import React from 'react';

function TabCandidate({ config, saveConfig }) {
  const candidate = config.candidate || {};

  const save = () => {
    alert('Candidate profile saved!');
  };

  return (
    <div>
      <h2>🪪 Candidate Profile</h2>
      <p>Everything here is configurable — change once, reflected everywhere.</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '20px' }}>
        <div>
          <label><strong>Short bio — Full Stack</strong></label>
          <input
            type="text"
            defaultValue={candidate.bio_fullstack || ''}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder="≤ 60 chars"
          />
        </div>
        <div>
          <label><strong>Short bio — Frontend</strong></label>
          <input
            type="text"
            defaultValue={candidate.bio_frontend || ''}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder="≤ 60 chars"
          />
        </div>
      </div>

      <div style={{ marginTop: '20px' }}>
        <label><strong>Long pitch</strong></label>
        <textarea
          defaultValue={candidate.pitch || ''}
          style={{ width: '100%', height: '120px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          placeholder="Used in DM follow-up"
        />
      </div>

      <div style={{ marginTop: '20px' }}>
        <label><strong>AI profile block</strong></label>
        <textarea
          defaultValue={candidate.profile_block || ''}
          style={{ width: '100%', height: '200px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          placeholder="Full bullet list, used in AI prompt"
        />
      </div>

      <button onClick={save} style={{ marginTop: '20px', padding: '10px 20px', background: '#667eea', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
        💾 Save
      </button>
    </div>
  );
}

export default TabCandidate;
