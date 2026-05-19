"use client";

import { Zap } from "lucide-react";
import { cn } from "@/lib/utils";

const SCENARIOS = [
  {
    id: "s1",
    label: "AWS Rotation",
    tag: "S1",
    message: "My alerts stopped firing after I rotated AWS credentials yesterday. How do I fix it?",
    color: { text: "#0891b2", bg: "rgba(8,145,178,0.06)", border: "rgba(8,145,178,0.15)" },
  },
  {
    id: "s2",
    label: "Billing Dispute",
    tag: "S2",
    message: "Hi, my customer ID is cust_acme_42. I see two charges of $149 in April on invoice INV-2024-04 and INV-2024-04-DUP. I think I was double charged.",
    color: { text: "#059669", bg: "rgba(5,150,105,0.06)", border: "rgba(5,150,105,0.15)" },
  },
  {
    id: "s3",
    label: "Escalation",
    tag: "S3",
    message: "This is completely unacceptable. Our production monitoring has been down for 6 hours and your technical team keeps giving me the same useless answers. I need to speak to a manager immediately.",
    color: { text: "#dc2626", bg: "rgba(220,38,38,0.06)", border: "rgba(220,38,38,0.15)" },
  },
  {
    id: "s4",
    label: "KB Gap",
    tag: "S4",
    message: "Does CloudDash support monitoring for on-premise Kubernetes clusters without internet access? We need air-gapped deployment.",
    color: { text: "#7c3aed", bg: "rgba(124,58,237,0.06)", border: "rgba(124,58,237,0.15)" },
  },
];

interface Props {
  onSelect: (message: string, scenarioId: string) => void;
  disabled?: boolean;
}

export function ScenarioButtons({ onSelect, disabled }: Props) {
  return (
    <div className="px-4 py-2 flex flex-wrap gap-2 items-center">
      <div className="flex items-center gap-1.5 mr-1">
        <Zap className="h-3 w-3" style={{ color: "var(--text-muted)" }} />
        <span className="text-[10px]" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
          quick start
        </span>
      </div>

      {SCENARIOS.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onSelect(s.message, s.id)}
          disabled={disabled}
          className="flex items-center gap-1.5 text-[10px] px-2.5 py-1.5 rounded-md transition-smooth active:scale-95"
          style={{
            background: s.color.bg,
            border: `1px solid ${s.color.border}`,
            color: s.color.text,
            fontFamily: "var(--font-mono)",
            opacity: disabled ? 0.4 : 1,
            cursor: disabled ? "not-allowed" : "pointer",
          }}
        >
          <span className="font-semibold opacity-60">{s.tag}</span>
          {s.label}
        </button>
      ))}
    </div>
  );
}
