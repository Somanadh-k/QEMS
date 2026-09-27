import React, { useState, useEffect } from 'react';
import { AlertOctagon, Check, Loader2, Inbox } from 'lucide-react';
import { listEscalations, acknowledgeEscalation } from '../api/client';
import { useApp } from '../context/AppContext';

/**
 * Escalation inbox (proposal SLA-02).
 *
 * Acknowledging requires a next action. A bare "seen" is not an outcome, and an inbox
 * that accepts one becomes a place where breaches go to be silently dismissed.
 */
export const EscalationInbox = () => {
  const { addToast, setActiveTab, setSelectedErrorId } = useApp();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAcked, setShowAcked] = useState(false);
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState(null);

  const load = async (acked = showAcked) => {
    setLoading(true);
    try {
      setItems(await listEscalations(acked));
    } catch (err) {
      addToast(err.message || 'Could not load escalations', 'error');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(showAcked); }, [showAcked]);

  const ack = async (item) => {
    const nextAction = (draft[item.escalation_id] || '').trim();
    if (!nextAction) {
      addToast('Describe the next action before acknowledging', 'error');
      return;
    }
    setBusy(item.escalation_id);
    try {
      await acknowledgeEscalation(item.escalation_id, nextAction);
      addToast(`Acknowledged ${item.qa_error_code}`, 'success');
      setDraft((d) => ({ ...d, [item.escalation_id]: '' }));
      await load();
    } catch (err) {
      addToast(err.message || 'Could not acknowledge', 'error');
    } finally { setBusy(null); }
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>Escalation Inbox</h1>
          <p>SLA breaches routed to you. Acknowledging records a commitment, not just a read.</p>
        </div>
        <button className="ghost-btn" onClick={() => setShowAcked(!showAcked)}>
          {showAcked ? 'Show open' : 'Show acknowledged'}
        </button>
      </div>

      {loading ? (
        <div className="signal-empty"><Loader2 size={16} className="spin" /> Loading…</div>
      ) : items.length === 0 ? (
        <div className="signal-empty">
          <Inbox size={18} />
          <div>
            <strong>Nothing {showAcked ? 'acknowledged' : 'outstanding'}.</strong>
            <p>{showAcked ? '' : 'No SLA breaches are currently escalated to you.'}</p>
          </div>
        </div>
      ) : (
        <div className="escalation-list">
          {items.map((item) => (
            <div key={item.escalation_id} className="escalation-card">
              <div className="escalation-top">
                <AlertOctagon size={16} className="escalation-icon" />
                <button className="link-btn" onClick={() => { setSelectedErrorId(item.error_id); setActiveTab('error-details'); }}>
                  {item.qa_error_code}
                </button>
                <span className="escalation-level">Level {item.level}</span>
                <span className="escalation-trigger">{item.trigger}</span>
                <span className="escalation-when">
                  {new Date(item.triggered_at).toLocaleString()}
                </span>
              </div>

              {item.acknowledged_at ? (
                <div className="escalation-acked">
                  <Check size={13} /> {item.next_action}
                </div>
              ) : (
                <div className="escalation-ack">
                  <input
                    placeholder="What will you do about it, and by when?"
                    value={draft[item.escalation_id] || ''}
                    onChange={(e) => setDraft((d) => ({ ...d, [item.escalation_id]: e.target.value }))}
                  />
                  <button disabled={busy === item.escalation_id} onClick={() => ack(item)}>
                    {busy === item.escalation_id ? <Loader2 size={13} className="spin" /> : 'Acknowledge'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
