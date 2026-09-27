import React, { useState, useEffect } from 'react';
import { Clock, PauseCircle } from 'lucide-react';
import { getSla } from '../api/client';

/**
 * Stage clock strip (proposal SLA-02).
 *
 * Shows each stage, its budget consumption, and — the part that matters in a
 * cross-functional argument — which role owned the clock while it ran. Time spent
 * waiting on operations is not charged to QA, and this strip is the artefact that proves
 * it when a breach is disputed.
 */
export const SlaStrip = ({ errorId }) => {
  const [sla, setSla] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (errorId) {
      getSla(errorId).then((d) => { if (!cancelled) setSla(d); }).catch(() => {});
    }
    return () => { cancelled = true; };
  }, [errorId]);

  if (!sla) return null;

  const pct = Math.min((sla.consumption_ratio || 0) * 100, 100);
  const state = sla.sla_state || 'ON_TRACK';

  return (
    <div className="signal-panel" style={{ paddingBottom: 12 }}>
      <div className="signal-head">
        {state === 'PAUSED' ? <PauseCircle size={16} /> : <Clock size={16} />}
        <h3>SLA — {sla.sla_stage || 'not started'}</h3>
        <span className={`sla-chip sla-${state}`} style={{ marginLeft: 'auto' }}>
          {state.replace('_', ' ')}
        </span>
      </div>

      <div className="signal-bar-row" style={{ gridTemplateColumns: '130px 1fr 46px' }}>
        <span>Budget consumed</span>
        <div className="signal-bar-track">
          <div
            className="signal-bar-fill"
            style={{
              width: `${pct}%`,
              background: state === 'BREACHED' ? '#a32f2f' : state === 'AT_RISK' ? '#9a6a06' : '#2b6b47',
            }}
          />
        </div>
        <span className="signal-bar-value">{Math.round(pct)}%</span>
      </div>

      <div style={{ fontSize: 11.5, opacity: 0.65, marginTop: 8 }}>
        Clock owner: <strong>{sla.clock_owner_role || '—'}</strong>
        {sla.sla_due_at && <> · due {new Date(sla.sla_due_at).toLocaleString()}</>}
        {sla.escalation_level > 0 && <> · escalated to L{sla.escalation_level}</>}
      </div>

      {sla.timeline?.length > 0 && (
        <details className="signal-neighbours">
          <summary>{sla.timeline.length} clock events</summary>
          {sla.timeline.map((t, i) => (
            <div key={i} className="signal-neighbour" style={{ gridTemplateColumns: '110px 1fr 140px' }}>
              <code>{t.stage}</code>
              <span>{t.event_type}{t.owner_role ? ` · ${t.owner_role}` : ''}</span>
              <em>{new Date(t.occurred_at).toLocaleString()}</em>
            </div>
          ))}
        </details>
      )}
    </div>
  );
};
