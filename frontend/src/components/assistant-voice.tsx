import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { preferredVoice, recognitionConstructor, spokenChunks, wakeQuestion, type BrowserRecognition } from "@/lib/assistant-speech";
import { synthesizeVoice, transcribeVoice, voiceConfig } from "@/lib/voice-api";

const FOCUS_EVENT = "finpilot:voice-focus";
const PREFS = "finpilot.voice.preferences";

export function AssistantVoice({ assistant, onQuestion, onDraft, reply = "", busy = false, contextKey = "" }: {
  assistant: "Wilbur" | "Amelia"; onQuestion: (text: string) => void; onDraft: (text: string) => void;
  reply?: string; busy?: boolean; contextKey?: string;
}) {
  const id = useId();
  const [micReady, setMicReady] = useState(false);
  const [nativeSpeechReady, setNativeSpeechReady] = useState(false);
  const [cloudEnabled, setCloudEnabled] = useState(false);
  const [provider, setProvider] = useState<"browser" | "elevenlabs">("browser");
  const [recording, setRecording] = useState<"off" | "starting" | "recording" | "transcribing">("off");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceURI, setVoiceURI] = useState("");
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [mode, setMode] = useState<"off" | "once" | "wake">("off");
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [armed, setArmed] = useState(false);
  const [restart, setRestart] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const currentUtterance = useRef<SpeechSynthesisUtterance | null>(null);
  const activeRecognition = useRef<BrowserRecognition | null>(null);
  const generation = useRef(0);
  const latestReply = useRef("");
  const playback = useRef<HTMLAudioElement | null>(null);
  const audioURL = useRef<string | null>(null);
  const remoteAbort = useRef<AbortController | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const microphone = useRef<MediaStream | null>(null);
  const recordGeneration = useRef(0);
  const recordTimeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const speechReady = (provider === "elevenlabs" && cloudEnabled) || nativeSpeechReady;
  const callbacks = useRef({ onQuestion, onDraft });
  callbacks.current = { onQuestion, onDraft };
  const voice = voices.find((item) => item.voiceURI === voiceURI) ?? preferredVoice(voices);

  const stopSpeech = () => {
    generation.current += 1;
    remoteAbort.current?.abort(); remoteAbort.current = null;
    if (playback.current) { playback.current.pause(); playback.current.src = ""; playback.current = null; }
    if (audioURL.current) { URL.revokeObjectURL(audioURL.current); audioURL.current = null; }
    if (currentUtterance.current) window.speechSynthesis?.cancel();
    currentUtterance.current = null;
    setSpeaking(false);
  };
  const stopRecording = () => {
    recordGeneration.current += 1; clearTimeout(recordTimeout.current);
    if (recorder.current) {
      recorder.current.onstop = null; recorder.current.ondataavailable = null;
      if (recorder.current.state !== "inactive") recorder.current.stop();
      recorder.current = null;
    }
    microphone.current?.getTracks().forEach((track) => track.stop()); microphone.current = null;
    setRecording("off");
  };
  const stop = () => { setMode("off"); setArmed(false); stopRecording(); stopSpeech(); };
  const save = (uri: string, enabled: boolean) => {
    try { localStorage.setItem(PREFS, JSON.stringify({ voiceURI: uri, autoSpeak: enabled })); } catch { /* Storage is optional. */ }
  };
  const speak = (text: string) => {
    if (!speechReady || !text.trim() || document.hidden) return;
    window.dispatchEvent(new CustomEvent(FOCUS_EVENT, { detail: id }));
    if (activeRecognition.current) {
      activeRecognition.current.onend = null; activeRecognition.current.onerror = null;
      activeRecognition.current.abort();
    }
    stopSpeech();
    const token = ++generation.current;
    const chunks = spokenChunks(text);
    setError(null);
    setSpeaking(true);
    if (provider === "elevenlabs") {
      const controller = new AbortController(); remoteAbort.current = controller;
      void synthesizeVoice(chunks.join(" "), assistant, controller.signal).then(async (blob) => {
        if (token !== generation.current || controller.signal.aborted) return;
        const url = URL.createObjectURL(blob); audioURL.current = url;
        const audio = new Audio(url); playback.current = audio;
        const finish = () => {
          if (token !== generation.current) return;
          URL.revokeObjectURL(url); audioURL.current = null; playback.current = null; setSpeaking(false);
        };
        audio.onended = finish;
        audio.onerror = () => { if (token === generation.current) { finish(); setError("Audio playback failed. Press Read reply to try again."); } };
        try { await audio.play(); } catch {
          if (token === generation.current) { finish(); setError("Press Read reply to allow audio playback in your browser."); }
        }
      }).catch((reason: unknown) => {
        if (controller.signal.aborted || token !== generation.current) return;
        setSpeaking(false); setError(reason instanceof Error ? reason.message : "ElevenLabs voice failed. Try a browser voice.");
      });
      return;
    }
    const next = (index: number) => {
      if (token !== generation.current) return;
      if (index >= chunks.length) { currentUtterance.current = null; setSpeaking(false); return; }
      const utterance = new SpeechSynthesisUtterance(chunks[index]);
      if (voice) utterance.voice = voice;
      utterance.lang = voice?.lang ?? "en-US"; utterance.rate = 0.97; utterance.pitch = 1;
      utterance.onend = () => next(index + 1);
      utterance.onerror = () => {
        if (token !== generation.current) return;
        currentUtterance.current = null; setSpeaking(false);
        setError("Audio playback stopped. Press Read reply to try again.");
      };
      currentUtterance.current = utterance;
      window.speechSynthesis.speak(utterance);
    };
    next(0);
  };

  useEffect(() => {
    setMicReady(Boolean(recognitionConstructor()));
    setNativeSpeechReady(typeof window.speechSynthesis?.speak === "function" && typeof window.SpeechSynthesisUtterance === "function");
    let mounted = true;
    void voiceConfig().then((config) => {
      if (mounted && config.enabled) { setCloudEnabled(true); setProvider("elevenlabs"); }
    }).catch(() => { /* Browser voice remains available. */ });
    const update = () => setVoices(window.speechSynthesis?.getVoices() ?? []);
    update(); window.speechSynthesis?.addEventListener("voiceschanged", update);
    try {
      const saved = JSON.parse(localStorage.getItem(PREFS) ?? "{}");
      if (typeof saved.voiceURI === "string") setVoiceURI(saved.voiceURI);
      if (saved.autoSpeak === true) setAutoSpeak(true);
    } catch { /* Ignore unavailable preferences. */ }
    const focus = (event: Event) => { if ((event as CustomEvent).detail !== id) { stop(); setAutoSpeak(false); } };
    const hidden = () => { if (document.hidden) { stop(); setAutoSpeak(false); } };
    window.addEventListener(FOCUS_EVENT, focus); document.addEventListener("visibilitychange", hidden);
    return () => {
      mounted = false; recordGeneration.current += 1; clearTimeout(recordTimeout.current);
      if (recorder.current) { recorder.current.onstop = null; if (recorder.current.state !== "inactive") recorder.current.stop(); }
      microphone.current?.getTracks().forEach((track) => track.stop());
      remoteAbort.current?.abort(); playback.current?.pause();
      if (audioURL.current) URL.revokeObjectURL(audioURL.current);
      generation.current += 1;
      if (currentUtterance.current) window.speechSynthesis?.cancel();
      window.speechSynthesis?.removeEventListener("voiceschanged", update);
      window.removeEventListener(FOCUS_EVENT, focus); document.removeEventListener("visibilitychange", hidden);
    };
  }, [id]);

  useEffect(() => { stop(); latestReply.current = reply; }, [contextKey]);
  useEffect(() => {
    if (busy) stopSpeech();
  }, [busy]);
  useEffect(() => {
    if (!reply || !autoSpeak || busy || reply === latestReply.current || !speechReady) return;
    latestReply.current = reply;
    speak(reply);
  }, [reply, autoSpeak, busy, speechReady]);

  useEffect(() => {
    const Ctor = recognitionConstructor();
    if (mode === "off" || busy || speaking || !Ctor || document.hidden) { setListening(false); return; }
    const recognition = new Ctor();
    activeRecognition.current = recognition;
    let delivered = false;
    let ended = false;
    let failed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    recognition.lang = voice?.lang ?? "en-US";
    recognition.continuous = mode === "wake"; recognition.interimResults = false;
    recognition.onstart = () => setListening(true);
    recognition.onresult = (event) => {
      if (delivered || ended) return;
      for (let index = event.resultIndex; index < event.results.length; index++) {
        const result = event.results[index];
        if (!result?.isFinal) continue;
        const transcript = result[0]?.transcript.trim() ?? "";
        if (!transcript) continue;
        let question = transcript;
        if (mode === "wake") {
          const wake = wakeQuestion(transcript, assistant);
          if (wake === "") { setArmed(true); return; }
          if (wake !== null) question = wake;
          else if (!armed) continue;
        }
        delivered = true;
        setArmed(false);
        if (mode === "once") setMode("off");
        callbacks.current.onDraft(question);
        callbacks.current.onQuestion(question);
        break;
      }
    };
    recognition.onerror = (event) => {
      if (ended) return;
      if (event.error === "no-speech" && mode === "wake") return;
      failed = true; setMode("off"); setArmed(false); setListening(false);
      setError(event.error === "not-allowed" || event.error === "service-not-allowed"
        ? "Microphone permission was denied. Allow it in your browser to use voice."
        : "Speech recognition could not continue. Try again or type your question.");
    };
    recognition.onend = () => {
      if (ended) return;
      setListening(false);
      if (mode === "wake" && !failed) retry = setTimeout(() => setRestart((value) => value + 1), 750);
      else setMode("off");
    };
    try { recognition.start(); } catch { setError("The microphone could not start. Type your question or try again."); setMode("off"); }
    return () => {
      ended = true; clearTimeout(retry); recognition.onend = null; recognition.onresult = null; recognition.onerror = null;
      recognition.abort(); activeRecognition.current = null; setListening(false);
    };
  }, [mode, busy, speaking, restart, armed, voice?.lang, assistant]);

  const begin = (next: "once" | "wake") => {
    window.dispatchEvent(new CustomEvent(FOCUS_EVENT, { detail: id }));
    stopRecording(); stopSpeech(); setError(null); setArmed(false); setAutoSpeak(true); save(voiceURI, true); setMode(next);
  };
  const recordQuestion = async () => {
    window.dispatchEvent(new CustomEvent(FOCUS_EVENT, { detail: id }));
    stop(); setError(null); setAutoSpeak(true); save(voiceURI, true);
    setRecording("starting");
    const token = ++recordGeneration.current;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (token !== recordGeneration.current) { stream.getTracks().forEach((track) => track.stop()); return; }
      microphone.current = stream;
      const mime = ["audio/webm", "audio/mp4", "audio/ogg"].find((item) => MediaRecorder.isTypeSupported(item));
      const capture = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      recorder.current = capture;
      const chunks: BlobPart[] = [];
      capture.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      capture.onstop = () => {
        clearTimeout(recordTimeout.current);
        stream.getTracks().forEach((track) => track.stop()); microphone.current = null; recorder.current = null;
        if (token !== recordGeneration.current) return;
        setRecording("transcribing");
        const controller = new AbortController(); remoteAbort.current = controller;
        void transcribeVoice(new Blob(chunks, { type: capture.mimeType }), controller.signal).then((text) => {
          if (controller.signal.aborted || token !== recordGeneration.current) return;
          setRecording("off"); callbacks.current.onDraft(text); callbacks.current.onQuestion(text);
        }).catch((reason: unknown) => {
          if (controller.signal.aborted || token !== recordGeneration.current) return;
          setRecording("off"); setError(reason instanceof Error ? reason.message : "Could not transcribe your question.");
        });
      };
      capture.onerror = () => { stopRecording(); setError("Microphone recording failed. Try again or type your question."); };
      capture.start(); setRecording("recording");
      recordTimeout.current = setTimeout(() => { if (capture.state === "recording") capture.stop(); }, 60000);
    } catch {
      if (token !== recordGeneration.current) return;
      stopRecording(); setError("Microphone access failed. Allow microphone permission or type your question.");
    }
  };
  const recordReady = typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== "undefined";
  const status = recording === "starting" ? "Requesting microphone access..." : recording === "recording"
    ? "Listening. Press Finish question when you are done." : recording === "transcribing" ? "Transcribing your question..."
    : speaking ? `${assistant} is speaking.` : busy ? `${assistant} is thinking.`
    : armed ? "Go ahead. What would you like to ask?" : listening
      ? mode === "wake" ? `Listening for Hey ${assistant}.` : "Listening. Your question sends when you finish."
      : mode === "wake" ? "Starting wake-phrase listening..." : "Voice is off.";
  return <section aria-label={`${assistant} voice controls`} className="space-y-3 rounded-xl border border-border p-3 text-xs">
    <div className="flex flex-wrap gap-2">
      <Button type="button" size="sm" variant="outline" disabled={busy || recording === "starting" || recording === "transcribing" || (provider === "elevenlabs" ? !recordReady : !micReady)}
        onClick={() => recording === "recording" ? recorder.current?.stop() : provider === "elevenlabs" ? void recordQuestion() : begin("once")}>
        {recording === "recording" ? "Finish question" : "Ask by voice"}</Button>
      <Button type="button" size="sm" variant={mode === "wake" ? "default" : "outline"} disabled={!micReady || busy || recording !== "off"}
        aria-pressed={mode === "wake"} onClick={() => mode === "wake" ? stop() : begin("wake")}>
        {mode === "wake" ? "Disable wake phrase" : `Enable Hey ${assistant}`}
      </Button>
      <Button type="button" size="sm" variant="outline" disabled={!reply || !speechReady || busy || recording !== "off"} onClick={() => speak(reply)}>Read reply</Button>
      <Button type="button" size="sm" variant="outline" disabled={mode === "off" && !speaking && !autoSpeak && recording === "off"}
        onClick={() => { stop(); setAutoSpeak(false); save(voiceURI, false); }}>Stop voice</Button>
    </div>
    <div className="flex flex-wrap items-center gap-3">
      {cloudEnabled && <label>Voice engine<select aria-label={`${assistant} voice engine`} value={provider} className="ml-2 rounded border bg-background p-1"
        onChange={(event) => { stop(); setProvider(event.target.value as "browser" | "elevenlabs"); }}>
        <option value="elevenlabs">ElevenLabs — natural voice</option><option value="browser">Browser voice</option>
      </select></label>}
      <label className="flex items-center gap-2"><input type="checkbox" checked={autoSpeak} disabled={!speechReady}
        onChange={(event) => { setAutoSpeak(event.target.checked); save(voiceURI, event.target.checked); if (!event.target.checked) stopSpeech(); }} />Speak replies</label>
      {provider === "browser" && <label className="min-w-0 flex-1">Voice
        <select aria-label={`${assistant} speaking voice`} className="mt-1 w-full rounded-md border border-border bg-background p-1"
          value={voice?.voiceURI ?? ""} disabled={!speechReady || voices.length === 0}
          onChange={(event) => { stopSpeech(); setVoiceURI(event.target.value); save(event.target.value, autoSpeak); }}>
          {voices.length === 0 && <option value="">Browser default</option>}
          {voices.map((item) => <option key={item.voiceURI} value={item.voiceURI}>{item.name} ({item.lang})</option>)}
        </select>
      </label>}
      <Button type="button" size="sm" variant="ghost" disabled={!speechReady || recording !== "off"} onClick={() => speak(`Hi, I'm ${assistant}. What would you like to understand?`)}>Try voice</Button>
    </div>
    <p role="status" aria-live="polite">{status}</p>
    {!micReady && !(provider === "elevenlabs" && recordReady) && <p>Microphone input is unavailable in this browser. You can still type.</p>}
    {!speechReady && <p>Spoken replies are unavailable in this browser.</p>}
    <p className="text-muted-foreground">{provider === "elevenlabs"
      ? "ElevenLabs transcribes recorded questions and speaks replies in a natural voice. Audio and reply text are sent to ElevenLabs when you use voice. Wake phrases use your browser's recognition."
      : "Choose a Natural or Neural voice when available. Your browser may use an online speech service."} The microphone starts only after you enable it.</p>
    {error && <p role="alert" className="text-destructive">{error}</p>}
  </section>;
}
