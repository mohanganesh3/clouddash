"use client";

import { useState, useRef, KeyboardEvent } from "react";
import { ArrowUp, Square } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  onSend: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
}

export function MessageInput({ onSend, onStop, isStreaming }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const msg = value.trim();
    if (!msg || isStreaming) return;
    setValue("");
    onSend(msg);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  };

  const hasValue = value.trim().length > 0;
  const charCount = value.length;

  return (
    <div
      className="px-4 pb-4 pt-2"
      style={{ background: "#0f1117" }}
    >
      <div
        className="relative rounded-xl"
        style={{
          background: "#1a1d27",
          border: `1px solid ${isStreaming ? "rgba(13,148,136,0.35)" : hasValue ? "rgba(255,255,255,0.10)" : "rgba(255,255,255,0.06)"}`,
          boxShadow: isStreaming ? "0 0 0 2px rgba(13,148,136,0.15)" : hasValue ? "0 4px 20px rgba(0,0,0,0.3)" : "none",
          transition: "border-color 0.2s ease, box-shadow 0.2s ease",
        }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => { setValue(e.target.value); handleInput(); }}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about CloudDash…"
          rows={1}
          disabled={isStreaming}
          className="w-full resize-none text-sm leading-relaxed pr-12 pl-4 pt-3 pb-3 bg-transparent placeholder:text-slate-500"
          style={{
            color: "#f0f0f5",
            outline: "none",
            fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          }}
        />

        {/* Character count — shows when typing */}
        {charCount > 100 && (
          <span
            className="absolute bottom-2.5 right-12 text-[10px]"
            style={{ color: charCount > 3500 ? "#ef4444" : "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}
          >
            {charCount}/4000
          </span>
        )}

        {/* Send / Stop button */}
        <button
          type="button"
          onClick={isStreaming ? onStop : submit}
          disabled={!isStreaming && !hasValue}
          className="absolute right-2 bottom-2 h-7 w-7 rounded-lg flex items-center justify-center active:scale-90"
          style={{
            background: isStreaming ? "#ef4444" : hasValue ? "#0d9488" : "#2a2e3d",
            boxShadow: isStreaming ? "0 0 12px rgba(239,68,68,0.4)" : hasValue ? "0 0 12px rgba(13,148,136,0.4)" : "none",
            transition: "background 0.15s ease, box-shadow 0.15s ease",
          }}
          aria-label={isStreaming ? "Stop" : "Send"}
        >
          {isStreaming ? (
            <Square className="h-3 w-3 text-white fill-white" />
          ) : (
            <ArrowUp className="h-3 w-3 text-white" />
          )}
        </button>
      </div>

      {/* Hint text */}
      <p
        className="text-center text-[10px] mt-2"
        style={{ color: "#4b5563", fontFamily: "'JetBrains Mono', monospace" }}
      >
        {isStreaming ? "Processing… press ■ to stop" : "↵ send · ⇧↵ newline"}
      </p>
    </div>
  );
}
