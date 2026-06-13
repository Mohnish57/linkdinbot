import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'react-toastify';
import Icon from './Icon';

function TabSetup({ config, saveConfig, apiUrl }) {
  const prefs = config.jobPreferences || {};
  const settings = config.settings || {};
  const candidate = config.candidate || {};

  const [name, setName] = useState(candidate.name || '');
  const [firstName, setFirstName] = useState(candidate.first_name || '');
  const [email, setEmail] = useState(candidate.email || '');
  const [bio, setBio] = useState(candidate.bio_fullstack || '');
  const [positions, setPositions] = useState((prefs.positions || []).join('\n'));
  const [recruiterKeywords, setRecruiterKeywords] = useState((prefs.recruiterKeywords || []).join('\n'));
  const [driveLink, setDriveLink] = useState(settings.resumeDriveLink || '');
  const [resume, setResume] = useState(null);
  const [uploading, setUploading] = useState(false);

  const fetchResume = useCallback(async () => {
    try {
      const res = await axios.get(`${apiUrl}/api/resumes`);
      setResume(res.data.resumes?.fullstack || null);
    } catch (err) {
      console.error('Failed to load resume:', err);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchResume();
  }, [fetchResume]);

  const uploadResume = async (file) => {
    if (!file) return;

    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      toast.warn('Please upload a PDF resume.');
      return;
    }

    const formData = new FormData();
    formData.append('role', 'fullstack');
    formData.append('resume', file);

    try {
      setUploading(true);
      const res = await axios.post(`${apiUrl}/api/resumes/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResume(res.data.resumes?.fullstack || res.data.resume || null);
      toast.success('Resume uploaded.');
    } catch (err) {
      toast.error(`Failed to upload resume: ${err.response?.data?.error || err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const save = async () => {
    await saveConfig({
      settings: {
        resumeDriveLink: driveLink.trim(),
        resumeDriveLinkFrontend: driveLink.trim(),
        sendInviteNote: true,
      },
      candidate: {
        name: name.trim(),
        first_name: firstName.trim(),
        email: email.trim(),
        bio_fullstack: bio.trim(),
      },
      jobPreferences: {
        positions: positions.split('\n').map(p => p.trim()).filter(Boolean),
        recruiterKeywords: recruiterKeywords.split('\n').map(k => k.trim()).filter(Boolean),
      },
    });
    toast.success('Setup saved!');
  };

  return (
    <div>
      <h2 className="heading-with-icon"><Icon name="settings" /> Setup</h2>

      <div style={{ padding: '14px', border: '1px solid #ddd', borderRadius: '6px', background: '#fff', marginTop: '20px' }}>
        <label style={{ display: 'block', fontWeight: 600, marginBottom: '8px' }}>Your details</label>
        <p style={{ marginTop: 0, color: '#777', fontSize: '0.85em' }}>
          Used to fill <code>{'{candidate_name} {candidate_first_name} {candidate_email} {candidate_bio_long}'}</code> in connection notes &amp; emails.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div>
            <label style={{ fontSize: '0.85em' }}>Full name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)}
              placeholder="Mohnish Sawlani"
              style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }} />
          </div>
          <div>
            <label style={{ fontSize: '0.85em' }}>First name</label>
            <input type="text" value={firstName} onChange={(e) => setFirstName(e.target.value)}
              placeholder="Mohnish"
              style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }} />
          </div>
          <div>
            <label style={{ fontSize: '0.85em' }}>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }} />
          </div>
          <div>
            <label style={{ fontSize: '0.85em' }}>Short bio</label>
            <input type="text" value={bio} onChange={(e) => setBio(e.target.value)}
              placeholder="Software Engineer (Node.js, Python, React)"
              style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }} />
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '20px' }}>
        <div style={{ padding: '14px', border: '1px solid #ddd', borderRadius: '6px', background: '#fff' }}>
          <label style={{ display: 'block', fontWeight: 600, marginBottom: '8px' }}>Resume PDF</label>
          <input
            type="file"
            accept="application/pdf,.pdf"
            onChange={(e) => uploadResume(e.target.files?.[0])}
            disabled={uploading}
          />
          <div style={{ marginTop: '8px', color: resume ? '#388e3c' : '#777', fontSize: '0.9em' }}>
            {uploading ? 'Uploading...' : resume?.name || 'No resume uploaded'}
          </div>
        </div>

        <div style={{ padding: '14px', border: '1px solid #ddd', borderRadius: '6px', background: '#fff' }}>
          <label style={{ display: 'block', fontWeight: 600, marginBottom: '8px' }}>Drive resume link</label>
          <input
            type="url"
            value={driveLink}
            onChange={(e) => setDriveLink(e.target.value)}
            placeholder="https://drive.google.com/..."
            style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
          />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '20px' }}>
        <div>
          <label><strong>Positions to search</strong></label>
          <textarea
            value={positions}
            onChange={(e) => setPositions(e.target.value)}
            style={{ width: '100%', height: '180px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder={'Software Engineer\nFrontend Developer'}
          />
        </div>
        <div>
          <label><strong>Recruiter keywords</strong></label>
          <textarea
            value={recruiterKeywords}
            onChange={(e) => setRecruiterKeywords(e.target.value)}
            style={{ width: '100%', height: '180px', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
            placeholder={'recruiter\ntalent acquisition\nhiring'}
          />
        </div>
      </div>

      <div style={{ marginTop: '20px' }}>
        <label>
          <input type="checkbox" checked readOnly />
          Attach personalised note to each invite
        </label>
      </div>

      <button onClick={save} style={{ marginTop: '20px', padding: '10px 20px', background: '#667eea', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
        <span className="button-with-icon"><Icon name="check" size={16} /> Save setup</span>
      </button>
    </div>
  );
}

export default TabSetup;
