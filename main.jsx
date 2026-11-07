import React, {useState, useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

function App(){
 const [auth,setAuth]=useState(null), [username,setUsername]=useState(''),[password,setPassword]=useState(''),[items,setItems]=useState([]),[title,setTitle]=useState(''),[message,setMessage]=useState(''),[notice,setNotice]=useState(''),[summaries,setSummaries]=useState({});
 async function api(path,options={}){
  const res=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',...(auth?{Authorization:'Bearer '+auth.access_token}:{}),...(options.headers||{})}});
  const data=await res.json().catch(()=>({}));if(!res.ok) throw new Error(typeof data.detail==='string'?data.detail:'Request failed');return data;
 }
 async function signIn(register=false){try{setNotice('');if(register){await api('/auth/register',{method:'POST',body:JSON.stringify({username,password})});setNotice('Registered. Now log in.');return;}
 const a=await api('/auth/login',{method:'POST',body:JSON.stringify({username,password})});setAuth(a);setPassword('');}catch(e){setNotice(e.message)}}
 async function refresh(){try{setItems(await api('/incidents'))}catch(e){setNotice(e.message)}}
 useEffect(()=>{if(auth)refresh()},[auth]);
 async function submit(e){e.preventDefault();try{await api('/incidents',{method:'POST',body:JSON.stringify({title,message})});setTitle('');setMessage('');setNotice('Report submitted.');await refresh()}catch(e){setNotice(e.message)}}
 async function update(id,state){try{await api('/incidents/'+id,{method:'PATCH',body:JSON.stringify({state})});await refresh()}catch(e){setNotice(e.message)}}
 async function summarize(id){try{let data=await api('/incidents/'+id+'/summary');setSummaries(s=>({...s,[id]:data.summary+' ('+data.source+')'}))}catch(e){setNotice(e.message)}}
 return <main><header><div><h1>DisasterMesh</h1><p>Local emergency incident dashboard — software prototype</p></div>{auth&&<button onClick={()=>{setAuth(null);setItems([]);setSummaries({})}}>Log out</button>}</header>
 {notice&&<div className="notice">{notice}</div>}
 {!auth?<section className="panel"><h2>Log in or register</h2><input value={username} onChange={e=>setUsername(e.target.value)} placeholder="Username (letters, numbers, _ or -)"/><input value={password} type="password" onChange={e=>setPassword(e.target.value)} placeholder="Password (12+ characters)"/><div className="actions"><button onClick={()=>signIn(false)}>Log in</button><button className="secondary" onClick={()=>signIn(true)}>Register citizen</button></div><small>For testing, create separate citizen and responder accounts. Only an administrator can grant responder access.</small></section>:<><p className="who">Signed in as <b>{auth.username}</b> — role: <b>{auth.role}</b></p><section className="panel"><h2>Report incident</h2><form onSubmit={submit}><input value={title} onChange={e=>setTitle(e.target.value)} placeholder="Incident title" maxLength={120} required minLength={3}/><textarea value={message} onChange={e=>setMessage(e.target.value)} placeholder="Describe the incident (no real emergencies)" maxLength={3000} required minLength={5}/><button type="submit">Submit report</button></form></section><section className="panel"><div className="line"><h2>Incident reports</h2><button className="secondary" onClick={refresh}>Refresh</button></div>{items.length===0?<p>No reports yet.</p>:items.map(i=><article key={i.id}><div className="line"><h3>#{i.id} — {i.title}</h3><strong className={'pill '+i.priority}>{i.priority.toUpperCase()}</strong></div><p>{i.message}</p><p className="muted">{i.category} • {i.state} • {new Date(i.created_at).toLocaleString()}</p><div className="actions"><button className="secondary" onClick={()=>summarize(i.id)}>Summarize</button>{auth.role!=='citizen'&&<select value={i.state} onChange={e=>update(i.id,e.target.value)}><option value="open">Open</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option></select>}</div>{summaries[i.id]&&<p className="summary">{summaries[i.id]}</p>}</article>)}</section></>}
 <footer>Prototype only. Not a live emergency response service. Call local emergency services for real emergencies.</footer></main>
}
createRoot(document.getElementById('root')).render(<App/>);
