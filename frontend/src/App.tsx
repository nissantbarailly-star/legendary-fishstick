import { useEffect, useMemo, useState } from 'react';

type User = { name: string; email?: string };
type Department = { id: string; name: string; category: string; description: string; ownerRole: string; templatesCount: number };
type Template = { id: string; name: string; department: string; departmentId: string; category: string; ownerRole: string; type: string; description: string; copyAvailable: boolean };
type RolloutTask = { id: string; phase: string; title: string; ownerRole: string; complete: boolean };

let csrfToken = '';
async function api(path: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (init?.method && init.method !== 'GET') headers.set('X-CSRF-Token', csrfToken);
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, { credentials: 'include', ...init, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [tasks, setTasks] = useState<RolloutTask[]>([]);
  const [query, setQuery] = useState('');
  const [section, setSection] = useState('Dashboard');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    try {
      const me = await api('/api/me');
      setUser(me.user);
      const csrf = await api('/api/csrf'); csrfToken = csrf.token;
      const [catalog, deptData, rollout] = await Promise.all([api('/api/templates'), api('/api/departments'), api('/api/rollout')]);
      setTemplates(catalog.templates); setDepartments(deptData.departments); setTasks(rollout.tasks);
    } catch { setUser(null); setTemplates([]); }
  };
  useEffect(() => { void load(); }, []);

  const signOut = async () => { try { await api('/auth/logout', { method: 'POST' }); } finally { csrfToken = ''; setUser(null); setTemplates([]); } };
  const createCopy = async (item: Template) => {
    setBusy(item.id); setMessage('');
    try {
      const result = await api(`/api/templates/${encodeURIComponent(item.id)}/copy`, { method: 'POST', body: JSON.stringify({}) });
      setMessage(`A working copy of “${item.name}” was created.`);
      if (result.copy.url) window.open(result.copy.url, '_blank', 'noopener,noreferrer');
    } catch (error) { setMessage(error instanceof Error ? error.message.replaceAll('_', ' ') : 'Unable to create copy.'); }
    finally { setBusy(null); }
  };
  const visible = useMemo(() => templates.filter((item) => `${item.name} ${item.department} ${item.category} ${item.ownerRole} ${item.description}`.toLowerCase().includes(query.toLowerCase().trim())), [templates, query]);
  const totalDone = tasks.filter((task) => task.complete).length;

  if (!user) return <main className="signin"><div className="brand-mark">OD1</div><p className="eyebrow">COMPANY WORKSPACES</p><h1>Office Desk 1</h1><p>Find approved templates and create your own working copies.</p><a className="button primary" href="/auth/login">Sign in with your company account</a></main>;

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><span className="brand-mark">OD1</span><span>Office Desk 1<small>Company Workspaces</small></span></div><div className="user-area"><span>{user.name}</span><button className="button secondary" onClick={signOut}>Sign out</button></div></header>
    <div className="layout"><aside className="sidebar" aria-label="Main navigation"><p className="nav-label">WORKSPACE</p>{['Dashboard', 'Departments', 'Template catalog'].map((name) => <button key={name} className={`nav-item ${section === name ? 'selected' : ''}`} onClick={() => setSection(name)}>{name}</button>)}<p className="nav-label">OPERATIONS</p>{['Governance', '14-week rollout', 'KPIs & reporting', 'Catalog admin'].map((name) => <button key={name} className={`nav-item ${section === name ? 'selected' : ''}`} onClick={() => setSection(name)}>{name}</button>)}</aside>
      <main className="content">
        <section className="hero"><p className="eyebrow">ONE DESK. EVERY DEPARTMENT.</p><h1>{section === 'Dashboard' ? <>Find the right template.<br />Get work moving.</> : section}</h1><p>Browse approved company starting points. Creating a template always makes a separate copy.</p></section>
        {section === 'Dashboard' && <><div className="stats"><article><span>Departments</span><b>{departments.length}</b></article><article><span>Templates</span><b>{templates.length}</b></article><article><span>Rollout tasks done</span><b>{totalDone}/{tasks.length}</b></article><article><span>Categories</span><b>{new Set(departments.map((d) => d.category)).size}</b></article></div><div className="section-heading"><div><p className="eyebrow">YOUR WORKSPACES</p><h2>Browse departments</h2></div><button className="text-button" onClick={() => setSection('Departments')}>View all →</button></div><div className="grid">{departments.slice(0, 6).map((d) => <button className="department-card" key={d.id} onClick={() => { setSection('Departments'); setQuery(d.name); }}><span>{d.templatesCount} templates · {d.category}</span><h3>{d.name}</h3><p>{d.description}</p><small>OWNER · {d.ownerRole}</small></button>)}</div></>}
        {['Departments', 'Template catalog', 'Catalog admin'].includes(section) && <section className="catalog"><div className="section-heading"><div><p className="eyebrow">TEMPLATE INVENTORY</p><h2>{section === 'Departments' ? 'Department templates' : 'Browse templates'}</h2></div><span>{visible.length} templates</span></div><label className="search-label" htmlFor="template-search">Search templates</label><input id="template-search" className="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name, department, or keyword" />{message && <p className="notice" role="status">{message}</p>}<div className="grid">{visible.map((item) => <article className="card" key={item.id}><span className="badge">{item.type} · {item.department}</span><h3>{item.name}</h3><p>{item.description}</p><dl><div><dt>Department</dt><dd>{item.department}</dd></div><div><dt>Owner</dt><dd>{item.ownerRole}</dd></div></dl><button className="button primary" onClick={() => void createCopy(item)} disabled={busy === item.id || !item.copyAvailable}>{busy === item.id ? 'Creating copy…' : item.copyAvailable ? 'Create my copy' : 'Source not connected'}</button></article>)}</div>{visible.length === 0 && <p className="empty">No templates match that search.</p>}</section>}
        {section === 'Governance' && <div className="panel"><h2>Ownership & control</h2><ul><li>Template owners review content quarterly and nominate a backup.</li><li>Change requests are stored centrally and require owner approval.</li><li>Restricted completed documents must follow normal company permissions.</li></ul><p className="muted">Administrative access is enforced by the API using the configured identity group.</p></div>}
        {section === '14-week rollout' && <div className="panel"><h2>Rollout checklist</h2><p>{totalDone} of {tasks.length} tasks complete. Checklist state is server-backed.</p>{tasks.length === 0 && <p className="empty">No rollout tasks have been configured yet.</p>}{tasks.map((task) => <label className="task" key={task.id}><input type="checkbox" checked={task.complete} readOnly /><span>{task.phase}: {task.title}<small>Owner: {task.ownerRole}</small></span></label>)}</div>}
        {section === 'KPIs & reporting' && <div className="panel"><h2>Adoption targets</h2><p>Live KPI reporting requires production event collection and a verified employee denominator. The scaffold does not claim to measure adoption.</p><div className="stats"><article><span>Weekly active users target</span><b>≥40%</b></article><article><span>Search success target</span><b>≥50%</b></article><article><span>Template freshness target</span><b>100%</b></article></div></div>}
        {section === 'Catalog admin' && <div className="panel"><h2>Admin API is available</h2><p>Catalog write endpoints are group-gated. A full validated admin editor and change-request review UI remains a follow-up; do not treat this read-only view as an admin console.</p></div>}
      </main>
    </div>
  </div>;
}
