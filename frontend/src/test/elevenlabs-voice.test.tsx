import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AssistantVoice } from "@/components/assistant-voice";
import { synthesizeVoice, transcribeVoice, voiceConfig } from "@/lib/voice-api";

vi.mock("@/lib/voice-api", () => ({ voiceConfig: vi.fn(), synthesizeVoice: vi.fn(), transcribeVoice: vi.fn() }));
const tracks = [{ stop: vi.fn() }];
const stream = { getTracks: () => tracks };
let captures: Capture[];
let audios: Playback[];
class Capture {
  static isTypeSupported = () => true;
  state = "inactive"; mimeType = "audio/webm";
  onstop: (() => void) | null = null;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() { captures.push(this); }
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["question"], { type: this.mimeType }) }); this.onstop?.(); }
}
class Playback {
  src = ""; onended: (() => void) | null = null; onerror: (() => void) | null = null;
  play = vi.fn(() => Promise.resolve()); pause = vi.fn();
  constructor() { audios.push(this); }
}
beforeEach(() => {
  localStorage.clear(); vi.clearAllMocks(); captures = []; audios = [];
  vi.mocked(voiceConfig).mockResolvedValue({ enabled: true });
  vi.mocked(synthesizeVoice).mockResolvedValue(new Blob(["reply"], { type: "audio/mpeg" }));
  vi.mocked(transcribeVoice).mockResolvedValue("Give me a quick review of my finances");
  vi.stubGlobal("MediaRecorder", Capture); vi.stubGlobal("Audio", Playback);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) } });
  vi.stubGlobal("URL", class extends URL {
    static override createObjectURL = vi.fn(() => "blob:voice"); static override revokeObjectURL = vi.fn();
  });
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("uses ElevenLabs for a recorded question and the spoken answer without starting on mount", async () => {
  const ask = vi.fn(); const draft = vi.fn();
  const { rerender } = render(<AssistantVoice assistant="Amelia" onQuestion={ask} onDraft={draft} />);
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Amelia voice engine" })).toHaveValue("elevenlabs"));
  expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Ask by voice" }));
  fireEvent.click(await screen.findByRole("button", { name: "Finish question" }));
  await waitFor(() => expect(ask).toHaveBeenCalledWith("Give me a quick review of my finances"));
  expect(draft).toHaveBeenCalledWith("Give me a quick review of my finances");
  expect(tracks[0]!.stop).toHaveBeenCalled();
  expect(transcribeVoice).toHaveBeenCalledWith(expect.any(Blob), expect.any(AbortSignal));
  rerender(<AssistantVoice assistant="Amelia" onQuestion={ask} onDraft={draft} reply="Your savings give you a cushion." />);
  await waitFor(() => expect(synthesizeVoice).toHaveBeenCalledWith("Your savings give you a cushion.", "Amelia", expect.any(AbortSignal)));
  await waitFor(() => expect(audios[0]?.play).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: "Stop voice" }));
  expect(audios[0]!.pause).toHaveBeenCalled();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:voice");
});

it("cancels recording without sending audio when stopped or unmounted", async () => {
  const { unmount } = render(<AssistantVoice assistant="Wilbur" onQuestion={vi.fn()} onDraft={vi.fn()} />);
  await screen.findByRole("combobox", { name: "Wilbur voice engine" });
  fireEvent.click(screen.getByRole("button", { name: "Ask by voice" }));
  await screen.findByRole("button", { name: "Finish question" });
  fireEvent.click(screen.getByRole("button", { name: "Stop voice" }));
  expect(captures[0]!.state).toBe("inactive");
  expect(transcribeVoice).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Ask by voice" }));
  await screen.findByRole("button", { name: "Finish question" });
  unmount();
  expect(captures[1]!.state).toBe("inactive");
  expect(transcribeVoice).not.toHaveBeenCalled();
});

it("reports cloud failures and lets the customer choose the browser fallback", async () => {
  vi.mocked(synthesizeVoice).mockRejectedValue(new Error("ElevenLabs voice quota reached."));
  render(<AssistantVoice assistant="Amelia" onQuestion={vi.fn()} onDraft={vi.fn()} reply="Your cash is available." />);
  await screen.findByRole("combobox", { name: "Amelia voice engine" });
  fireEvent.click(screen.getByRole("button", { name: "Read reply" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("quota reached");
  fireEvent.change(screen.getByRole("combobox", { name: "Amelia voice engine" }), { target: { value: "browser" } });
  expect(screen.getByRole("combobox", { name: "Amelia speaking voice" })).toBeInTheDocument();
});

it("does not keep a microphone acquired after the user cancels permission", async () => {
  let resolve!: (value: typeof stream) => void;
  vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValue(new Promise<typeof stream>((done) => { resolve = done; }) as unknown as Promise<MediaStream>);
  render(<AssistantVoice assistant="Wilbur" onQuestion={vi.fn()} onDraft={vi.fn()} />);
  await screen.findByRole("combobox", { name: "Wilbur voice engine" });
  fireEvent.click(screen.getByRole("button", { name: "Ask by voice" }));
  fireEvent.click(screen.getByRole("button", { name: "Stop voice" }));
  await act(async () => { resolve(stream); });
  expect(tracks[0]!.stop).toHaveBeenCalled();
  expect(captures).toHaveLength(0);
});
