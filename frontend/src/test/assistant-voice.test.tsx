import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantVoice } from "@/components/assistant-voice";
import { preferredVoice, spokenChunks, wakeQuestion, type BrowserRecognition, type RecognitionResultEvent } from "@/lib/assistant-speech";

const natural = { name: "Microsoft Aria Online (Natural)", voiceURI: "natural", lang: "en-US", default: false } as SpeechSynthesisVoice;
const ordinary = { name: "System voice", voiceURI: "system", lang: "en-US", default: true } as SpeechSynthesisVoice;
let instances: MockRecognition[];
class MockRecognition implements BrowserRecognition {
  lang = ""; continuous = false; interimResults = false;
  onresult: ((event: RecognitionResultEvent) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null; onstart: (() => void) | null = null;
  start = vi.fn(() => this.onstart?.()); abort = vi.fn();
  constructor() { instances.push(this); }
  say(text: string) { this.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: text } }] }); }
}
const synth = { getVoices: vi.fn(() => [ordinary, natural]), speak: vi.fn(), cancel: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() };
class MockUtterance {
  text: string; voice = null; lang = ""; rate = 1; pitch = 1;
  onend: (() => void) | null = null; onerror: (() => void) | null = null;
  constructor(text: string) { this.text = text; }
}
beforeEach(() => {
  instances = []; localStorage.clear(); vi.clearAllMocks();
  vi.stubGlobal("SpeechRecognition", MockRecognition);
  vi.stubGlobal("speechSynthesis", synth);
  vi.stubGlobal("SpeechSynthesisUtterance", MockUtterance);
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("Assistant voice conversation", () => {
  it("prefers a natural voice and never starts the microphone on mount", () => {
    expect(preferredVoice([ordinary, natural])).toBe(natural);
    render(<AssistantVoice assistant="Wilbur" onQuestion={vi.fn()} onDraft={vi.fn()} />);
    expect(instances).toHaveLength(0);
    expect(screen.getByRole("combobox", { name: "Wilbur speaking voice" })).toHaveValue("natural");
  });

  it("submits one spoken question and speaks the returned answer", async () => {
    const ask = vi.fn(); const draft = vi.fn();
    const { rerender } = render(<AssistantVoice assistant="Wilbur" onQuestion={ask} onDraft={draft} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask by voice" }));
    act(() => instances.at(-1)!.say("What does Sharpe ratio mean?"));
    expect(ask).toHaveBeenCalledOnce(); expect(draft).toHaveBeenCalledWith("What does Sharpe ratio mean?");
    rerender(<AssistantVoice assistant="Wilbur" onQuestion={ask} onDraft={draft} reply="It compares excess return with volatility." />);
    await waitFor(() => expect(synth.speak).toHaveBeenCalled());
    expect((synth.speak.mock.calls[0]![0] as MockUtterance).text).toBe("It compares excess return with volatility.");
    expect((synth.speak.mock.calls[0]![0] as MockUtterance).voice).toBe(natural);
    fireEvent.click(screen.getByRole("button", { name: "Stop voice" }));
    expect(synth.cancel).toHaveBeenCalled();
    expect(screen.getByRole("checkbox", { name: "Speak replies" })).not.toBeChecked();
  });

  it("ignores conversation until the chosen wake phrase is spoken", () => {
    const ask = vi.fn();
    render(<AssistantVoice assistant="Amelia" onQuestion={ask} onDraft={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Enable Hey Amelia" }));
    act(() => instances.at(-1)!.say("How is the weather?"));
    expect(ask).not.toHaveBeenCalled();
    act(() => instances.at(-1)!.say("Hey Amelia, explain my savings"));
    expect(ask).toHaveBeenCalledExactlyOnceWith("explain my savings");
  });

  it("handles a wake phrase followed by the question in a second sentence", () => {
    const ask = vi.fn();
    render(<AssistantVoice assistant="Wilbur" onQuestion={ask} onDraft={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Enable Hey Wilbur" }));
    act(() => instances.at(-1)!.say("Hey Wilbur"));
    act(() => instances.at(-1)!.say("Explain diversification"));
    expect(ask).toHaveBeenCalledExactlyOnceWith("Explain diversification");
  });

  it("stops recognition when busy, hidden or unmounted and reports denied permissions", () => {
    const { rerender, unmount } = render(<AssistantVoice assistant="Wilbur" onQuestion={vi.fn()} onDraft={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask by voice" }));
    const first = instances.at(-1)!;
    rerender(<AssistantVoice assistant="Wilbur" onQuestion={vi.fn()} onDraft={vi.fn()} busy />);
    expect(first.abort).toHaveBeenCalled();
    rerender(<AssistantVoice assistant="Wilbur" onQuestion={vi.fn()} onDraft={vi.fn()} />);
    act(() => instances.at(-1)!.onerror?.({ error: "not-allowed" }));
    expect(screen.getByRole("alert")).toHaveTextContent("permission was denied");
    fireEvent.click(screen.getByRole("button", { name: "Enable Hey Wilbur" }));
    const last = instances.at(-1)!;
    act(() => { Object.defineProperty(document, "hidden", { configurable: true, value: true }); document.dispatchEvent(new Event("visibilitychange")); });
    expect(last.abort).toHaveBeenCalled();
    unmount(); expect(last.onresult).toBeNull();
  });

  it("chunks long replies without repeating text and recognizes only the correct wake name", () => {
    const text = "This is one short sentence. ".repeat(50).trim();
    const chunks = spokenChunks(text);
    expect(chunks.every((part) => part.length <= 240)).toBe(true);
    expect(chunks.join(" ")).toBe(text);
    expect(wakeQuestion("Hey Wilbur, define beta", "Wilbur")).toBe("define beta");
    expect(wakeQuestion("Hey Amelia, define beta", "Wilbur")).toBeNull();
  });
});
