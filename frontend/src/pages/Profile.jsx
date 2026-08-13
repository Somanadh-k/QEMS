import React, { useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import { PrimaryButton } from '../components/PrimaryButton';
import { Avatar } from '../components/Avatar';
import { Save, RotateCcw, Camera, X, ShieldCheck, Award, Bug, CheckCircle2, LogOut } from 'lucide-react';

const MAX_AVATAR_SIZE_MB = 2;

export const Profile = () => {
  const { user, setUser, departments, addToast, logoutUser } = useApp();
  const avatarInputRef = useRef(null);

  const [formData, setFormData] = useState({
    name: user.name,
    email: user.email,
    phone: user.phone || '+1 (555) 234-5678',
    department: user.department || 'Quality Assurance',
    role: user.role || 'Quality Assurance Manager',
    employeeId: user.employeeId || 'EMP-001',
    address: user.address || 'San Francisco, California, USA',
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  });

  const handleSave = (e) => {
    e.preventDefault();
    if (formData.newPassword && formData.newPassword !== formData.confirmPassword) {
      addToast('New passwords do not match.', 'error');
      return;
    }

    setUser(prev => ({
      ...prev,
      name: formData.name,
      email: formData.email,
      phone: formData.phone,
      department: formData.department,
      address: formData.address
    }));

    // The backend doesn't expose a profile-update endpoint yet, so this is local-only for now.
    addToast('Profile preferences saved locally (not yet synced to the server).', 'info');
  };

  const handleAvatarFileSelected = (e) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow picking the same file again later
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      addToast('Please choose an image file.', 'error');
      return;
    }
    if (file.size > MAX_AVATAR_SIZE_MB * 1024 * 1024) {
      addToast(`Image must be under ${MAX_AVATAR_SIZE_MB}MB.`, 'error');
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      setUser(prev => ({ ...prev, avatar: reader.result }));
      addToast('Profile picture updated.', 'success');
    };
    reader.onerror = () => addToast('Could not read that image file.', 'error');
    reader.readAsDataURL(file);
  };

  const handleAvatarRemove = () => {
    setUser(prev => ({ ...prev, avatar: null }));
    addToast('Profile picture removed.', 'info');
  };

  return (
    <div className="content-wrapper">
      <div className="page-header">
        <div>
          <h1>User Profile Settings</h1>
          <p>Manage your account credentials, preferences, and QA audit achievements</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Left Form */}
        <div className="glass-card" style={{ gridColumn: 'span 2' }}>
          {/* Profile Avatar Banner */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', marginBottom: '2rem', paddingBottom: '1.5rem', borderBottom: '1px solid var(--border-light)', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative' }}>
              <Avatar
                src={user.avatar}
                name={user.name}
                size={90}
                style={{ border: '3px solid var(--primary)' }}
              />
              <input
                ref={avatarInputRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={handleAvatarFileSelected}
              />
              <button
                type="button"
                className="icon-btn"
                onClick={() => avatarInputRef.current?.click()}
                style={{ position: 'absolute', bottom: 0, right: user.avatar ? '28px' : 0, width: '32px', height: '32px', borderRadius: '50%', background: 'var(--primary)', color: '#fff' }}
                title="Choose a picture from your computer"
              >
                <Camera size={16} />
              </button>
              {user.avatar && (
                <button
                  type="button"
                  className="icon-btn"
                  onClick={handleAvatarRemove}
                  style={{ position: 'absolute', bottom: 0, right: 0, width: '32px', height: '32px', borderRadius: '50%', background: '#ef4444', color: '#fff' }}
                  title="Remove picture"
                >
                  <X size={16} />
                </button>
              )}
            </div>

            <div>
              <h2 style={{ fontSize: '1.3rem', color: 'var(--text-main)' }}>{user.name}</h2>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>{user.role}</p>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                <span className="badge badge-closed" style={{ fontSize: '0.75rem' }}>Verified QA Lead</span>
                <span className="badge badge-low" style={{ fontSize: '0.75rem' }}>{user.department}</span>
              </div>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSave} className="form-grid">
            <div className="form-group">
              <label>Full Name</label>
              <input 
                type="text" 
                className="form-control" 
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required 
              />
            </div>

            <div className="form-group">
              <label>Email Address</label>
              <input 
                type="email" 
                className="form-control" 
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                required 
              />
            </div>

            <div className="form-group">
              <label>Phone Number</label>
              <input 
                type="text" 
                className="form-control" 
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label>Department</label>
              <select
                className="form-control"
                value={formData.department}
                onChange={(e) => setFormData({ ...formData, department: e.target.value })}
              >
                {departments.map((d) => (
                  <option key={d.department_id} value={d.name}>{d.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Employee ID</label>
              <input type="text" className="form-control" value={formData.employeeId} disabled style={{ opacity: 0.7 }} />
            </div>

            <div className="form-group">
              <label>Role</label>
              <input type="text" className="form-control" value={formData.role} disabled style={{ opacity: 0.7 }} />
            </div>

            <div className="form-group full-width">
              <label>Address</label>
              <textarea 
                className="form-control" 
                rows={2}
                value={formData.address}
                onChange={(e) => setFormData({ ...formData, address: e.target.value })}
              />
            </div>

            {/* Password Section */}
            <div className="form-group full-width" style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-light)' }}>
              <h3 style={{ fontSize: '1rem', color: 'var(--text-main)', marginBottom: '0.75rem' }}>Security & Password</h3>
            </div>

            <div className="form-group">
              <label>New Password</label>
              <input 
                type="password" 
                className="form-control" 
                placeholder="Leave blank to keep current password"
                value={formData.newPassword}
                onChange={(e) => setFormData({ ...formData, newPassword: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label>Confirm New Password</label>
              <input 
                type="password" 
                className="form-control" 
                placeholder="Confirm new password"
                value={formData.confirmPassword}
                onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
              />
            </div>

            <div className="form-group full-width" style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end', marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border-light)' }}>
              <button 
                type="button" 
                className="btn-secondary" 
                onClick={logoutUser}
                style={{ color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.3)' }}
              >
                <LogOut size={16} /> Log Out of Account
              </button>
              <PrimaryButton type="submit" size="lg">
                <Save size={16} /> Save Changes
              </PrimaryButton>
            </div>
          </form>
        </div>

        {/* Right Stats Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="glass-card">
            <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)', marginBottom: '1.25rem' }}>QA Achievements</h2>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div style={{ background: 'var(--primary-light)', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: 'var(--primary)' }}>
                  <Bug size={24} />
                </div>
                <div>
                  <h3 style={{ fontSize: '1.4rem', color: 'var(--text-main)' }}>142</h3>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Errors Reviewed & Closed</p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div style={{ background: 'var(--status-closed-bg)', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: 'var(--status-closed-text)' }}>
                  <Award size={24} />
                </div>
                <div>
                  <h3 style={{ fontSize: '1.4rem', color: 'var(--text-main)' }}>98.5%</h3>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>QA Audit Accuracy Score</p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div style={{ background: 'rgba(123, 116, 129, 0.12)', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: 'var(--secondary)' }}>
                  <ShieldCheck size={24} />
                </div>
                <div>
                  <h3 style={{ fontSize: '1.4rem', color: 'var(--text-main)' }}>3+ Years</h3>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>QA Management Seniority</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
