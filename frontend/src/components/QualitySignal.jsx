import React, { useState, useEffect } from 'react';
import {
  Activity, AlertTriangle, Copy, Loader2, RefreshCw, ShieldQuestion, Check, X,
} from 'lucide-react';
import { getSignal, recomputeSignal, acknowledgeInsight } from '../api/client';
import { useApp } from '../context/AppContext';

/**
 * Quality Signal rail (proposal QS-01).
 *
 * The ordering here is the argument, not a layout preference: the SQL-computed evidence
 * table sits ABOVE the AI narrative, so a reviewer who distrusts the prose can still act
 * on the facts. When the model is unavailable the panel renders the facts alone rather
 * than disappearing — which is why `status: DEGRADED` is a first-class render path.
 *
 * Nothing in this component writes to the decision form. It cannot: no callback it owns
 * touches status, severity, or the decision field.
 */

const BAND_STYLE = {
  HIGH: { bg: 'rgba(163,47,47,0.14)', fg: '#d98b84', label: 'HIGH' },
  MEDIUM: { bg: 'rgba(154,106,6,0.14)', fg: '#d9ab5c', label: 'MEDIUM' },
  LOW: { bg: 'rgba(43,107,71,0.14)', fg: '#7cc79b', label: 'LOW' },
};

const COMPONENT_LABEL = {
  similar_volume: 'Similar findings',
  process_concentration: 'Same process',
  trend: 'Quarter-on-quarter rise',
  severity: 'Severity',
  prior_capa_ineffective: 'Prior fix failed',
};

const Metric = ({ label, value, hint }) => (
  <div className="signal-metric">
    <div className="signal-metric-value">{value}</div>
    <div className="signal-metric-label">{label}</div>
    {hint && <div className="signal-metric-hint">{hint}</div>}
  </div>
);

export const QualitySignal = ({ errorId }) => {
  const { addToast } = useApp();
  const [signal, setSignal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [showAck, setShowAck] = useState(null);

  const load = async (recompute = false) => {
    setLoading(true);
    try {
      setSignal(recompute ? await recomputeSignal(errorId) : await getSignal(errorId));
    } catch (err) {
      addToast(err.message || 'Could not load the quality signal', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (errorId) load(); }, [errorId]);

  const submitAck = async (action) => {
    if (action !== 'ACCEPTED' && !note.trim()) {
      addToast('Add a note explaining why before rejecting a recommendation', 'error');
      return;
    }
    setBusy(true);
    try {
      await acknowledgeInsight(signal.insight_id, action, note);
      addToast('Recorded in the audit trail', 'success');
      setShowAck(null); setNote('');
      await load();
    } catch (err) {
      addToast(err.message || 'Could not record acknowledgement', 'error');
    } finally { setBusy(false); }
  };

  if (loading) {
    return (
      <div className="signal-panel">
        <div className="signal-head"><Activity size={16} /><h3>Quality Signal</h3></div>
        <div className="signal-empty"><Loader2 size={16} className="spin" /> Analysing history…</div>
      </div>
    );
  }
  if (!signal) return null;

  // Two distinct reasons for no signal, and conflating them misleads the reviewer: one
  // says the system does not know enough yet, the other says this particular finding
  // looks novel — which is itself useful information.
  if (signal.status === 'INSUFFICIENT_HISTORY') {
    return (
      <div className="signal-panel">
        <div className="signal-head"><Activity size={16} /><h3>Quality Signal</h3></div>
        <div className="signal-empty">
          <ShieldQuestion size={16} />
          <div>
            <strong>Not enough history yet.</strong>
            <p>
              Only {signal.corpus_size ?? 0} findings carry a comparable embedding
              {signal.required ? `; ${signal.required} are needed` : ''}. A recurrence
              verdict drawn from too few cases would be confident and wrong, so none is shown.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (signal.status === 'NO_COMPARABLE_FINDINGS') {
    return (
      <div className="signal-panel">
        <div className="signal-head"><Activity size={16} /><h3>Quality Signal</h3></div>
        <div className="signal-empty">
          <ShieldQuestion size={16} />
          <div>
            <strong>No comparable findings.</strong>
            <p>
              Searched {signal.corpus_size ?? 0} historical findings and matched
              {' '}{signal.neighbours_found ?? 0} closely enough to compare
              {signal.required ? ` (${signal.required} needed)` : ''}. On the evidence
              available this looks like an isolated issue rather than a recurring one.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (signal.status === 'DUPLICATE_SUSPECTED') {
    return (
      <div className="signal-panel">
        <div className="signal-head"><Copy size={16} /><h3>Possible duplicate</h3></div>
        <div className="signal-empty">
          <p>
            This is near-identical to <strong>{signal.duplicate_of?.qa_error_code}</strong>.
            Treated as a re-filing rather than a recurrence, so it does not inflate the trend.
          </p>
        </div>
      </div>
    );
  }

  const band = BAND_STYLE[signal.risk_band] || BAND_STYLE.LOW;
  const m = signal.metrics || {};
  const degraded = signal.status === 'DEGRADED';

  return (
    <div className="signal-panel">
      <div className="signal-head">
        <Activity size={16} />
        <h3>Quality Signal</h3>
        <span className="signal-band" style={{ background: band.bg, color: band.fg }}>
          {band.label} RECURRENCE RISK
        </span>
        <button className="signal-icon-btn" onClick={() => load(true)} title="Recompute">
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Facts first. Every figure below is computed in SQL, not by a model. */}
      <div className="signal-metrics">
        <Metric label="similar findings" value={m.similar_90d ?? 0} hint="last 90 days" />
        <Metric label="same process" value={m.same_process ?? 0} />
        <Metric label="same team" value={m.same_team ?? 0} />
        <Metric
          label="vs previous quarter"
          value={`${(m.qoq_delta_pct ?? 0) > 0 ? '+' : ''}${Math.round(m.qoq_delta_pct ?? 0)}%`}
        />
      </div>

      {signal.score_breakdown?.components && (
        <div className="signal-breakdown">
          <div className="signal-breakdown-title">
            Score {signal.risk_score} — how it was reached
          </div>
          {signal.score_breakdown.components.map((c) => (
            <div key={c.name} className="signal-bar-row">
              <span>{COMPONENT_LABEL[c.name] || c.name}</span>
              <div className="signal-bar-track">
                <div className="signal-bar-fill" style={{ width: `${c.contribution}%` }} />
              </div>
              <span className="signal-bar-value">{c.contribution}</span>
            </div>
          ))}
        </div>
      )}

      {/* Interpretation, kept visually and structurally subordinate to the facts. */}
      <div className="signal-divider">
        <span>{degraded ? 'AI narrative unavailable' : 'AI-generated interpretation'}</span>
      </div>

      {degraded ? (
        <div className="signal-degraded">
          <AlertTriangle size={14} />
          <p>
            The language model could not be reached. The figures above are unaffected —
            they come from the QEMS database.
          </p>
        </div>
      ) : signal.narrative ? (
        <div className="signal-narrative">
          <p className="signal-label">{signal.narrative.label}</p>
          {signal.narrative.contributing_factors?.length > 0 && (
            <ul>
              {signal.narrative.contributing_factors.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          )}
          {signal.narrative.recommended_action && (
            <p className="signal-action">
              <strong>Suggested action:</strong> {signal.narrative.recommended_action}
            </p>
          )}
        </div>
      ) : null}

      {signal.neighbours?.length > 0 && (
        <details className="signal-neighbours">
          <summary>{signal.neighbours.length} comparable findings the analysis used</summary>
          {signal.neighbours.map((n) => (
            <div key={n.error_id} className="signal-neighbour">
              <code>{n.qa_error_code}</code>
              <span>{n.title}</span>
              <em>{n.status}</em>
            </div>
          ))}
        </details>
      )}

      <p className="signal-disclaimer">{signal.disclaimer}</p>

      {signal.reviewer_action ? (
        <div className="signal-acked">
          Acknowledged: <strong>{signal.reviewer_action.replace(/_/g, ' ').toLowerCase()}</strong>
        </div>
      ) : (
        <div className="signal-ack">
          {showAck ? (
            <>
              <textarea
                placeholder="Why? (required unless accepting)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
              />
              <div className="signal-ack-row">
                <button disabled={busy} onClick={() => submitAck(showAck)}>Confirm</button>
                <button disabled={busy} onClick={() => setShowAck(null)}>Cancel</button>
              </div>
            </>
          ) : (
            <div className="signal-ack-row">
              <button onClick={() => submitAck('ACCEPTED')} disabled={busy}>
                <Check size={13} /> Accept
              </button>
              <button onClick={() => setShowAck('PARTIALLY_ACCEPTED')} disabled={busy}>
                Partially
              </button>
              <button onClick={() => setShowAck('REJECTED')} disabled={busy}>
                <X size={13} /> Reject
              </button>
            </div>
          )}
        </div>
      )}

      {signal.provenance && (
        <details className="signal-provenance">
          <summary>Provenance</summary>
          <div>Model: <code>{signal.provenance.model}</code></div>
          <div>Prompt: <code>{signal.provenance.prompt_version || 'n/a (metrics only)'}</code></div>
          <div>Generated: {new Date(signal.provenance.generated_at).toLocaleString()}</div>
          {signal.provenance.offline_embedder && (
            <div className="signal-warn">
              Offline lexical embedder in use — configure OPENAI_API_KEY for semantic matching.
            </div>
          )}
        </details>
      )}
    </div>
  );
};
