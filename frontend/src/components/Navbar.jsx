import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext';
import { Avatar } from './Avatar';
import { getUnreadNotificationCount } from '../api/client';
import { Search, Bell, Sun, Moon, Calendar, LogOut, User, ChevronDown } from 'lucide-react';

const NOTIFICATION_POLL_MS = 30000;

export const Navbar = () => {
  const { user, searchQuery, setSearchQuery, setActiveTab, theme, toggleTheme, logoutUser } = useApp();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [unreadNotifications, setUnreadNotifications] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const { count } = await getUnreadNotificationCount();
        if (!cancelled) setUnreadNotifications(count);
      } catch {
        // Notification count is a nice-to-have indicator, not core workflow -- a
        // transient failure here must never surface as a user-facing error.
      }
    };
    poll();
    const interval = setInterval(poll, NOTIFICATION_POLL_MS);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  const formattedDate = new Date().toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });

  return (
    <nav className="top-navbar">
      <div className="search-input-group">
        <Search size={18} />
        <input 
          type="text" 
          placeholder="Search QA Errors..." 
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            if (e.target.value.trim() !== '') {
              setActiveTab('qa-errors');
            }
          }}
        />
      </div>

      <div className="nav-actions">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          <Calendar size={16} />
          <span>{formattedDate}</span>
        </div>

        <button className="icon-btn" onClick={toggleTheme} title="Toggle Dark/Light Mode">
          {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
        </button>

        <button className="icon-btn" title={unreadNotifications > 0 ? `${unreadNotifications} unread notifications` : 'Notifications'}>
          <Bell size={18} />
          {unreadNotifications > 0 && <span className="badge-dot"></span>}
        </button>

        {/* User Profile Dropdown */}
        <div style={{ position: 'relative' }}>
          <div 
            className="user-profile-badge" 
            onClick={() => setDropdownOpen(!dropdownOpen)}
            style={{ position: 'relative' }}
          >
            <Avatar src={user.avatar} name={user.name} size={36} />
            <div>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)' }}>{user.name}</h4>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{user.role}</p>
            </div>
            <ChevronDown size={14} color="var(--text-muted)" />
          </div>

          {dropdownOpen && (
            <div style={{
              position: 'absolute',
              right: 0,
              top: '115%',
              width: '200px',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-md)',
              boxShadow: 'var(--shadow-lg)',
              padding: '0.5rem',
              zIndex: 50
            }}>
              <button 
                onClick={() => {
                  setActiveTab('profile');
                  setDropdownOpen(false);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.6rem',
                  width: '100%',
                  padding: '0.6rem 0.8rem',
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-main)',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  textAlign: 'left'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-primary)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                <User size={16} /> My Profile
              </button>

              <button 
                onClick={() => {
                  setDropdownOpen(false);
                  logoutUser();
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.6rem',
                  width: '100%',
                  padding: '0.6rem 0.8rem',
                  background: 'transparent',
                  border: 'none',
                  color: '#ef4444',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  textAlign: 'left',
                  marginTop: '0.2rem',
                  borderTop: '1px solid var(--border-light)'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                <LogOut size={16} /> Log Out
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
};
