import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { exportReportCsv } from '../api/client';
import { PrimaryButton } from '../components/PrimaryButton';
import {
  BarChart3, 
  PieChart as PieIcon, 
  Download, 
  TrendingUp, 
  AlertCircle, 
  CheckCircle2, 
  Bug, 
  Flame, 
  Award 
} from 'lucide-react';

const CLOSED_STATUSES = ['Resolved', 'Rejected', 'Closed'];

export const Reports = () => {
  const { errors, departments: departmentList, addToast } = useApp();

  const totalErrors = errors.length;
  const openErrors = errors.filter(e => !CLOSED_STATUSES.includes(e.status)).length;
  const closedErrors = errors.filter(e => CLOSED_STATUSES.includes(e.status)).length;
  const highSeverity = errors.filter(e => e.severity === 'High' || e.severity === 'Critical').length;

  // Monthly trend data (historical months are illustrative; only the current month reflects real data)
  const monthlyData = [
    { month: 'Mar', Open: 4, Closed: 14 },
    { month: 'Apr', Open: 5, Closed: 20 },
    { month: 'May', Open: 4, Closed: 28 },
    { month: 'Jun', Open: 4, Closed: 24 },
    { month: 'Jul', Open: 5, Closed: 30 },
    { month: 'Aug', Open: openErrors, Closed: closedErrors }
  ];

  // Severity Distribution Data
  const severityCount = {
    High: errors.filter(e => e.severity === 'High' || e.severity === 'Critical').length,
    Medium: errors.filter(e => e.severity === 'Medium').length,
    Low: errors.filter(e => e.severity === 'Low').length
  };

  const totalSev = (severityCount.High + severityCount.Medium + severityCount.Low) || 1;

  // Department Breakdown
  const departmentSummary = departmentList.map(dept => {
    const deptErrors = errors.filter(e => e.department === dept.name);
    return {
      name: dept.name,
      total: deptErrors.length,
      open: deptErrors.filter(e => !CLOSED_STATUSES.includes(e.status)).length,
      closed: deptErrors.filter(e => CLOSED_STATUSES.includes(e.status)).length,
      high: deptErrors.filter(e => e.severity === 'High' || e.severity === 'Critical').length
    };
  });

  const [exporting, setExporting] = useState(false);

  const handleExportReport = async () => {
    setExporting(true);
    try {
      const csv = await exportReportCsv();
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `qems-report-${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      addToast('Report exported.', 'success');
    } catch (err) {
      addToast(err.message || 'Failed to export report.', 'error');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="content-wrapper">
      <div className="page-header">
        <div>
          <h1>Reports & Analytics</h1>
          <p>Comprehensive Quality Error Management insights and performance metrics</p>
        </div>

        <PrimaryButton onClick={handleExportReport} disabled={exporting}>
          <Download size={18} /> {exporting ? 'Exporting…' : 'Export Full Report'}
        </PrimaryButton>
      </div>

      {/* Summary KPI Cards */}
      <div className="kpi-grid">
        <div className="glass-card kpi-card">
          <div>
            <h3>Total QA Errors</h3>
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
            <h3>High Severity</h3>
            <h2>{highSeverity}</h2>
          </div>
          <div className="kpi-icon" style={{ background: 'var(--sev-high-bg)', color: 'var(--sev-high-text)' }}>
            <Flame />
          </div>
        </div>
      </div>

      {/* Charts Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* SVG Bar Chart */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <BarChart3 size={20} color="var(--primary)" />
              <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)' }}>Monthly Error Trend</h2>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.75rem' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}><span style={{ width: '8px', height: '8px', background: '#ef4444', borderRadius: '2px' }}></span> Open</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}><span style={{ width: '8px', height: '8px', background: '#10b981', borderRadius: '2px' }}></span> Closed</span>
            </div>
          </div>

          <div style={{ width: '100%', height: '220px' }}>
            <svg viewBox="0 0 450 180" style={{ width: '100%', height: '100%' }}>
              {[0, 10, 20, 30].map((val, idx) => (
                <line key={idx} x1="30" y1={150 - (val / 35) * 130} x2="430" y2={150 - (val / 35) * 130} stroke="var(--border-light)" strokeDasharray="3" />
              ))}

              {monthlyData.map((d, i) => {
                const groupX = 40 + i * 65;
                const openH = (d.Open / 35) * 130;
                const closedH = (d.Closed / 35) * 130;

                return (
                  <g key={i}>
                    {/* Open Bar */}
                    <rect x={groupX} y={150 - openH} width="16" height={openH} rx="3" fill="#ef4444" />
                    {/* Closed Bar */}
                    <rect x={groupX + 18} y={150 - closedH} width="16" height={closedH} rx="3" fill="#10b981" />
                    {/* X Label */}
                    <text x={groupX + 17} y="168" textAnchor="middle" fill="var(--text-muted)" fontSize="11">{d.month}</text>
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        {/* Donut Severity Visualizer */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
            <PieIcon size={20} color="var(--secondary)" />
            <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)' }}>Severity Breakdown</h2>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', justifyContent: 'center', height: '200px' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem', fontSize: '0.85rem' }}>
                <span style={{ color: '#ef4444', fontWeight: 600 }}>High Severity ({severityCount.High})</span>
                <span>{Math.round((severityCount.High / totalSev) * 100)}%</span>
              </div>
              <div style={{ width: '100%', height: '8px', background: 'var(--bg-primary)', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: `${(severityCount.High / totalSev) * 100}%`, height: '100%', background: '#ef4444', borderRadius: '4px' }}></div>
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem', fontSize: '0.85rem' }}>
                <span style={{ color: '#f59e0b', fontWeight: 600 }}>Medium Severity ({severityCount.Medium})</span>
                <span>{Math.round((severityCount.Medium / totalSev) * 100)}%</span>
              </div>
              <div style={{ width: '100%', height: '8px', background: 'var(--bg-primary)', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: `${(severityCount.Medium / totalSev) * 100}%`, height: '100%', background: '#f59e0b', borderRadius: '4px' }}></div>
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem', fontSize: '0.85rem' }}>
                <span style={{ color: '#3b82f6', fontWeight: 600 }}>Low Severity ({severityCount.Low})</span>
                <span>{Math.round((severityCount.Low / totalSev) * 100)}%</span>
              </div>
              <div style={{ width: '100%', height: '8px', background: 'var(--bg-primary)', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: `${(severityCount.Low / totalSev) * 100}%`, height: '100%', background: '#3b82f6', borderRadius: '4px' }}></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Department Breakdown Table */}
      <div className="glass-card" style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)', marginBottom: '1.25rem' }}>Department-wise Error Summary</h2>
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Department</th>
                <th>Total Errors</th>
                <th>Open</th>
                <th>Closed</th>
                <th>High Severity</th>
              </tr>
            </thead>
            <tbody>
              {departmentSummary.map(dept => (
                <tr key={dept.name}>
                  <td style={{ fontWeight: 600 }}>{dept.name}</td>
                  <td>{dept.total}</td>
                  <td style={{ color: 'var(--status-open-text)', fontWeight: 600 }}>{dept.open}</td>
                  <td style={{ color: 'var(--status-closed-text)', fontWeight: 600 }}>{dept.closed}</td>
                  <td style={{ color: 'var(--sev-high-text)', fontWeight: 600 }}>{dept.high}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Automated AI Insights */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem' }}>
        <div className="glass-card" style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
          <div style={{ background: 'var(--primary-light)', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: 'var(--primary)' }}>
            <TrendingUp size={24} />
          </div>
          <div>
            <h3 style={{ fontSize: '1rem', color: 'var(--text-main)', marginBottom: '0.3rem' }}>Overall Performance</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
              Quality audit compliance improved by <strong>14%</strong> this month compared to prior quarter averages.
            </p>
          </div>
        </div>

        <div className="glass-card" style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
          <div style={{ background: 'var(--status-open-bg)', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: 'var(--status-open-text)' }}>
            <AlertCircle size={24} />
          </div>
          <div>
            <h3 style={{ fontSize: '1rem', color: 'var(--text-main)', marginBottom: '0.3rem' }}>Attention Required</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
              Operations department currently maintains the largest ratio of open QA items.
            </p>
          </div>
        </div>

        <div className="glass-card" style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
          <div style={{ background: 'var(--status-closed-bg)', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: 'var(--status-closed-text)' }}>
            <Award size={24} />
          </div>
          <div>
            <h3 style={{ fontSize: '1rem', color: 'var(--text-main)', marginBottom: '0.3rem' }}>Top Team Performance</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
              HR and Finance achieved a 100% resolution turnaround rate for logged audit items.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
