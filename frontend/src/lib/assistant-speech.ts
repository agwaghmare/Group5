export interface RecognitionResultEvent {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; [index: number]: { transcript: string } }>;
}
export interface BrowserRecognition {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  start(): void; abort(): void;
}
export function recognitionConstructor(): (new () => BrowserRecognition) | undefined {
  if (typeof window === "undefined") return undefined;
  const host = window as unknown as { SpeechRecognition?: new () => BrowserRecognition; webkitSpeechRecognition?: new () => BrowserRecognition };
  return host.SpeechRecognition ?? host.webkitSpeechRecognition;
}
export function preferredVoice(voices: SpeechSynthesisVoice[]) {
  const score = (voice: SpeechSynthesisVoice) => (/^en/i.test(voice.lang) ? 100 : 0)
    + (/natural|neural|online/i.test(voice.name) ? 40 : 0) + (/google/i.test(voice.name) ? 20 : 0)
    + (/en-US/i.test(voice.lang) ? 5 : 0) + (voice.default ? 1 : 0);
  return [...voices].sort((a, b) => score(b) - score(a))[0];
}
export function spokenChunks(text: string): string[] {
  const plain = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/https?:\/\/\S+/g, "")
    .replace(/[`*#]/g, "").replace(/\s+/g, " ").trim();
  const chunks: string[] = [];
  let remaining = plain;
  while (remaining.length > 240) {
    const candidate = remaining.slice(0, 240);
    const sentence = Math.max(candidate.lastIndexOf(". "), candidate.lastIndexOf("? "), candidate.lastIndexOf("! "));
    const space = candidate.lastIndexOf(" ");
    const end = sentence > 60 ? sentence + 1 : space > 0 ? space : 240;
    chunks.push(remaining.slice(0, end)); remaining = remaining.slice(end).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}
export function wakeQuestion(text: string, assistant: string): string | null {
  const match = text.trim().match(new RegExp(`^(?:hey|hi|okay|ok)[,\\s]+${assistant}\\b[,\\s:.-]*(.*)$`, "i"));
  return match ? match[1]!.trim() : null;
}
