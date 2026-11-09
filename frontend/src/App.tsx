import { useEffect, useState } from 'react';

type User = { name: string; email?: string };
type Template = {
  id: string;
  name: string;
  department: string;
  category: string;
  ownerRole: string;
  type: string;
  description: string;
};

const api = async (path: string, init?: RequestInit) => {
  const response = await fetch(path, { credentials: 'include', ...init });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${response.status})`);
  }
  return response.json();
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [query, setQuery] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    try {
      const me = await api('/api/me');
      setUser(me.user);
      const catalog = await api('/api/templates');
      setTemplates(catalog.templates);
    } catch {
      setUser(null);
      setTemplates([]);
    }
  };

  useEffect(() => { void load(); }, []);

  const signOut = async () => {
    await api('/auth/logout', { method: 'POST' });
    setUser(null);
    setTemplates([]);
  };

  const createCopy = async (template: Template) => {
    setBusy(template.id);
    setMessage('');
    try {
      const result = await api(`/api/templates/${encodeURIComponent(template.id)}/copy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      setMessage(`A copy of “${template.name}” was created.`);
      if (result.copy.url) window.open(result.copy.url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      setMessage(error instanceof Error ? error.message.replaceAll('_', ' ') : 'Unable to create copy.');
    } finally {
      setBusy(null);
    }
  };

  const visible = templates.filter((item) =>
    `${item.name} ${item.department} ${item.category} ${item.ownerRole} ${item.description}`
      .toLowerCase().includes(query.toLowerCase().trim()),
  );

  if (!user) {
    return <main className="signin"><div className="brand-mark">OD1</div><p className="eyebrow">COMPANY WORKSPACES</p><h1>Office Desk 1</h1><p>Find approved templates and create your own working copies.</p><a className="button primary" href="/auth/login">Sign in with your company account</a></main>;
  }

  return (
    <div className="app-shell">
      <header className="topbar"><div className="brand"><span className="brand-mark">OD1</span><span>Office Desk 1<small>Company Workspaces</small></span></div><div className="user-area"><span>{user.name}</span><button className="button secondary" onClick={signOut}>Sign out</button></div></header>
      <main className="content">
        <section className="hero"><p className="eyebrow">ONE DESK. EVERY DEPARTMENT.</p><h1>Find the right template.<br />Get work moving.</h1><p>Browse approved company starting points. Creating a template always makes a separate copy.</p></section>
        <section className="catalog"><div className="section-heading"><div><p className="eyebrow">TEMPLATE CATALOG</p><h2>Browse templates</h2></div><span>{visible.length} templates</span></div>
          <label className="search-label" htmlFor="template-search">Search templates</label><input id="template-search" className="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name, department, or keyword" />
          {message && <p className="notice" role="status">{message}</p>}
          <div className="grid">{visible.map((template) => <article className="card" key={template.id}><span className="badge">{template.type}</span><h3>{template.name}</h3><p>{template.description}</p><dl><div><dt>Department</dt><dd>{template.department}</dd></div><div><dt>Owner</dt><dd>{template.ownerRole}</dd></div></dl><button className="button primary" onClick={() => void createCopy(template)} disabled={busy === template.id}>{busy === template.id ? 'Creating copy…' : 'Create my copy'}</button></article>)}</div>
          {visible.length === 0 && <p className="empty">No templates match that search.</p>}
        </section>
      </main>
    </div>
  );
}
