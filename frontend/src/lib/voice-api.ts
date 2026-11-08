import { readCustomerSession } from "@/lib/customer-session";

const BASE = (import.meta.env["VITE_PNC_API_URL"] as string | undefined) ?? "";
async function voiceRequest(path: string, init?: RequestInit) {
  const token = readCustomerSession()?.token;
  if (!token) throw new Error("Sign in to use ElevenLabs voice.");
  const response = await fetch(`${BASE}/api/v1/speech/${path}`, {
    ...init, headers: { Authorization: `Bearer ${token}`, ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "The voice service could not complete this request.");
  }
  return response;
}
export async function voiceConfig() {
  if (!readCustomerSession()?.token) return { enabled: false };
  return (await voiceRequest("config")).json() as Promise<{ enabled: boolean }>;
}
export async function synthesizeVoice(text: string, assistant: "Amelia" | "Wilbur", signal: AbortSignal) {
  return (await voiceRequest("synthesize", { method: "POST", signal,
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, assistant }) })).blob();
}
export async function transcribeVoice(audio: Blob, signal: AbortSignal): Promise<string> {
  const body = new FormData(); body.append("file", audio, "question.webm");
  return ((await (await voiceRequest("transcribe", { method: "POST", body, signal })).json()) as { text: string }).text;
}
