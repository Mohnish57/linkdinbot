import React, { useState } from 'react';
import Icon from './Icon';

function TabSetup({ config, saveConfig }) {
  const prefs = config.jobPreferences || {};
  const settings = config.settings || {};
  
  const [positions, setPositions] = useState((prefs.positions || []).join('\n'));
  const [recruiterKeywords, setRecruiterKeywords] = useState((prefs.recruiterKeywords || []).join('\n'));
  const [peopleProfiles, setPeopleProfiles] = useState((prefs.people_profiles || []).join('\n'));
  const [blacklistedTitles, setBlacklistedTitles] = useState((prefs.blacklistedTitles || []).join('\n'));

  const save = () => {
    saveConfig({
      jobPreferences: {
        positions: positions.split('\n').filter(p => p.trim()),
        recruiterKeywords: recruiterKeywords.split('\n').filter(k => k.trim()),
        people_profiles: peopleProfiles.split('\n').filter(p => p.trim()),
        blacklistedTitles: blacklistedTitles.split('\n').filter(t => t.trim()),
      },
    });
    alert('Saved!');
  };

  return (
    <div>
      <h2 className="heading-with-icon"><Icon name="settings" /> Setup</h2>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '20px' }}>
        <div>
          <label><strong>Positions to search (one per line)</strong></label>
          <textarea
            value={positions}
            onChange={(e) => setPositions(e.target.value)}
            style={{ width: '100%', height: '150px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          />
        </div>
        <div>
          <label><strong>Recruiter keywords (one per line)</strong></label>
          <textarea
            value={recruiterKeywords}
            onChange={(e) => setRecruiterKeywords(e.target.value)}
            style={{ width: '100%', height: '150px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '20px' }}>
        <div>
          <label><strong>People search keywords (one per line)</strong></label>
          <textarea
            value={peopleProfiles}
            onChange={(e) => setPeopleProfiles(e.target.value)}
            style={{ width: '100%', height: '150px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          />
        </div>
        <div>
          <label><strong>Blacklisted job titles (one per line)</strong></label>
          <textarea
            value={blacklistedTitles}
            onChange={(e) => setBlacklistedTitles(e.target.value)}
            style={{ width: '100%', height: '150px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          />
        </div>
      </div>

      <div style={{ marginTop: '20px' }}>
        <h3>Bot toggles</h3>
        <label>
          <input type="checkbox" defaultChecked={settings.recruitersOnly} />
          Only message recruiters
        </label><br/>
        <label>
          <input type="checkbox" defaultChecked={settings.sendInviteNote} />
          Attach personalised note to each invite
        </label><br/>
        <label>
          <input type="checkbox" defaultChecked={settings.contactHirerFirst} />
          Send first invite to the hirer
        </label>
      </div>

      <button onClick={save} style={{ marginTop: '20px', padding: '10px 20px', background: '#667eea', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
        <span className="button-with-icon"><Icon name="check" size={16} /> Save</span>
      </button>
    </div>
  );
}

export default TabSetup;
