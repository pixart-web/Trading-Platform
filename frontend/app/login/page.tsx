"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
export default function LoginPage(){
 const router=useRouter(); const [user,setUser]=useState("operator"); const [pin,setPin]=useState(""); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
 async function submit(e:FormEvent){e.preventDefault();setBusy(true);setError("");const r=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({user,pin})});if(r.ok)router.replace(new URLSearchParams(location.search).get("next")||"/");else{const j=await r.json().catch(()=>({}));setError(j.detail??"Invalid credentials");setBusy(false);}}
 return <main className="auth-page"><form className="auth-card" onSubmit={submit}><h1>Pocket Alpha</h1><p>Operator access</p><label>User<input value={user} onChange={e=>setUser(e.target.value)} autoComplete="username"/></label><label>PIN<input value={pin} onChange={e=>setPin(e.target.value.replace(/\D/g,"").slice(0,6))} inputMode="numeric" maxLength={6} autoComplete="current-password"/></label>{error&&<div role="alert" className="auth-error">{error}</div>}<button disabled={busy||pin.length!==6}>{busy?"Signing in…":"Sign in"}</button><button type="button" className="auth-link" onClick={()=>setError("PIN recovery will be enabled when SMTP is configured.")}>Forgot PIN?</button></form></main>;
}
