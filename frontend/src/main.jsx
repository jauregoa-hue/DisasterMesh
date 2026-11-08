import React, { useState, useEffect, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const RESCUE_ID = '!0436bda8';
const fmtTime = value => value ? new Date(value).toLocaleString() : '—';
const nice = value => (value || 'unknown').replaceAll('_', ' ').toUpperCase();
const shortTime = value => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';

function Icon({ name, size = 18 }) {
  const common = { width: size, height: size, fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', viewBox: '0 0 24 24', 'aria-hidden': true };
  const paths = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    radio: <><circle cx="12" cy="12" r="2"/><path d="M7.8 7.8a6 6 0 0 0 0 8.4m8.4-8.4a6 6 0 0 1 0 8.4M4.6 4.6a10.5 10.5 0 0 0 0 14.8m14.8-14.8a10.5 10.5 0 0 1 0 14.8"/></>,
    shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/></>,
    alert: <><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v4m0 4h.01"/></>,
    pin: <><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/></>,
    pulse: <><path d="M2 12h4l3-7 5 14 3-7h5"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.5 9a7 7 0 0 1 12-2L20 12M4 12l2.5 5a7 7 0 0 0 12-2"/></>,
    logout: <><path d="M9 3H4v18h5M16 17l5-5-5-5M21 12H9"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    chevron: <path d="m9 18 6-6-6-6"/>,
    satellite: <><path d="m6 6 12 12m-9-3 6-6M3 10l7-7 4 4-7 7-4-4Zm7 7 7-7 4 4-7 7-4-4Z"/></>,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></>,
    terminal: <><rect x="2" y="3" width="20" height="18" rx="2"/><path d="m6 9 3 3-3 3m6 0h6"/></>,
  };
  return <svg {...common}>{paths[name] || paths.pulse}</svg>;
}

function App() {
  const [auth, setAuth] = useState(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [items, setItems] = useState([]);
  const [radioMessages, setRadioMessages] = useState([]);
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [notice, setNotice] = useState('');
  const [summaries, setSummaries] = useState({});
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState('overview');
  const [lastRefresh, setLastRefresh] = useState(null);

  const api = useCallback(async (path, options = {}) => {
    const res = await fetch('/api' + path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(auth ? { Authorization: 'Bearer ' + auth.access_token } : {}),
        ...(options.headers || {}),
      },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${res.status})`);
    return data;
  }, [auth]);

  const refresh = useCallback(async () => {
    if (!auth) return;
    try {
      const [incidents, radios] = await Promise.all([
        api('/incidents'),
        auth.role !== 'citizen' ? api('/gateway/messages') : Promise.resolve([]),
      ]);
      setItems(incidents);
      setRadioMessages(radios);
      setLastRefresh(new Date());
    } catch (e) { setNotice(e.message); }
  }, [auth, api]);

  useEffect(() => {
    if (!auth) return;
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [auth, refresh]);

  async function signIn(register = false) {
    setBusy(true);
    try {
      setNotice('');
      if (register) {
        await api('/auth/register', { method: 'POST', body: JSON.stringify({ username, password }) });
        setNotice('Citizen account created. Log in to continue.');
      } else {
        const a = await api('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
        setAuth(a);
        setPassword('');
      }
    } catch (e) { setNotice(e.message); }
    finally { setBusy(false); }
  }
  async function submit(e) {
    e.preventDefault(); setBusy(true);
    try {
      await api('/incidents', { method: 'POST', body: JSON.stringify({ title, message }) });
      setTitle(''); setMessage(''); setNotice('Incident report transmitted successfully.'); await refresh(); setView('incidents');
    } catch (e) { setNotice(e.message); }
    finally { setBusy(false); }
  }
  async function update(id, state) {
    try { await api('/incidents/' + id, { method: 'PATCH', body: JSON.stringify({ state }) }); await refresh(); }
    catch (e) { setNotice(e.message); }
  }
  async function summarize(id) {
    try {
      const data = await api('/incidents/' + id + '/summary');
      setSummaries(prev => ({ ...prev, [id]: `${data.summary} (${data.source})` }));
    } catch (e) { setNotice(e.message); }
  }
  function signOut() {
    setAuth(null); setItems([]); setRadioMessages([]); setSummaries({}); setNotice(''); setView('overview');
  }

  const canRespond = auth && auth.role !== 'citizen';
  const openCount = items.filter(i => i.state === 'open').length;
  const urgentCount = items.filter(i => i.priority === 'high' && i.state !== 'resolved').length;
  const gpsCount = radioMessages.filter(r => r.latitude != null && r.longitude != null).length;
  const latestRadio = radioMessages[0];
  const incidentRows = view === 'overview' ? items.slice(0, 5) : items;

  const incidentsPanel = <section className="panel incidents-panel" aria-label="Incident reports">
    <div className="panel-heading"><div><p className="eyebrow">LIVE INCIDENT FEED</p><h2>Incident reports</h2></div><div className="heading-actions"><span className="mini-live"><span className="dot"/> AUTO-SYNC</span><button className="icon-button" onClick={refresh} title="Refresh incident feed"><Icon name="refresh"/></button></div></div>
    {incidentRows.length === 0 ? <div className="empty-state"><Icon name="pulse" size={26}/><strong>No incidents logged</strong><span>Incoming SOS transmissions will appear here after the gateway receives them.</span></div> : <div className="incident-list">{incidentRows.map(i => <article className="incident" key={i.id}>
      <div className="incident-top"><div className="incident-identity"><span className="record-number">#{String(i.id).padStart(4, '0')}</span><h3>{i.title}</h3></div><span className={'priority ' + i.priority}>{nice(i.priority)}</span></div>
      <p className="incident-message">{i.message}</p>
      <div className="incident-meta"><span><Icon name="pulse" size={14}/> {nice(i.category)}</span><span><Icon name="clock" size={14}/> {fmtTime(i.created_at)}</span><span className={'state state-' + i.state}>{nice(i.state)}</span></div>
      <div className="incident-actions"><button className="link-button" onClick={() => summarize(i.id)}>GENERATE RULES SUMMARY <Icon name="chevron" size={14}/></button>{canRespond && <label className="state-control"><span className="sr-only">Update incident #{i.id} status</span><select value={i.state} onChange={e => update(i.id, e.target.value)}><option value="open">Open</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option></select></label>}</div>
      {summaries[i.id] && <div className="summary">{summaries[i.id]}</div>}
    </article>)}</div>}
  </section>;

  const radioPanel = <section className="panel radio-panel" aria-label="Meshtastic radio messages">
    <div className="panel-heading"><div><p className="eyebrow">MESHTASTIC / TWO-NODE LINK</p><h2>Radio transmissions</h2></div><span className="chip"><Icon name="radio" size={14}/> FIXED NODE</span></div>
    <div className="node-strip"><div className="node-symbol"><Icon name="radio" size={22}/></div><div><strong>RESCUE NODE</strong><code>{RESCUE_ID}</code></div><span className="node-tag">AUTHORIZED ID</span></div>
    {radioMessages.length === 0 ? <div className="empty-state compact"><Icon name="satellite" size={25}/><strong>Awaiting first transmission</strong><span>Start the Mac gateway simulator or connect the receiver over USB.</span></div> : <div className="radio-list">{radioMessages.slice(0, view === 'radio' ? 50 : 4).map(r => <article className="radio-entry" key={r.id}>
      <div className="radio-entry-top"><strong>{r.device_name || 'Rescue Node'}</strong><span>{shortTime(r.received_at)}</span></div>
      <p>{r.message}</p>
      <div className="radio-details"><span><Icon name="pin" size={14}/>{r.latitude == null || r.longitude == null ? 'GPS unavailable' : `${Number(r.latitude).toFixed(5)}, ${Number(r.longitude).toFixed(5)}`}</span><span>SNR {r.snr ?? '—'}</span>{r.incident_id != null && <span className="radio-incident">INCIDENT #{r.incident_id}</span>}</div>
    </article>)}</div>}
  </section>;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-symbol"><Icon name="pulse" size={25}/></div><div><strong>DISASTER<span>MESH</span></strong><small>EMERGENCY OPERATIONS // v0.2</small></div></div>
      <div className="nav-group"><p className="nav-heading">COMMAND CENTER</p>
        <button className={'nav-item ' + (view === 'overview' ? 'active' : '')} onClick={() => setView('overview')}><Icon name="grid"/> Overview</button>
        <button className={'nav-item ' + (view === 'incidents' ? 'active' : '')} onClick={() => setView('incidents')}><Icon name="alert"/> Incidents{auth && <span className="nav-count">{items.length}</span>}</button>
        {canRespond && <button className={'nav-item ' + (view === 'radio' ? 'active' : '')} onClick={() => setView('radio')}><Icon name="radio"/> Radio traffic<span className="nav-count">{radioMessages.length}</span></button>}
        <button className={'nav-item ' + (view === 'report' ? 'active' : '')} onClick={() => setView('report')}><Icon name="plus"/> New report</button>
      </div>
      <div className="sidebar-bottom"><div className="sidebar-node"><span className="dot"/><div><strong>LOCAL MODE</strong><small>Mac / Docker / Rules engine</small></div></div><div className="sidebar-foot">PROTOTYPE / NOT FOR LIVE EMERGENCIES</div></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div className="crumb">OPERATIONS <span>/</span> <strong>{nice(view)}</strong></div><div className="top-right"><span className="header-status"><span className="dot"/> LOCAL SYSTEM</span>{auth && <><div className="profile"><span className="avatar">{auth.username.slice(0, 1).toUpperCase()}</span><div><strong>{auth.username}</strong><small>{nice(auth.role)}</small></div></div><button className="icon-button" title="Log out" onClick={signOut}><Icon name="logout"/></button></>}</div></header>
      <main className="main-content">
        {notice && <div role="status" className="notice"><Icon name="terminal" size={18}/><span>{notice}</span><button aria-label="Dismiss message" onClick={() => setNotice('')}>×</button></div>}
        {!auth ? <div className="login-layout"><div className="hero login-hero"><div className="hero-glow"/><span className="hero-label"><span className="dot"/> NETWORK OPERATIONS TERMINAL</span><h1>When networks fail,<br/><em>the mesh holds.</em></h1><p>A secure, local-first two-node emergency communications prototype. Receive SOS messages, record GPS coordinates, and coordinate response from one command center.</p><div className="hero-tags"><span><Icon name="radio" size={15}/> MESHTASTIC</span><span><Icon name="shield" size={15}/> ROLE ACCESS</span><span><Icon name="database" size={15}/> LOCAL DATA</span></div></div><section className="panel login-panel"><p className="eyebrow">SECURE ACCESS // 01</p><h2>Operator sign in</h2><p className="muted">Authenticate to access your local DisasterMesh dashboard.</p><form onSubmit={e => {e.preventDefault();signIn(false)}}><label>USERNAME<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} placeholder="Enter username" required/></label><label>PASSWORD<input autoComplete="current-password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter password" required/></label><button disabled={busy} type="submit" className="primary-button full">{busy ? 'AUTHENTICATING…' : 'ACCESS COMMAND CENTER'} <Icon name="chevron" size={17}/></button></form><button className="text-button" disabled={busy} onClick={() => signIn(true)}>Register a new citizen account</button><div className="login-note">Use test accounts only. This system is for demonstration, not live emergency response.</div></section></div> : <>
          <div className="hero"><div className="hero-glow"/><span className="hero-label"><span className="dot"/> TWO-NODE RESPONSE NETWORK <span className="hero-divider">/</span> LOCAL PROTOTYPE</span><h1>{view === 'overview' ? <>Network overview<span className="hero-caret">_</span></> : view === 'incidents' ? <>Incident operations<span className="hero-caret">_</span></> : view === 'radio' ? <>Radio intelligence<span className="hero-caret">_</span></> : <>New incident report<span className="hero-caret">_</span></>}</h1><p>Monitor rescue transmissions, track incident priority, and coordinate a response using a local-only mesh gateway.</p><div className="hero-tags"><span><Icon name="shield" size={15}/> RULES-BASED TRIAGE</span><span><Icon name="radio" size={15}/> 2 NODES</span><span><Icon name="clock" size={15}/> {lastRefresh ? `SYNC ${shortTime(lastRefresh)}` : 'AWAITING SYNC'}</span></div></div>
          {view === 'overview' && <><div className="metrics"><div className="metric"><div className="metric-top"><span>ALL INCIDENTS</span><Icon name="pulse"/></div><strong>{String(items.length).padStart(2,'0')}</strong><small>Registered reports</small></div><div className="metric"><div className="metric-top"><span>OPEN CASES</span><Icon name="clock"/></div><strong>{String(openCount).padStart(2,'0')}</strong><small>Awaiting resolution</small></div><div className="metric metric-danger"><div className="metric-top"><span>HIGH PRIORITY</span><Icon name="alert"/></div><strong>{String(urgentCount).padStart(2,'0')}</strong><small>Unresolved urgent reports</small></div><div className="metric"><div className="metric-top"><span>RADIO PACKETS</span><Icon name="radio"/></div><strong>{canRespond ? String(radioMessages.length).padStart(2,'0') : '—'}</strong><small>{canRespond ? `${gpsCount} with GPS` : 'Responder access only'}</small></div></div><div className="content-grid"><div>{incidentsPanel}</div><div>{canRespond ? radioPanel : <section className="panel"><div className="panel-heading"><div><p className="eyebrow">CITIZEN PORTAL</p><h2>Submit a report</h2></div></div><p className="muted">Report a test incident to the response team.</p><button className="primary-button" onClick={() => setView('report')}>NEW REPORT <Icon name="plus" size={16}/></button></section>}<section className="panel system-panel"><p className="eyebrow">SYSTEM STATUS</p><h2>Infrastructure</h2><div className="system-row"><span><Icon name="terminal"/> API & RULES ENGINE</span><b><span className="dot"/> RUNNING</b></div><div className="system-row"><span><Icon name="database"/> POSTGRESQL</span><b><span className="dot"/> CONNECTED*</b></div><div className="system-row"><span><Icon name="radio"/> RADIO INPUT</span><b className="neutral">{radioMessages.length ? 'DATA RECEIVED' : 'NO DATA YET'}</b></div><small>*Based on the most recent successful API refresh; this is not a direct infrastructure health probe.</small></section></div></div></>}
          {view === 'incidents' && incidentsPanel}
          {view === 'radio' && (canRespond ? radioPanel : <section className="panel"><h2>Responder access required</h2></section>)}
          {view === 'report' && <section className="panel report-panel"><div className="panel-heading"><div><p className="eyebrow">MANUAL REPORT</p><h2>Submit incident</h2></div><span className="chip">LOCAL TEST ONLY</span></div><form onSubmit={submit}><label>INCIDENT TITLE<input placeholder="e.g. Flooded street" value={title} onChange={e => setTitle(e.target.value)} maxLength={120} minLength={3} required/></label><label>REPORT DETAILS<textarea placeholder="Describe the test incident. Do not enter real emergencies or private data." value={message} onChange={e => setMessage(e.target.value)} maxLength={3000} minLength={5} required/></label><div className="form-actions"><button className="primary-button" type="submit" disabled={busy}>{busy ? 'TRANSMITTING…' : 'SUBMIT REPORT'} <Icon name="chevron" size={17}/></button></div></form></section>}
        </>}
        <footer><span><span className="dot"/> DISASTERMESH // TWO-NODE FIELD PROTOTYPE</span><span>NOT AN EMERGENCY SERVICE · USE OFFICIAL CHANNELS FOR REAL EMERGENCIES</span></footer>
      </main>
    </div>
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
