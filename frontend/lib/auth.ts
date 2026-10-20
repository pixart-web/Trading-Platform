import crypto from "node:crypto";
import { promises as fs } from "node:fs";

const USER = process.env.PA_OPERATOR_ID ?? "operator";
const EMAIL = process.env.PA_OPERATOR_EMAIL ?? "webmaster@pixart.pt";
const PIN_HASH_FILE = process.env.PA_OPERATOR_PIN_HASH_FILE ?? "/run/secrets/operator_pin_hash";
const SESSION_SECRET_FILE = process.env.PA_SESSION_SECRET_FILE ?? "/run/secrets/session_secret";

async function secret(path: string) { return (await fs.readFile(path, "utf8")).trim(); }
export async function credentials() { return { user: USER, email: EMAIL, pinHash: await secret(PIN_HASH_FILE), sessionSecret: await secret(SESSION_SECRET_FILE) }; }
export function pinDigest(pin: string) { return crypto.createHash("sha256").update(pin, "utf8").digest("hex"); }
export function validPin(pin: string, expected: string) {
  if (!/^\\d{6}$/.test(pin)) return false;
  const a=Buffer.from(pinDigest(pin),"hex"), b=Buffer.from(expected,"hex");
  return a.length===b.length && crypto.timingSafeEqual(a,b);
}
export function sessionToken(user: string, secret: string) {
  const payload=Buffer.from(JSON.stringify({u:user,exp:Date.now()+1000*60*60*12})).toString("base64url");
  const sig=crypto.createHmac("sha256",secret).update(payload).digest("base64url");
  return payload+"."+sig;
}
export function validSession(token: string|undefined, secret: string) {
  if (!token) return false;
  const [payload,sig]=token.split("."); if(!payload||!sig) return false;
  const expected=crypto.createHmac("sha256",secret).update(payload).digest("base64url");
  if(expected.length!==sig.length||!crypto.timingSafeEqual(Buffer.from(expected),Buffer.from(sig))) return false;
  try { const p=JSON.parse(Buffer.from(payload,"base64url").toString()); return p.u===USER && Number(p.exp)>Date.now(); } catch { return false; }
}
