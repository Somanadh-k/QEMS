import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { PrimaryButton } from '../components/PrimaryButton';
import {
  Bug, 
  AlertCircle, 
  CheckCircle2, 
  HelpCircle, 
  Flame, 
  Plus, 
  List, 
  TrendingUp, 
  User, 
  Eye, 
  ArrowUpRight 
} from 'lucide-react';

const statusBadgeClass = (status) => `badge-${status.toLowerCase().replace(/\s+/g, '-')}`;

export const Dashboard = () => {
  const { errors, user, setActiveTab, setSelectedErrorId } = useApp();

  const CLOSED_STATUSES = ['Resolved', 'Rejected', 'Closed'];
  const REVIEW_STATUSES = ['In Review', 'Rebuttal Raised', 'QA Decision Pending'];

  const totalErrors = errors.length;
  const openErrors = errors.filter(e => e.status === 'Open').length;
  const closedErrors = errors.filter(e => CLOSED_STATUSES.includes(e.status)).length;
  const reviewErrors = errors.filter(e => REVIEW_STATUSES.includes(e.status)).length;
  const highSeverity = errors.filter(e => e.severity === 'High' || e.severity === 'Critical').length;

  const [hoveredPoint, setHoveredPoint] = useState(null);

  const chartData = [
    { month: 'Mar', total: 18, resolved: 14 },
    { month: 'Apr', total: 25, resolved: 20 },
    { month: 'May', total: 32, resolved: 28 },
    { month: 'Jun', total: 28, resolved: 24 },
    { month: 'Jul', total: 35, resolved: 30 },
    { month: 'Aug', total: totalErrors, resolved: closedErrors }
  ];

  const handleViewError = (id) => {
    setSelectedErrorId(id);
    setActiveTab('error-details');
  };

  // SVG Area Chart calculations
  const maxVal = Math.max(...chartData.map(d => d.total), 40);
  const chartHeight = 180;
  const chartWidth = 500;

  const getX = (index) => (index / (chartData.length - 1)) * (chartWidth - 40) + 20;
  const getY = (val) => chartHeight - (val / maxVal) * (chartHeight - 30) - 10;

  const totalPoints = chartData.map((d, i) => `${getX(i)},${getY(d.total)}`).join(' ');
  const resolvedPoints = chartData.map((d, i) => `${getX(i)},${getY(d.resolved)}`).join(' ');

  const totalArea = `M ${getX(0)},${chartHeight} L ${totalPoints} L ${getX(chartData.length - 1)},${chartHeight} Z`;
  const resolvedArea = `M ${getX(0)},${chartHeight} L ${resolvedPoints} L ${getX(chartData.length - 1)},${chartHeight} Z`;

  return (
    <div className="content-wrapper">
      {/* Welcome Banner */}
      <div className="glass-card" style={{ marginBottom: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', background: 'linear-gradient(135deg, rgba(123, 116, 129, 0.12), rgba(156, 148, 163, 0.12))' }}>
        <div>
          <h1 style={{ fontSize: '1.8rem', color: 'var(--text-main)', marginBottom: '0.4rem' }}>
            Welcome Back, {user.name} 👋
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>
            Monitor quality metrics, manage QA errors, and review reports from one centralized platform.
          </p>
        </div>

        <PrimaryButton onClick={() => setActiveTab('create-error')}>
          <Plus size={18} />
          Create New QA Error
        </PrimaryButton>
      </div>

      {/* KPI Cards Grid */}
      <div className="kpi-grid">
        <div className="glass-card kpi-card">
          <div>
            <h3>Total Errors</h3>
            <h2>{totalErrors}</h2>
          </div>
          <div className="kpi-icon" style={{ background: 'rgba(123, 116, 129, 0.12)', color: 'var(--primary)' }}>
            <Bug />
          </div>
        </div>

        <div className="glass-card kpi-card">
          <div>
            <h3>Open Errors</h3>
            <h2>{openErrors}</h2>
          </div>
          <div className="kpi-icon" style={{ background: 'var(--status-open-bg)', color: 'var(--status-open-text)' }}>
            <AlertCircle />
          </div>
        </div>

        <div className="glass-card kpi-card">
          <div>
            <h3>Closed Errors</h3>
            <h2>{closedErrors}</h2>
          </div>
          <div className="kpi-icon" style={{ background: 'var(--status-closed-bg)', color: 'var(--status-closed-text)' }}>
            <CheckCircle2 />
          </div>
        </div>

        <div className="glass-card kpi-card">
          <div>
            <h3>Under Review</h3>
            <h2>{reviewErrors}</h2>
          </div>
          <div className="kpi-icon" style={{ background: 'var(--status-review-bg)', color: 'var(--status-review-text)' }}>
            <HelpCircle />
          </div>
        </div>

        <div className="glass-card kpi-card">
          <div>
            <h3>High Severity</h3>
            <h2>{highSeverity}</h2>
          </div>
          <div className="kpi-icon" style={{ background: 'var(--sev-high-bg)', color: 'var(--sev-high-text)' }}>
            <Flame />
          </div>
        </div>
      </div>

      {/* Chart + Quick Actions Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Error Trend SVG Area Chart */}
        <div className="glass-card" style={{ gridColumn: 'span 2' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
            <div>
              <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)' }}>Error Trend</h2>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Monthly logging vs resolution rates</p>
            </div>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', fontSize: '0.8rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--text-main)' }}>
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#7B7481' }}></span>
                Total Errors
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--text-main)' }}>
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#10b981' }}></span>
                Resolved
              </div>
            </div>
          </div>

          {/* SVG Canvas */}
          <div style={{ position: 'relative', width: '100%', height: '220px' }}>
            <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} style={{ width: '100%', height: '100%', overflow: 'visible' }}>
              <defs>
                <linearGradient id="totalGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7B7481" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="#7B7481" stopOpacity="0.0" />
                </linearGradient>
                <linearGradient id="resolvedGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Grid Lines */}
              {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => (
                <line 
                  key={idx}
                  x1="10" 
                  y1={chartHeight * ratio} 
                  x2={chartWidth - 10} 
                  y2={chartHeight * ratio} 
                  stroke="var(--border-light)" 
                  strokeDasharray="4"
                />
              ))}

              {/* Area Fills */}
              <path d={totalArea} fill="url(#totalGradient)" />
              <path d={resolvedArea} fill="url(#resolvedGradient)" />

              {/* Lines */}
              <polyline fill="none" stroke="#7B7481" strokeWidth="3" points={totalPoints} />
              <polyline fill="none" stroke="#10b981" strokeWidth="3" points={resolvedPoints} />

              {/* Data Dots */}
              {chartData.map((d, i) => (
                <g key={i}>
                  <circle 
                    cx={getX(i)} 
                    cy={getY(d.total)} 
                    r="5" 
                    fill="#7B7481" 
                    stroke="var(--bg-secondary)" 
                    strokeWidth="2"
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHoveredPoint({ ...d, x: getX(i), y: getY(d.total) })}
                    onMouseLeave={() => setHoveredPoint(null)}
                  />
                  <circle 
                    cx={getX(i)} 
                    cy={getY(d.resolved)} 
                    r="5" 
                    fill="#10b981" 
                    stroke="var(--bg-secondary)" 
                    strokeWidth="2" 
                    style={{ cursor: 'pointer' }}
                  />
                  {/* Month Label */}
                  <text 
                    x={getX(i)} 
                    y={chartHeight + 15} 
                    textAnchor="middle" 
                    fill="var(--text-muted)" 
                    fontSize="11"
                  >
                    {d.month}
                  </text>
                </g>
              ))}
            </svg>

            {/* Hover Tooltip */}
            {hoveredPoint && (
              <div style={{
                position: 'absolute',
                left: `${(hoveredPoint.x / chartWidth) * 100}%`,
                top: `${(hoveredPoint.y / chartHeight) * 100 - 10}%`,
                transform: 'translate(-50%, -100%)',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-light)',
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                boxShadow: 'var(--shadow-md)',
                fontSize: '0.8rem',
                zIndex: 10,
                pointerEvents: 'none'
              }}>
                <strong>{hoveredPoint.month}</strong>: {hoveredPoint.total} Errors ({hoveredPoint.resolved} Resolved)
              </div>
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)', marginBottom: '1.25rem' }}>Quick Actions</h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <button className="btn-secondary" style={{ width: '100%', justifyContent: 'flex-start', padding: '0.9rem' }} onClick={() => setActiveTab('create-error')}>
              <Plus size={18} color="var(--primary)" />
              <span>Create QA Error Record</span>
            </button>
            <button className="btn-secondary" style={{ width: '100%', justifyContent: 'flex-start', padding: '0.9rem' }} onClick={() => setActiveTab('qa-errors')}>
              <List size={18} color="var(--secondary)" />
              <span>View All QA Errors</span>
            </button>
            <button className="btn-secondary" style={{ width: '100%', justifyContent: 'flex-start', padding: '0.9rem' }} onClick={() => setActiveTab('reports')}>
              <TrendingUp size={18} color="#9C94A8" />
              <span>View Analytics & Reports</span>
            </button>
            <button className="btn-secondary" style={{ width: '100%', justifyContent: 'flex-start', padding: '0.9rem' }} onClick={() => setActiveTab('profile')}>
              <User size={18} color="#10b981" />
              <span>Manage My Profile</span>
            </button>
          </div>
        </div>
      </div>

      {/* Recent Errors Table Section */}
      <div className="glass-card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <div>
            <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)' }}>Recent QA Errors</h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Latest logged defect entries</p>
          </div>
          <button className="btn-secondary" style={{ fontSize: '0.85rem' }} onClick={() => setActiveTab('qa-errors')}>
            View All Records <ArrowUpRight size={16} />
          </button>
        </div>

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Error ID</th>
                <th>Title</th>
                <th>Department</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Date</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {errors.slice(0, 5).map(err => (
                <tr key={err.id}>
                  <td style={{ fontWeight: 600, color: 'var(--primary)' }}>{err.id}</td>
                  <td>{err.title}</td>
                  <td>{err.department}</td>
                  <td>
                    <span className={`badge badge-${err.severity.toLowerCase()}`}>
                      {err.severity}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${statusBadgeClass(err.status)}`}>
                      {err.status}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{err.date}</td>
                  <td>
                    <button 
                      className="icon-btn" 
                      onClick={() => handleViewError(err.id)}
                      title="View Details"
                      style={{ width: '32px', height: '32px' }}
                    >
                      <Eye size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
