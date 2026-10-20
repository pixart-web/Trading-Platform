import { NextRequest, NextResponse } from "next/server";
import { credentials, validPin, sessionToken } from "@/lib/auth";
export const dynamic="force-dynamic";
let failures=new Map<string,{n:number,at:number}>();
export async function POST(req:NextRequest){
 const ip=req.headers.get("x-forwarded-for")?.split(",")[0]?.trim()??"unknown"; const now=Date.now(); const f=failures.get(ip); if(f&&f.n>=8&&now-f.at<15*60*1000)return NextResponse.json({detail:"Too many attempts. Try again later."},{status:429});
 try{const b=await req.json();const user=String(b.user??"");const pin=String(b.pin??"");const c=await credentials(); if(user!==c.user||!validPin(pin,c.pinHash)){failures.set(ip,{n:(f?.n??0)+1,at:now});return NextResponse.json({detail:"Invalid user or PIN."},{status:401});} failures.delete(ip); const res=NextResponse.json({ok:true});res.cookies.set("pa_session",sessionToken(c.user,c.sessionSecret),{httpOnly:true,secure:true,sameSite:"lax",path:"/",maxAge:60*60*12});return res;}catch{return NextResponse.json({detail:"Invalid request."},{status:400});}
}
