import React, {useState, useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import IncidentMap, {locationLabel} from './IncidentMap';
import './style.css';

function App() {
  const [auth, setAuth] = useState(null), [username, setUsername] = useState(''), [password, setPassword] = useState('');
  const [items, setItems] = useState([]), [title, setTitle] = useState(''), [message, setMessage] = useState('');
  const [notice, setNotice] = useState(''), [summaries, setSummaries] = useState({}), [feedStatus, setFeedStatus] = useState('Connecting');
  async function api(path, options = {}) {
    const res = await fetch('/api' + path, {...options, headers: {'Content-Type': 'application/json',
      ...(auth ? {Authorization: 'Bearer ' + auth.access_token} : {}), ...(options.headers || {})}});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Check your inputs.');
      error.status = res.status;
      throw error;
    }
    return data;
  }
  function logout() {setAuth(null); setItems([]); setSummaries({}); setNotice('')}
  async function signIn(register = false) {
    try {
      setNotice('');
      if (register) {
        await api('/auth/register', {method: 'POST', body: JSON.stringify({username, password})});
        setNotice('Registered. Now log in.'); return;
      }
      setAuth(await api('/auth/login', {method: 'POST', body: JSON.stringify({username, password})}));
      setPassword('');
    } catch (e) {setNotice(e.message)}
  }
  async function refresh() {
    try {setItems(await api('/incidents')); setFeedStatus('Live — checks every 2 seconds')}
    catch (e) {setFeedStatus('Disconnected — retrying'); setNotice(e.message)}
  }
  useEffect(() => {
    if (!auth) return;
    let active = true, timer;
    const controller = new AbortController();
    async function poll() {
      try {
        const data = await api('/incidents', {signal: controller.signal});
        if (active) {setItems(data); setFeedStatus('Live — checks every 2 seconds')}
      } catch (e) {
        if (active) {
          setFeedStatus('Disconnected — retrying');
          if (e.status === 401) {logout(); setNotice('Session expired. Please log in again.'); return}
        }
      }
      if (active) timer = setTimeout(poll, 2000);
    }
    poll();
    return () => {active = false; clearTimeout(timer); controller.abort()};
  }, [auth]);
  async function submit(e) {
    e.preventDefault();
    try {
      await api('/incidents', {method: 'POST', body: JSON.stringify({title, message})});
      setTitle(''); setMessage(''); setNotice('Report submitted.'); await refresh();
    } catch (e) {setNotice(e.message)}
  }
  async function update(id, state) {
    try {await api('/incidents/' + id, {method: 'PATCH', body: JSON.stringify({state})}); await refresh()}
    catch (e) {setNotice(e.message)}
  }
  async function summarize(id) {
    try {
      const data = await api('/incidents/' + id + '/summary');
      setSummaries(s => ({...s, [id]: data.summary + ' (' + data.source + ')'}));
    } catch (e) {setNotice(e.message)}
  }
  return <main>
    <header><div><h1>DisasterMesh</h1><p>Local LoRa emergency incident dashboard</p></div>{auth && <button onClick={logout}>Log out</button>}</header>
    {notice && <div className="notice" role="status">{notice}</div>}
    {!auth ? <section className="panel"><h2>Log in or register</h2>
      <form onSubmit={e => {e.preventDefault(); signIn()}}>
        <label>Username<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required/></label>
        <label>Password<input autoComplete="current-password" value={password} type="password" onChange={e => setPassword(e.target.value)} required/></label>
        <div className="actions"><button type="submit">Log in</button><button type="button" className="secondary" onClick={() => signIn(true)}>Register citizen</button></div>
      </form><small>Passwords need 12+ characters. A local administrator grants responder access. Responders see gateway SOS incidents.</small>
    </section> : <>
      <p className="who">Signed in as <b>{auth.username}</b> — role: <b>{auth.role}</b></p>
      <p className="feed-status" role="status">{feedStatus}</p>
      <section className="panel"><h2>Report incident</h2><form onSubmit={submit}>
        <label>Incident title<input value={title} onChange={e => setTitle(e.target.value)} maxLength={120} required minLength={3}/></label>
        <label>Description<textarea value={message} onChange={e => setMessage(e.target.value)} placeholder="Describe the incident (synthetic tests only)" maxLength={3000} required minLength={5}/></label>
        <button type="submit">Submit report</button>
      </form></section>
      <IncidentMap items={items}/>
      <section className="panel"><div className="line"><h2>Incident reports</h2><button className="secondary" onClick={refresh}>Refresh</button></div>
        {items.length === 0 ? <p>No reports yet.</p> : items.map(i => <article key={i.id} data-testid="incident">
          <div className="line"><h3>#{i.id} — {i.title}</h3><strong className={'pill ' + i.priority}>{i.priority.toUpperCase()}</strong></div>
          <p>{i.message}</p><p className="muted">{i.category} • {i.state} • Stored {new Date(i.created_at).toLocaleString()}</p>
          {i.gateway && <><p className="muted">Node {i.gateway.node_id} • Packet {i.gateway.packet_id} • SOS observed {new Date(i.gateway.event_timestamp).toLocaleString()}</p>
            <p>{locationLabel(i.gateway)}{i.gateway.gps_status === 'valid' && `: ${i.gateway.latitude.toFixed(6)}, ${i.gateway.longitude.toFixed(6)}`}
              {i.gateway.position_timestamp && ` • Fix ${new Date(i.gateway.position_timestamp).toLocaleString()}`}</p></>}
          <div className="actions"><button className="secondary" onClick={() => summarize(i.id)}>Summarize</button>
            {auth.role !== 'citizen' && <label>Status for incident #{i.id}<select value={i.state} onChange={e => update(i.id, e.target.value)}>
              <option value="open">Open</option><option value="in_progress">Acknowledged / in progress</option><option value="resolved">Resolved</option>
            </select></label>}
          </div>{summaries[i.id] && <p className="summary">{summaries[i.id]}</p>}
        </article>)}
      </section>
    </>}
    <footer>Prototype only. Public Primary channel: synthetic test messages only. Not a live emergency response service.</footer>
  </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
