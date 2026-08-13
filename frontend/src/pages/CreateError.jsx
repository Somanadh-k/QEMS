import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { uploadEvidence } from '../api/client';
import { PrimaryButton } from '../components/PrimaryButton';
import { Save, RotateCcw, X, UploadCloud, AlertCircle } from 'lucide-react';

const todayIso = () => new Date().toISOString().split('T')[0];

const emptyForm = {
  title: '',
  department_id: '',
  category_id: '',
  severity: 'Medium',
  date_discovered: todayIso(),
  description: '',
};

export const CreateError = () => {
  const { addError, setActiveTab, setSelectedErrorId, departments, categories, addToast } = useApp();

  const [formData, setFormData] = useState(emptyForm);
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.title || !formData.description || !formData.department_id || !formData.category_id) {
      addToast('Please fill out all required fields.', 'error');
      return;
    }

    setSubmitting(true);
    try {
      const created = await addError({
        title: formData.title,
        description: formData.description,
        category_id: Number(formData.category_id),
        severity: formData.severity,
        department_id: Number(formData.department_id),
        date_discovered: formData.date_discovered,
      });

      if (file) {
        try {
          await uploadEvidence(created.error_id, file);
          addToast('Evidence attached.', 'success');
        } catch (err) {
          addToast(`Error created, but evidence upload failed: ${err.message}`, 'error');
        }
      }

      setSelectedErrorId(created.qa_error_code);
      setActiveTab('qa-errors');
    } catch (err) {
      // addError already surfaced a toast via context's error handling.
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setFormData(emptyForm);
    setFile(null);
  };

  return (
    <div className="content-wrapper">
      <div className="page-header">
        <div>
          <h1>Create New QA Error</h1>
          <p>Fill out the form below to log a new quality error record into QEMS</p>
        </div>

        <button className="btn-secondary" onClick={() => setActiveTab('qa-errors')}>
          <X size={18} />
          Cancel & Return
        </button>
      </div>

      <div className="glass-card" style={{ maxWidth: '900px', margin: '0 auto' }}>
        <form onSubmit={handleSubmit} className="form-grid">
          <div className="form-group">
            <label>Error ID</label>
            <input
              type="text"
              className="form-control"
              value="Auto-generated on submission"
              disabled
              style={{ opacity: 0.75, background: 'var(--bg-secondary)' }}
            />
          </div>

          <div className="form-group">
            <label>Reporting Date *</label>
            <input
              type="date"
              className="form-control"
              value={formData.date_discovered}
              onChange={(e) => setFormData({ ...formData, date_discovered: e.target.value })}
              required
            />
          </div>

          <div className="form-group full-width">
            <label>Error Title *</label>
            <input
              type="text"
              className="form-control"
              placeholder="e.g. Incorrect Customer Address Entry"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label>Department *</label>
            <select
              className="form-control"
              value={formData.department_id}
              onChange={(e) => setFormData({ ...formData, department_id: e.target.value })}
              required
            >
              <option value="">Select department…</option>
              {departments.map((d) => (
                <option key={d.department_id} value={d.department_id}>{d.name}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Category *</label>
            <select
              className="form-control"
              value={formData.category_id}
              onChange={(e) => setFormData({ ...formData, category_id: e.target.value })}
              required
            >
              <option value="">Select category…</option>
              {categories.map((c) => (
                <option key={c.category_id} value={c.category_id}>{c.name}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Severity Level *</label>
            <select
              className="form-control"
              value={formData.severity}
              onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
            >
              <option value="Critical">Critical</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>
          </div>

          <div className="form-group full-width">
            <label>Error Description *</label>
            <textarea
              className="form-control"
              rows={4}
              placeholder="Provide detailed description of the error discovered..."
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              required
            />
          </div>

          <div className="form-group full-width" style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start', background: 'var(--bg-primary)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)' }}>
            <AlertCircle size={16} color="var(--primary)" style={{ marginTop: '0.15rem', flexShrink: 0 }} />
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
              Root cause analysis and corrective action aren't set at creation time — QA can request
              an AI-suggested root cause during review, and the corrective action is recorded as part
              of the final QA decision, both on the error's detail page.
            </p>
          </div>

          {/* Attachment Box */}
          <div className="form-group full-width">
            <label>Supporting Evidence / Attachments</label>
            <div style={{
              border: '2px dashed var(--border-light)',
              borderRadius: 'var(--radius-md)',
              padding: '1.5rem',
              textAlign: 'center',
              background: 'var(--bg-primary)',
              cursor: 'pointer'
            }} onClick={() => document.getElementById('file-upload').click()}>
              <UploadCloud size={32} color="var(--primary)" style={{ marginBottom: '0.5rem' }} />
              <p style={{ fontSize: '0.9rem', color: 'var(--text-main)', fontWeight: 500 }}>
                {file ? `Attached: ${file.name}` : 'Click or drag files here to attach screenshot/PDF evidence'}
              </p>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Supports PNG, JPG, PDF up to 15MB</p>
              <input
                id="file-upload"
                type="file"
                accept="image/png,image/jpeg,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                style={{ display: 'none' }}
                onChange={(e) => {
                  if (e.target.files[0]) setFile(e.target.files[0]);
                }}
              />
            </div>
          </div>

          {/* Buttons */}
          <div className="form-group full-width" style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end', marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border-light)' }}>
            <button type="button" className="btn-secondary" onClick={handleReset} disabled={submitting}>
              <RotateCcw size={16} /> Reset
            </button>
            <PrimaryButton type="submit" size="lg" disabled={submitting}>
              <Save size={16} /> {submitting ? 'Submitting…' : 'Submit QA Error'}
            </PrimaryButton>
          </div>
        </form>
      </div>
    </div>
  );
};
