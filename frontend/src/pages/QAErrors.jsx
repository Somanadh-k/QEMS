import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { PrimaryButton } from '../components/PrimaryButton';
import {
  Plus,
  RotateCcw,
  Download,
  Eye,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

const STATUS_OPTIONS = ['Open', 'In Review', 'Rebuttal Raised', 'QA Decision Pending', 'Resolved', 'Rejected', 'Closed'];
const SEVERITY_OPTIONS = ['Critical', 'High', 'Medium', 'Low'];

const statusBadgeClass = (status) => `badge-${status.toLowerCase().replace(/\s+/g, '-')}`;

export const QAErrors = () => {
  const { errors, errorsLoading, departments, searchQuery, setSearchQuery, setActiveTab, setSelectedErrorId, addToast } = useApp();

  const [departmentFilter, setDepartmentFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  const filteredErrors = errors.filter((err) => {
    const matchesSearch =
      err.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      err.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (err.department || '').toLowerCase().includes(searchQuery.toLowerCase());

    const matchesDept = departmentFilter === '' || err.department === departmentFilter;
    const matchesSev = severityFilter === '' || err.severity === severityFilter;
    const matchesStatus = statusFilter === '' || err.status === statusFilter;

    return matchesSearch && matchesDept && matchesSev && matchesStatus;
  });

  const totalPages = Math.ceil(filteredErrors.length / itemsPerPage) || 1;
  const paginatedErrors = filteredErrors.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const resetFilters = () => {
    setSearchQuery('');
    setDepartmentFilter('');
    setSeverityFilter('');
    setStatusFilter('');
    setCurrentPage(1);
  };

  const handleExportCSV = () => {
    const headers = ['ID', 'Title', 'Department', 'Category', 'Severity', 'Status', 'Date'];
    const rows = filteredErrors.map((e) => [
      e.id,
      `"${e.title}"`,
      e.department,
      e.category,
      e.severity,
      e.status,
      e.date,
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `QEMS_Errors_Export_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    addToast('CSV export downloaded!', 'success');
  };

  const handleView = (err) => {
    setSelectedErrorId(err.id);
    setActiveTab('error-details');
  };

  return (
    <div className="content-wrapper">
      <div className="page-header">
        <div>
          <h1>QA Errors Directory</h1>
          <p>Search, filter, and manage quality error records</p>
        </div>

        <PrimaryButton onClick={() => setActiveTab('create-error')}>
          <Plus size={18} />
          Create New Error
        </PrimaryButton>
      </div>

      {/* Filter Section */}
      <div className="glass-card" style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <div className="form-group" style={{ flex: 1, minWidth: '180px' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Department</label>
          <select className="form-control" value={departmentFilter} onChange={(e) => setDepartmentFilter(e.target.value)}>
            <option value="">All Departments</option>
            {departments.map((d) => (
              <option key={d.department_id} value={d.name}>{d.name}</option>
            ))}
          </select>
        </div>

        <div className="form-group" style={{ flex: 1, minWidth: '160px' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Severity</label>
          <select className="form-control" value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
            <option value="">All Severity</option>
            {SEVERITY_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div className="form-group" style={{ flex: 1, minWidth: '180px' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Status</label>
          <select className="form-control" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All Status</option>
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.25rem' }}>
          <button className="btn-secondary" onClick={resetFilters} title="Reset Filters">
            <RotateCcw size={16} />
            Reset
          </button>

          <button className="btn-secondary" onClick={handleExportCSV} title="Export to CSV">
            <Download size={16} />
            Export CSV
          </button>
        </div>
      </div>

      {/* Table Section */}
      <div className="glass-card">
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Error ID</th>
                <th>Title</th>
                <th>Department</th>
                <th>Category</th>
                <th>Risk</th>
                <th>SLA</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {errorsLoading ? (
                <tr>
                  <td colSpan={10} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                    Loading QA errors…
                  </td>
                </tr>
              ) : paginatedErrors.length > 0 ? (
                paginatedErrors.map((err) => (
                  <tr key={err.id}>
                    <td style={{ fontWeight: 600, color: 'var(--primary)' }}>{err.id}</td>
                    <td style={{ maxWidth: '220px' }}>{err.title}</td>
                    <td>{err.department}</td>
                    <td className="risk-cell" title="Severity, SLA pressure, recurrence, rebuttal, impact and age — hover the detail page for the full breakdown">
                      {err.riskScore != null ? Math.round(err.riskScore) : '—'}
                    </td>
                    <td>
                      {err.slaState
                        ? <span className={`sla-chip sla-${err.slaState}`}>{err.slaState.replace('_', ' ')}</span>
                        : <span style={{ opacity: 0.4 }}>—</span>}
                    </td>
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
                        onClick={() => handleView(err)}
                        title="View Details"
                        style={{ width: '32px', height: '32px' }}
                      >
                        <Eye size={15} />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={10} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                    No QA error records matched your filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--border-light)' }}>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Showing {paginatedErrors.length} of {filteredErrors.length} entries
          </p>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              className="btn-secondary"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem', opacity: currentPage === 1 ? 0.5 : 1 }}
            >
              <ChevronLeft size={16} /> Prev
            </button>

            <span style={{ fontSize: '0.85rem', fontWeight: 600, padding: '0 0.5rem' }}>
              Page {currentPage} of {totalPages}
            </span>

            <button
              className="btn-secondary"
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem', opacity: currentPage === totalPages ? 0.5 : 1 }}
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
