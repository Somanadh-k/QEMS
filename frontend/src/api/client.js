const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const ACCESS_TOKEN_KEY = 'qems_access_token';
const REFRESH_TOKEN_KEY = 'qems_refresh_token';

export const getAccessToken = () => localStorage.getItem(ACCESS_TOKEN_KEY);
export const getRefreshToken = () => localStorage.getItem(REFRESH_TOKEN_KEY);

export const setTokens = (accessToken, refreshToken) => {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
};

export const clearTokens = () => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
};

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

/** Thrown when a request 401s and the refresh attempt also fails — callers should log out. */
export class SessionExpiredError extends ApiError {}

let refreshPromise = null;

const doRefresh = async () => {
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new SessionExpiredError('No refresh token', 401, 'no_refresh_token');

  const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) {
    clearTokens();
    throw new SessionExpiredError('Session expired, please log in again.', res.status, 'session_expired');
  }
  const data = await res.json();
  setTokens(data.access_token, null);
  return data.access_token;
};

/**
 * Core request helper. Attaches the JWT, parses the backend's structured
 * {"error": {"code", "message"}} shape (Section 9.5), and transparently retries once
 * after refreshing an expired access token.
 */
async function request(path, { method = 'GET', body, isFormData = false, auth = true, _retried = false } = {}) {
  const headers = {};
  if (!isFormData) headers['Content-Type'] = 'application/json';
  if (auth) {
    const token = getAccessToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && auth && !_retried) {
    if (!refreshPromise) refreshPromise = doRefresh().finally(() => { refreshPromise = null; });
    await refreshPromise;
    return request(path, { method, body, isFormData, auth, _retried: true });
  }

  if (res.status === 204) return null;

  const isJson = res.headers.get('content-type')?.includes('application/json');
  const data = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    const message = data?.error?.message || data?.detail || res.statusText;
    const code = data?.error?.code || 'error';
    if (res.status === 401) throw new SessionExpiredError(message, res.status, code);
    throw new ApiError(message, res.status, code);
  }

  return data;
}

// --- Auth ---
export const login = (email, password) => request('/auth/login', { method: 'POST', body: { email, password }, auth: false });

// --- Errors ---
export const listErrors = (params = {}) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return request(`/errors${suffix}`);
};
export const getError = (errorId) => request(`/errors/${errorId}`);
export const createError = (payload) => request('/errors', { method: 'POST', body: payload });
export const updateErrorStatus = (errorId, status, adminOverride = false) =>
  request(`/errors/${errorId}/status`, { method: 'PATCH', body: { status, admin_override: adminOverride } });
export const submitRebuttal = (errorId, justification) =>
  request(`/errors/${errorId}/rebuttals`, { method: 'POST', body: { justification } });
export const recordDecision = (errorId, decision, notes) =>
  request(`/errors/${errorId}/decision`, { method: 'POST', body: { decision, notes } });
export const uploadEvidence = (errorId, file) => {
  const form = new FormData();
  form.append('file', file);
  return request(`/errors/${errorId}/evidence`, { method: 'POST', body: form, isFormData: true });
};

// --- Lookups ---
export const listDepartments = () => request('/departments');
export const listCategories = () => request('/categories');
export const listUsers = () => request('/users');
// Business processes. Recurrence concentration is measured per process, so an error
// filed without one has the heaviest component of its recurrence score zeroed out.
export const listProcesses = () => request('/processes');

// --- Profile ---
export const getMe = () => request('/auth/me');
export const updateProfile = (payload) => request('/auth/me', { method: 'PATCH', body: payload });

// --- Reports ---
export const reportsSummary = (params = {}) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return request(`/reports/summary${suffix}`);
};

// Server-computed CSV (not a client-side dump of already-loaded rows) -- same endpoint
// as reportsSummary, ?format=csv. request() already returns non-JSON bodies as text.
export const exportReportCsv = (params = {}) => {
  const qs = new URLSearchParams({ ...Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v != null)), format: 'csv' });
  return request(`/reports/summary?${qs.toString()}`);
};

// --- Quality Signal Engine (QS-01) ---
// Read-only by design: there is no client call that lets an AI output write to a
// workflow field. Acknowledging records what the reviewer did, not what the model said.
export const getSignal = (errorId) => request(`/errors/${errorId}/signal`);
export const recomputeSignal = (errorId) =>
  request(`/errors/${errorId}/signal/recompute`, { method: 'POST' });
export const listInsights = (errorId) => request(`/errors/${errorId}/insights`);
export const acknowledgeInsight = (insightId, action, notes) =>
  request(`/insights/${insightId}/ack`, { method: 'POST', body: { action, notes } });

// --- SLA & escalation (SLA-02) ---
export const getSla = (errorId) => request(`/errors/${errorId}/sla`);
export const pauseSla = (errorId, reason) =>
  request(`/errors/${errorId}/sla/pause`, { method: 'POST', body: { reason } });
export const listEscalations = (acknowledged = false) =>
  request(`/escalations?acknowledged=${acknowledged}`);
export const acknowledgeEscalation = (escalationId, nextAction, eta = null) =>
  request(`/escalations/${escalationId}/ack`, { method: 'POST', body: { next_action: nextAction, eta } });
export const listSlaPolicies = () => request('/sla/policies');

// --- Audit trail (section 13) ---
export const getErrorAudit = (errorId) => request(`/errors/${errorId}/audit`);
export const verifyAuditChain = () => request('/audit/verify');

// --- Analytics ---
export const analyticsTrends = (days = 180) => request(`/reports/analytics/trends?days=${days}`);

// --- Communication (two-way conversation per error) ---
export const getMessages = (errorId) => request(`/errors/${errorId}/messages`);
export const sendMessage = (errorId, message, { parentMessageId = null, messageType = 'TEXT' } = {}) =>
  request(`/errors/${errorId}/messages`, {
    method: 'POST',
    body: { message, parent_message_id: parentMessageId, message_type: messageType },
  });
export const markMessageRead = (messageId) =>
  request(`/messages/${messageId}/read`, { method: 'PATCH' });
export const uploadMessageAttachment = (messageId, file) => {
  const form = new FormData();
  form.append('file', file);
  return request(`/messages/${messageId}/attachments`, { method: 'POST', body: form, isFormData: true });
};
export const getAttachmentUrl = (attachmentId) =>
  request(`/messages/attachments/${attachmentId}/url`);

// --- Notifications ---
export const getErrorNotifications = (errorId) => request(`/errors/${errorId}/notifications`);
export const getUnreadNotificationCount = () => request('/notifications/unread-count');

// --- AI ---
export const aiRootCause = (errorId) => request('/ai/root-cause', { method: 'POST', body: { error_id: errorId } });
export const aiSimilar = (errorId) => request(`/ai/similar/${errorId}`);
export const aiSeverityPrediction = (title, description) =>
  request('/ai/severity-prediction', { method: 'POST', body: { title, description } });
export const aiNlSearch = (query) => request('/ai/nl-search', { method: 'POST', body: { query } });
