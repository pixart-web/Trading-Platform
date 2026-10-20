import { NextRequest, NextResponse } from "next/server";
import { validSession, credentials } from "@/lib/auth";
export async function proxy(req:NextRequest){
 const p=req.nextUrl.pathname;
 if(p==="/login"||p.startsWith("/api/auth/")||p.startsWith("/_next/")||p==="/favicon.ico") return NextResponse.next();
 try{const c=await credentials();if(validSession(req.cookies.get("pa_session")?.value,c.sessionSecret))return NextResponse.next();}catch{}
 const url=req.nextUrl.clone();url.pathname="/login";url.searchParams.set("next",p);return NextResponse.redirect(url);
}
export const config={matcher:["/((?!_next/static|_next/image|favicon.ico).*)"]};
