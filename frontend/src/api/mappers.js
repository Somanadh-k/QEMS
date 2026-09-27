// Backend rows only carry foreign keys (department_id, category_id, raised_by, ...) — these
// helpers resolve them to display names using the /departments, /categories, /users lookups.

export const nameById = (list, id, idKey, nameKey = 'name') => {
  if (id == null) return null;
  const match = list.find((item) => item[idKey] === id);
  return match ? match[nameKey] : `#${id}`;
};

export const mapListItem = (item, { departments, categories }) => ({
  pk: item.error_id,
  id: item.qa_error_code,
  title: item.title,
  status: item.status,
  severity: item.severity,
  departmentId: item.department_id,
  department: nameById(departments, item.department_id, 'department_id'),
  categoryId: item.category_id,
  category: nameById(categories, item.category_id, 'category_id'),
  dueAt: item.due_at,
  date: item.created_at?.split('T')[0],
  createdAt: item.created_at,
  // Governance fields (SLA-02 / RS-08) — drive the queue's sort order and state chips.
  slaState: item.sla_state,
  slaDueAt: item.sla_due_at,
  clockOwner: item.sla_clock_owner_role,
  riskScore: item.risk_score,
  escalationLevel: item.escalation_level,
});

export const mapRebuttal = (r, users) => ({
  id: r.rebuttal_id,
  author: nameById(users, r.raised_by, 'user_id', 'full_name') || `User #${r.raised_by}`,
  date: new Date(r.created_at).toLocaleString(),
  text: r.justification,
  status: r.status,
});

export const mapDecision = (d, users) => ({
  id: d.decision_id,
  author: nameById(users, d.decided_by, 'user_id', 'full_name') || `User #${d.decided_by}`,
  date: new Date(d.decided_at).toLocaleString(),
  decision: d.decision,
  notes: d.notes,
});

export const mapDetail = (detail, { departments, categories, users }) => ({
  pk: detail.error_id,
  id: detail.qa_error_code,
  title: detail.title,
  description: detail.description,
  status: detail.status,
  severity: detail.severity,
  departmentId: detail.department_id,
  department: nameById(departments, detail.department_id, 'department_id'),
  categoryId: detail.category_id,
  category: nameById(categories, detail.category_id, 'category_id'),
  raisedBy: detail.raised_by,
  raisedByName: nameById(users, detail.raised_by, 'user_id', 'full_name') || `User #${detail.raised_by}`,
  assignedTo: detail.assigned_to,
  assignedToName: detail.assigned_to
    ? nameById(users, detail.assigned_to, 'user_id', 'full_name') || `User #${detail.assigned_to}`
    : 'Unassigned',
  date: detail.date_discovered,
  dueAt: detail.due_at,
  createdAt: detail.created_at,
  updatedAt: detail.updated_at,
  closedAt: detail.closed_at,
  evidence: detail.evidence || [],
  rebuttals: (detail.rebuttals || []).map((r) => mapRebuttal(r, users)),
  decisions: (detail.decisions || []).map((d) => mapDecision(d, users)),
});
