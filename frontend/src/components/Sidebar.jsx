import React from 'react';
import { useApp } from '../context/AppContext';
import { 
  ShieldCheck, 
  LayoutDashboard, 
  AlertTriangle, 
  PlusCircle, 
  BarChart3, 
  User, 
  LogOut,
  AlertOctagon
} from 'lucide-react';

export const Sidebar = () => {
  const { activeTab, setActiveTab, logoutUser } = useApp();

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'qa-errors', label: 'QA Errors', icon: AlertTriangle },
    { id: 'create-error', label: 'Create Error', icon: PlusCircle },
    { id: 'escalations', label: 'Escalations', icon: AlertOctagon },
    { id: 'reports', label: 'Reports', icon: BarChart3 },
    { id: 'profile', label: 'Profile', icon: User },
  ];

  return (
    <aside className="sidebar">
      <div>
        <div className="sidebar-logo">
          <ShieldCheck size={32} color="#7B7481" />
          <h2>QEMS</h2>
        </div>

        <ul className="nav-list">
          {navItems.map(item => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <li key={item.id}>
                <a 
                  className={`nav-item ${isActive ? 'active' : ''}`}
                  onClick={(e) => {
                    e.preventDefault();
                    setActiveTab(item.id);
                  }}
                  href={`#${item.id}`}
                >
                  <Icon size={20} />
                  <span>{item.label}</span>
                </a>
              </li>
            );
          })}
        </ul>
      </div>

      <div>
        <button className="logout-btn" onClick={logoutUser}>
          <LogOut size={18} />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
};
