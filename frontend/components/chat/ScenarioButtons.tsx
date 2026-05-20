"use client";

import { Zap } from "lucide-react";

const SCENARIOS = [
  {
    id: "s1",
    label: "Technical",
    tag: "S1",
    message: "AWS CloudWatch alerts stopped firing after I rotated IAM credentials yesterday. What should I check first, and what evidence should I verify?",
    color: { text: "#0891b2", bg: "rgba(8,145,178,0.06)", border: "rgba(8,145,178,0.15)" },
  },
  {
    id: "s2",
    label: "Billing",
    tag: "S2",
    message: "Customer cust_002 says they were charged twice this month. Check the billing account and explain the refund path with policy citations.",
    color: { text: "#059669", bg: "rgba(5,150,105,0.06)", border: "rgba(5,150,105,0.15)" },
  },
  {
    id: "s3",
    label: "Escalate",
    tag: "S3",
    message: "Our production monitoring has been down for 6 hours, this is unacceptable, and I need a human manager immediately.",
    color: { text: "#dc2626", bg: "rgba(220,38,38,0.06)", border: "rgba(220,38,38,0.15)" },
  },
  {
    id: "s4",
    label: "Docs",
    tag: "S4",
    message: "Which cloud providers and notification channels does CloudDash support? Answer only from the CloudDash KB with citations.",
    color: { text: "#7c3aed", bg: "rgba(124,58,237,0.06)", border: "rgba(124,58,237,0.15)" },
  },
  {
    id: "s5",
    label: "Web",
    tag: "S5",
    message: "What is the latest Render free tier cold start and bandwidth pricing today? Use web fallback if this is not in CloudDash KB.",
    color: { text: "#d97706", bg: "rgba(217,119,6,0.06)", border: "rgba(217,119,6,0.15)" },
  },
  {
    id: "s6",
    label: "Hindi",
    tag: "S6",
    message: "Mera CloudDash dashboard bahut slow load ho raha hai. Mujhe kya check karna chahiye?",
    color: { text: "#0d9488", bg: "rgba(13,148,136,0.06)", border: "rgba(13,148,136,0.15)" },
  },
  {
    id: "s7",
    label: "API",
    tag: "S7",
    message: "Show me how to configure webhook authentication and avoid API rate limit errors in CloudDash.",
    color: { text: "#2563eb", bg: "rgba(37,99,235,0.06)", border: "rgba(37,99,235,0.15)" },
  },
];

interface Props {
  onSelect: (message: string, scenarioId: string) => void;
  disabled?: boolean;
}

export function ScenarioButtons({ onSelect, disabled }: Props) {
  return (
    <div className="px-4 py-2 flex flex-nowrap gap-2 items-center overflow-x-auto overflow-y-hidden">
      <div className="flex shrink-0 items-center gap-1.5 mr-1">
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
          className="flex shrink-0 items-center gap-1.5 whitespace-nowrap text-[10px] px-2.5 py-1.5 rounded-md transition-smooth active:scale-95"
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
