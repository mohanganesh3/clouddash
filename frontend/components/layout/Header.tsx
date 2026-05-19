"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Cloud, Wifi, WifiOff } from "lucide-react";
import { useConversationStore } from "@/store/conversation";
import { AgentBadge } from "@/components/agents/AgentBadge";
import { BASE_URL } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Header() {
  const { currentAgent, activeAgents, pendingInterrupt } = useConversationStore();
  const [online, setOnline] = useState(true);
  const [statusText, setStatusText] = useState("All systems operational");

  useEffect(() => {
    const ping = async () => {
      try {
        const res = await fetch(`${BASE_URL}/api/health`, { cache: "no-store" });
        const ok = res.ok;
        setOnline(ok);
        setStatusText(ok ? "All systems operational" : "Service degraded");
      } catch {
        setOnline(false);
        setStatusText("Connection lost");
      }
    };
    ping();
    const id = setInterval(ping, 10000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="flex items-center justify-between px-5 py-3">
      {/* Logo */}
      <div className="flex items-center gap-2.5">
        <div
          className="h-8 w-8 rounded-lg flex items-center justify-center"
          style={{ background: "rgba(13,148,136,0.12)", border: "1px solid rgba(13,148,136,0.3)" }}
        >
          <Cloud className="h-4 w-4" style={{ color: "#14b8a6" }} />
        </div>
        <div>
          <h1 className="text-sm font-semibold text-white tracking-tight">
            CloudDash
          </h1>
          <div className="flex items-center gap-1.5 text-[10px] font-mono" style={{ color: "#6b7280" }}>
            <span className="relative flex h-1.5 w-1.5">
              <span className={cn("animate-ping absolute inline-flex h-full w-full rounded-full opacity-50", online ? "bg-emerald-400" : "bg-red-400")} />
              <span className={cn("relative inline-flex rounded-full h-full w-full", online ? "bg-emerald-400" : "bg-red-400")} />
            </span>
            <span className={online ? "text-emerald-400/80" : "text-red-400/80"}>{statusText}</span>
          </div>
        </div>
      </div>

      {/* Center: Active agent */}
      <div className="flex items-center gap-3">
        <AnimatePresence mode="popLayout">
          {currentAgent && (
            <motion.div
              key={currentAgent}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
            >
              <AgentBadge agent={currentAgent} size="sm" pulse={online} />
            </motion.div>
          )}
        </AnimatePresence>

        {pendingInterrupt && (
          <div className="flex items-center gap-2 text-[10px] font-mono rounded-md px-2.5 py-1" style={{ background: "rgba(245,158,11,0.08)", color: "#d97706", border: "1px solid rgba(217,119,6,0.15)" }}>
            <span className="animate-pulse">
              1 interrupt pending
            </span>
          </div>
        )}
      </div>

      {/* Right: Active agents + connection */}
      <div className="flex items-center gap-2">
        {activeAgents.map((a) => (
          <div key={a} className="text-[9px] font-mono px-2 py-1 rounded-md" style={{ background: "#1a1d27", border: "1px solid rgba(255,255,255,0.06)", color: "#6b7280" }}>
            {a}
          </div>
        ))}
        <div className="h-4 w-px mx-1" style={{ background: "rgba(255,255,255,0.06)" }} />
        {online ? (
          <Wifi className="h-3.5 w-3.5 text-emerald-400/70" />
        ) : (
          <WifiOff className="h-3.5 w-3.5 text-red-400/70" />
        )}
      </div>
    </header>
  );
}
