import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Avatar } from './Avatar';
import { PrimaryButton } from './PrimaryButton';
import {
  getMessages,
  sendMessage,
  markMessageRead,
  uploadMessageAttachment,
  getAttachmentUrl,
  ApiError,
} from '../api/client';
import {
  MessageSquare,
  Send,
  Paperclip,
  FileText,
  Search,
  CornerUpLeft,
  X,
  CheckCheck,
  Check,
  Loader2,
} from 'lucide-react';

const POLL_INTERVAL_MS = 8000;

const STATUS_TONE = {
  'Awaiting QA': 'badge-review',
  'Awaiting Stakeholder': 'badge-open',
  'Under Review': 'badge-in-review',
  'Evidence Requested': 'badge-rebuttal-raised',
  'Response Received': 'badge-qa-decision-pending',
  Resolved: 'badge-resolved',
};

const MENTION_RE = /(@[A-Za-z][\w.]*)/g;

// Lightweight, display-only @mention highlighting -- no backend mention parsing or
// targeted mention-notifications (the message's own recipient already gets notified).
const renderWithMentions = (text) =>
  // split() with a capturing group interleaves matches at odd indices -- no need to
  // re-test each part (and re-testing a `g`-flagged regex with .test() would be
  // stateful/buggy anyway).
  text.split(MENTION_RE).map((part, i) =>
    i % 2 === 1 ? (
      <span key={i} style={{ color: 'var(--primary)', fontWeight: 600 }}>{part}</span>
    ) : (
      <React.Fragment key={i}>{part}</React.Fragment>
    )
  );

const formatTime = (iso) =>
  new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });

const AttachmentChip = ({ attachment, addToast }) => {
  const [busy, setBusy] = useState(false);

  const download = async () => {
    setBusy(true);
    try {
      const { url } = await getAttachmentUrl(attachment.attachment_id);
      window.open(url, '_blank', 'noreferrer');
    } catch (err) {
      addToast(err.message || 'Could not open attachment.', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={download}
      disabled={busy}
      style={{
        display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.4rem 0.7rem',
        background: 'var(--bg-primary)', border: '1px solid var(--border-light)',
        borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', color: 'var(--text-main)',
        cursor: 'pointer',
      }}
      title={`Download ${attachment.file_name}`}
    >
      {busy ? <Loader2 size={14} className="spin" /> : <FileText size={14} color="var(--primary)" />}
      <span>{attachment.file_name}</span>
      <span style={{ color: 'var(--text-muted)' }}>{attachment.file_size_kb} KB</span>
    </button>
  );
};

/**
 * Enterprise-style conversation thread for a single QA Error. Communication is always
 * scoped to `errorId` -- there is no cross-error inbox, matching the backend, which has
 * no endpoint that lets a message exist outside its error's context.
 */
export const CommunicationPanel = ({ errorId, currentUser, addToast }) => {
  const [items, setItems] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [status, setStatus] = useState('Under Review');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [draft, setDraft] = useState('');
  const [replyTo, setReplyTo] = useState(null);
  const [pendingFile, setPendingFile] = useState(null);
  const [sending, setSending] = useState(false);

  const fileInputRef = useRef(null);
  const listEndRef = useRef(null);
  const markedRef = useRef(new Set());

  const load = useCallback(async () => {
    try {
      const res = await getMessages(errorId);
      setItems(res.items);
      setUnreadCount(res.unread_count);
      setStatus(res.communication_status);
    } catch (err) {
      if (!(err instanceof ApiError)) throw err; // real bugs still surface
    } finally {
      setLoading(false);
    }
  }, [errorId]);

  useEffect(() => {
    markedRef.current = new Set();
    load();
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [items.length]);

  // Mark incoming (not-mine) unread messages as read once they're rendered in view.
  useEffect(() => {
    items.forEach((m) => {
      if (!m.is_read && m.sender_id !== currentUser.user_id && !markedRef.current.has(m.message_id)) {
        markedRef.current.add(m.message_id);
        markMessageRead(m.message_id).catch(() => markedRef.current.delete(m.message_id));
      }
    });
  }, [items, currentUser.user_id]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!draft.trim() && !pendingFile) return;
    setSending(true);
    try {
      const created = await sendMessage(errorId, draft.trim() || `Sent ${pendingFile?.name}`, {
        parentMessageId: replyTo?.message_id ?? null,
      });
      if (pendingFile) {
        await uploadMessageAttachment(created.message_id, pendingFile);
      }
      setDraft('');
      setPendingFile(null);
      setReplyTo(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await load();
    } catch (err) {
      addToast(err.message || 'Failed to send message.', 'error');
    } finally {
      setSending(false);
    }
  };

  const filtered = search.trim()
    ? items.filter((m) => m.message.toLowerCase().includes(search.trim().toLowerCase()))
    : items;

  return (
    <div className="glass-card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <h2 style={{ fontSize: '1.1rem', color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <MessageSquare size={20} color="var(--primary)" />
          Communication
          {unreadCount > 0 && (
            <span className="badge-dot" style={{ position: 'static', marginLeft: '0.3rem' }} title={`${unreadCount} unread`} />
          )}
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span className={`badge ${STATUS_TONE[status] || 'badge-review'}`}>{status}</span>
          <div className="search-input-group" style={{ padding: '0.3rem 0.7rem' }}>
            <Search size={14} />
            <input
              type="text"
              placeholder="Search conversation…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ fontSize: '0.8rem', width: '160px' }}
            />
          </div>
        </div>
      </div>

      <div
        style={{
          display: 'flex', flexDirection: 'column', gap: '0.9rem', maxHeight: '420px',
          overflowY: 'auto', paddingRight: '0.25rem', marginBottom: '1rem',
        }}
      >
        {loading ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading conversation…</p>
        ) : filtered.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            {search ? 'No messages match your search.' : 'No messages yet. Start the conversation below.'}
          </p>
        ) : (
          filtered.map((m) => {
            const isMine = m.sender_id === currentUser.user_id;
            const parent = m.parent_message_id ? items.find((i) => i.message_id === m.parent_message_id) : null;
            return (
              <div key={m.message_id} style={{ display: 'flex', gap: '0.75rem', flexDirection: isMine ? 'row-reverse' : 'row' }}>
                <Avatar name={m.sender_name} size={34} />
                <div style={{ maxWidth: '78%' }}>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'baseline', flexDirection: isMine ? 'row-reverse' : 'row' }}>
                    <strong style={{ fontSize: '0.85rem', color: 'var(--text-main)' }}>{m.sender_name}</strong>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>{m.sender_role}</span>
                  </div>
                  {parent && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                      <CornerUpLeft size={11} /> {parent.message.slice(0, 60)}{parent.message.length > 60 ? '…' : ''}
                    </div>
                  )}
                  <div
                    style={{
                      marginTop: '0.3rem', padding: '0.65rem 0.9rem', borderRadius: 'var(--radius-md)',
                      background: isMine ? 'var(--primary-light)' : 'var(--bg-primary)',
                      border: '1px solid var(--border-light)', fontSize: '0.88rem', color: 'var(--text-main)',
                      lineHeight: 1.5, whiteSpace: 'pre-wrap',
                    }}
                  >
                    {renderWithMentions(m.message)}
                    {m.message_type === 'EVIDENCE_REQUEST' && (
                      <div style={{ marginTop: '0.4rem' }}><span className="badge badge-rebuttal-raised" style={{ fontSize: '0.65rem' }}>Evidence requested</span></div>
                    )}
                  </div>
                  {m.attachments.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.4rem', justifyContent: isMine ? 'flex-end' : 'flex-start' }}>
                      {m.attachments.map((a) => (
                        <AttachmentChip key={a.attachment_id} attachment={a} addToast={addToast} />
                      ))}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', marginTop: '0.25rem', justifyContent: isMine ? 'flex-end' : 'flex-start' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>{formatTime(m.created_at)}</span>
                    {isMine && (m.is_read ? <CheckCheck size={13} color="var(--primary)" /> : <Check size={13} color="var(--text-subtle)" />)}
                    {!isMine && (
                      <button
                        type="button"
                        onClick={() => setReplyTo(m)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-subtle)', fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                      >
                        <CornerUpLeft size={11} /> Reply
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
        <div ref={listEndRef} />
      </div>

      {replyTo && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-primary)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-sm)', padding: '0.4rem 0.7rem', marginBottom: '0.6rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          <span>Replying to <strong>{replyTo.sender_name}</strong>: {replyTo.message.slice(0, 50)}{replyTo.message.length > 50 ? '…' : ''}</span>
          <button type="button" onClick={() => setReplyTo(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={14} />
          </button>
        </div>
      )}

      {pendingFile && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-primary)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-sm)', padding: '0.4rem 0.7rem', marginBottom: '0.6rem', fontSize: '0.78rem', color: 'var(--text-main)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}><Paperclip size={13} /> {pendingFile.name}</span>
          <button type="button" onClick={() => { setPendingFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={14} />
          </button>
        </div>
      )}

      <form onSubmit={handleSend} style={{ display: 'flex', gap: '0.6rem', alignItems: 'flex-end' }}>
        <button
          type="button"
          className="icon-btn"
          title="Attach a file"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip size={16} />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          onChange={(e) => setPendingFile(e.target.files?.[0] || null)}
        />
        <textarea
          className="form-control"
          rows={1}
          placeholder="Type a message… (@mention supported)"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend(e);
            }
          }}
          style={{ flex: 1, resize: 'none' }}
        />
        <PrimaryButton type="submit" disabled={sending || (!draft.trim() && !pendingFile)}>
          {sending ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
        </PrimaryButton>
      </form>
    </div>
  );
};
