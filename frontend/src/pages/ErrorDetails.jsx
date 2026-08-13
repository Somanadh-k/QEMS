import React, { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { aiRootCause, aiSimilar, ApiError } from '../api/client';
import { PrimaryButton } from '../components/PrimaryButton';
import {
  ArrowLeft,
  Printer,
  CheckCircle2,
  MessageSquare,
  Send,
  FileText,
  UserCheck,
  Sparkles,
  Search,
  Loader2,
} from 'lucide-react';

const statusBadgeClass = (status) => `badge-${status.toLowerCase().replace(/\s+/g, '-')}`;

export const ErrorDetails = () => {
  const {
    selectedErrorId,
    selectedError,
    errorDetailLoading,
    loadErrorDetail,
    setActiveTab,
    transitionErrorStatus,
    addRebuttal,
    recordDecision,
    user,
    addToast,
  } = useApp();

  const [rebuttalInput, setRebuttalInput] = useState('');
  const [decisionChoice, setDecisionChoice] = useState('Resolved');
  const [decisionNotes, setDecisionNotes] = useState('');
  const [busy, setBusy] = useState(false);

  const [rootCause, setRootCause] = useState(null);
  const [rootCauseLoading, setRootCauseLoading] = useState(false);
  const [similarErrors, setSimilarErrors] = useState(null);
  const [similarLoading, setSimilarLoading] = useState(false);

  useEffect(() => {
    if (selectedErrorId) loadErrorDetail(selectedErrorId);
    setRootCause(null);
    setSimilarErrors(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedErrorId]);

  if (errorDetailLoading || !selectedError) {
    return (
      <div className="content-wrapper">
        <p style={{ color: 'var(--text-muted)' }}>
          {errorDetailLoading ? 'Loading error details…' : 'No error selected.'}{' '}
          <button className="btn-secondary" onClick={() => setActiveTab('qa-errors')}>Return to List</button>
        </p>
      </div>
    );
  }

  const roles = user?.roles || [];
  const isQA = roles.includes('QA Reviewer') || roles.includes('Admin');
  const isOwner = roles.includes('Department Owner') || roles.includes('Admin');
  const isAdmin = roles.includes('Admin');

  const runAction = async (fn) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  const handlePostRebuttal = (e) => {
    e.preventDefault();
    if (!rebuttalInput.trim()) return;
    runAction(async () => {
      await addRebuttal(selectedError.pk, rebuttalInput.trim());
      setRebuttalInput('');
    });
  };

  const handleRecordDecision = (e) => {
    e.preventDefault();
    if (!decisionNotes.trim()) {
      addToast('Decision notes are required.', 'error');
      return;
    }
    runAction(async () => {
      await recordDecision(selectedError.pk, decisionChoice, decisionNotes.trim());
      setDecisionNotes('');
    });
  };

  const handlePrint = () => window.print();

  const fetchRootCause = async () => {
    setRootCauseLoading(true);
    try {
      const res = await aiRootCause(selectedError.pk);
      setRootCause(res);
    } catch (err) {
      const message = err instanceof ApiError && err.code === 'ai_service_unavailable'
        ? 'AI service is unavailable right now (check the OpenAI API key on the backend).'
        : err.message;
      addToast(message, 'error');
    } finally {
      setRootCauseLoading(false);
    }
  };

  const fetchSimilar = async () => {
    setSimilarLoading(true);
    try {
      const res = await aiSimilar(selectedError.pk);
      setSimilarErrors(res);
    } catch (err) {
      addToast(err.message, 'error');
    } finally {
      setSimilarLoading(false);
    }
  };

  return (
    <div className="content-wrapper">
      {/* Top Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button className="icon-btn" onClick={() => setActiveTab('qa-errors')} title="Back to QA Errors">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              Error Record: {selectedError.id}
              <span className={`badge ${statusBadgeClass(selectedError.status)}`}>{selectedError.status}</span>
            </h1>
            <p>{selectedError.title}</p>
          </div>
        </div>

        <button className="btn-secondary" onClick={handlePrint}>
          <Printer size={16} /> Print Report
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Main Details Card */}
        <div className="glass-card" style={{ gridColumn: 'span 2' }}>
          <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '0.75rem' }}>
            Primary Record Information
          </h2>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
            <div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Department</p>
              <h4 style={{ fontSize: '1rem', color: 'var(--text-main)', marginTop: '0.2rem' }}>{selectedError.department}</h4>
            </div>

            <div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Category</p>
              <h4 style={{ fontSize: '1rem', color: 'var(--text-main)', marginTop: '0.2rem' }}>{selectedError.category}</h4>
            </div>

            <div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Severity</p>
              <div style={{ marginTop: '0.2rem' }}>
                <span className={`badge badge-${selectedError.severity.toLowerCase()}`}>{selectedError.severity}</span>
              </div>
            </div>

            <div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Date Discovered</p>
              <h4 style={{ fontSize: '1rem', color: 'var(--text-main)', marginTop: '0.2rem' }}>{selectedError.date}</h4>
            </div>

            <div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Raised By</p>
              <h4 style={{ fontSize: '1rem', color: 'var(--text-main)', marginTop: '0.2rem' }}>{selectedError.raisedByName}</h4>
            </div>

            <div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Assigned To</p>
              <h4 style={{ fontSize: '1rem', color: 'var(--text-main)', marginTop: '0.2rem' }}>{selectedError.assignedToName}</h4>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div>
              <h3 style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Error Description</h3>
              <div style={{ background: 'var(--bg-primary)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)', lineHeight: 1.6 }}>
                {selectedError.description}
              </div>
            </div>

            {/* AI Root Cause */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>AI-Suggested Root Cause</h3>
                {isQA && (
                  <button className="btn-secondary" style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }} onClick={fetchRootCause} disabled={rootCauseLoading}>
                    {rootCauseLoading ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />}
                    {rootCauseLoading ? 'Thinking…' : 'Get AI Suggestion'}
                  </button>
                )}
              </div>
              <div style={{ background: 'var(--bg-primary)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)', lineHeight: 1.6 }}>
                {rootCause ? (
                  <>
                    <span className="badge badge-review" style={{ marginBottom: '0.5rem' }}>{rootCause.label} · {rootCause.confidence} confidence</span>
                    <p style={{ marginTop: '0.5rem' }}>{rootCause.suggested_root_cause}</p>
                  </>
                ) : (
                  isQA ? 'No suggestion requested yet.' : 'Available to QA Reviewers and Admins.'
                )}
              </div>
            </div>

            {/* AI Similar Errors */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Similar Past Errors (AI)</h3>
                {isQA && (
                  <button className="btn-secondary" style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }} onClick={fetchSimilar} disabled={similarLoading}>
                    {similarLoading ? <Loader2 size={14} className="spin" /> : <Search size={14} />}
                    {similarLoading ? 'Searching…' : 'Find Similar'}
                  </button>
                )}
              </div>
              {similarErrors && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {similarErrors.length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>No similar closed errors found yet.</p>
                  ) : (
                    similarErrors.map((s) => (
                      <div key={s.error_id} style={{ display: 'flex', justifyContent: 'space-between', background: 'var(--bg-primary)', padding: '0.6rem 0.8rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)', fontSize: '0.85rem' }}>
                        <span><strong style={{ color: 'var(--primary)' }}>{s.qa_error_code}</strong> — {s.title}</span>
                        <span className={`badge ${statusBadgeClass(s.status)}`}>{s.status}</span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Timeline & Workflow Side Card */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="glass-card">
            <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)', marginBottom: '1.25rem' }}>Workflow</h2>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
                <div style={{ background: 'var(--primary-light)', padding: '0.5rem', borderRadius: '50%', color: 'var(--primary)' }}>
                  <CheckCircle2 size={18} />
                </div>
                <div>
                  <h4 style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>Error Recorded</h4>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{new Date(selectedError.createdAt).toLocaleString()}</p>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
                <div style={{ background: 'var(--status-review-bg)', padding: '0.5rem', borderRadius: '50%', color: 'var(--status-review-text)' }}>
                  <UserCheck size={18} />
                </div>
                <div>
                  <h4 style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>Current Stage: {selectedError.status}</h4>
                  {selectedError.dueAt && (
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>SLA due {new Date(selectedError.dueAt).toLocaleString()}</p>
                  )}
                </div>
              </div>

              {selectedError.closedAt && (
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
                  <div style={{ background: 'var(--status-closed-bg)', padding: '0.5rem', borderRadius: '50%', color: 'var(--status-closed-text)' }}>
                    <CheckCircle2 size={18} />
                  </div>
                  <div>
                    <h4 style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>Closed</h4>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{new Date(selectedError.closedAt).toLocaleString()}</p>
                  </div>
                </div>
              )}
            </div>

            {/* Contextual Actions */}
            <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {selectedError.status === 'Open' && isQA && (
                <PrimaryButton fullWidth disabled={busy} onClick={() => runAction(() => transitionErrorStatus(selectedError.pk, 'In Review'))}>
                  Start Review
                </PrimaryButton>
              )}

              {selectedError.status === 'In Review' && isQA && (
                <PrimaryButton fullWidth disabled={busy} onClick={() => runAction(() => transitionErrorStatus(selectedError.pk, 'QA Decision Pending'))}>
                  Send to QA Decision
                </PrimaryButton>
              )}

              {selectedError.status === 'Rebuttal Raised' && isQA && (
                <PrimaryButton fullWidth disabled={busy} onClick={() => runAction(() => transitionErrorStatus(selectedError.pk, 'QA Decision Pending'))}>
                  Move to QA Decision
                </PrimaryButton>
              )}

              {selectedError.status === 'QA Decision Pending' && isQA && (
                <form onSubmit={handleRecordDecision} style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                  <select className="form-control" value={decisionChoice} onChange={(e) => setDecisionChoice(e.target.value)}>
                    <option value="Resolved">Resolved</option>
                    <option value="Rejected">Rejected</option>
                    <option value="Escalated">Escalated</option>
                  </select>
                  <textarea
                    className="form-control"
                    rows={2}
                    placeholder="Decision notes (required)…"
                    value={decisionNotes}
                    onChange={(e) => setDecisionNotes(e.target.value)}
                  />
                  <PrimaryButton type="submit" fullWidth disabled={busy}>Record QA Decision</PrimaryButton>
                </form>
              )}

              {['Open', 'In Review'].includes(selectedError.status) && !isQA && (
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Only a QA Reviewer or Admin can advance this error's status.</p>
              )}

              {isAdmin && selectedError.status !== 'Closed' && (
                <button
                  className="btn-secondary"
                  style={{ color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                  disabled={busy}
                  onClick={() => runAction(() => transitionErrorStatus(selectedError.pk, 'Closed', true))}
                >
                  Admin: Force Close
                </button>
              )}
            </div>
          </div>

          <div className="glass-card">
            <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)', marginBottom: '1rem' }}>Attached Evidence</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {selectedError.evidence.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No evidence attached yet.</p>
              ) : (
                selectedError.evidence.map((ev) => (
                  <a
                    key={ev.evidence_id}
                    href={ev.file_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.6rem 0.8rem', background: 'var(--bg-primary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)', textDecoration: 'none', color: 'inherit' }}
                  >
                    <FileText size={18} color="var(--primary)" />
                    <span style={{ fontSize: '0.85rem', flex: 1 }}>{ev.file_name}</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{ev.file_size_kb} KB</span>
                  </a>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* QA Decisions */}
      {selectedError.decisions.length > 0 && (
        <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)', marginBottom: '1.25rem' }}>QA Decisions</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {selectedError.decisions.map((d) => (
              <div key={d.id} style={{ background: 'var(--bg-primary)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)', padding: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                  <span className={`badge ${statusBadgeClass(d.decision === 'Resolved' ? 'Resolved' : d.decision === 'Rejected' ? 'Rejected' : 'QA Decision Pending')}`}>{d.decision}</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{d.author} · {d.date}</span>
                </div>
                <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>{d.notes}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Rebuttal & Discussion Thread */}
      <div className="glass-card">
        <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <MessageSquare size={20} color="var(--primary)" />
          Rebuttal & Discussion Thread ({selectedError.rebuttals.length})
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.5rem' }}>
          {selectedError.rebuttals.length > 0 ? (
            selectedError.rebuttals.map((reb) => (
              <div key={reb.id} style={{ background: 'var(--bg-primary)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)', padding: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                  <strong style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>{reb.author}</strong>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{reb.date}</span>
                </div>
                <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>{reb.text}</p>
              </div>
            ))
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>No rebuttal comments added yet.</p>
          )}
        </div>

        {selectedError.status === 'In Review' && isOwner ? (
          <form onSubmit={handlePostRebuttal} style={{ display: 'flex', gap: '0.75rem' }}>
            <input
              type="text"
              className="form-control"
              placeholder="Type your rebuttal justification…"
              value={rebuttalInput}
              onChange={(e) => setRebuttalInput(e.target.value)}
              style={{ flex: 1 }}
            />
            <PrimaryButton type="submit" disabled={busy}>
              <Send size={16} /> Post Rebuttal
            </PrimaryButton>
          </form>
        ) : (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {selectedError.status === 'In Review'
              ? 'Only the Department Owner (or Admin) can raise a rebuttal.'
              : 'Rebuttals can only be raised while the error is In Review.'}
          </p>
        )}
      </div>
    </div>
  );
};
