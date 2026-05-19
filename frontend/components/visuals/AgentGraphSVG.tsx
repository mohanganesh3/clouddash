"use client";

import { motion } from "framer-motion";

const nodes = [
  { id: "triage", label: "Triage", x: 44, y: 62, color: "#d97706" },
  { id: "rag", label: "CRAG", x: 150, y: 28, color: "#7c3aed" },
  { id: "tech", label: "Tech", x: 256, y: 62, color: "#0891b2" },
  { id: "bill", label: "Billing", x: 150, y: 104, color: "#059669" },
  { id: "hitl", label: "HITL", x: 256, y: 142, color: "#dc2626" },
];

const links = [
  ["triage", "rag"],
  ["rag", "tech"],
  ["triage", "bill"],
  ["tech", "hitl"],
  ["bill", "hitl"],
];

function point(id: string) {
  return nodes.find((n) => n.id === id)!;
}

export function AgentGraphSVG() {
  return (
    <svg viewBox="0 0 304 176" role="img" aria-label="CloudDash multi-agent support graph">
      <defs>
        <filter id="agent-glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {links.map(([from, to], i) => {
        const a = point(from);
        const b = point(to);
        return (
          <motion.path
            key={`${from}-${to}`}
            d={`M ${a.x} ${a.y} C ${(a.x + b.x) / 2} ${a.y}, ${(a.x + b.x) / 2} ${b.y}, ${b.x} ${b.y}`}
            fill="none"
            stroke="rgba(240,240,245,0.18)"
            strokeWidth="1.4"
            strokeLinecap="round"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.7, delay: 0.12 * i, ease: "easeOut" }}
          />
        );
      })}

      {links.map(([from, to], i) => {
        const a = point(from);
        const b = point(to);
        return (
          <motion.circle
            key={`${from}-${to}-pulse`}
            r="3"
            fill={b.color}
            filter="url(#agent-glow)"
            initial={{ cx: a.x, cy: a.y, opacity: 0 }}
            animate={{ cx: [a.x, b.x], cy: [a.y, b.y], opacity: [0, 1, 0] }}
            transition={{ duration: 1.9, delay: 0.25 * i, repeat: Infinity, repeatDelay: 1.2, ease: "easeInOut" }}
          />
        );
      })}

      {nodes.map((node, i) => (
        <motion.g
          key={node.id}
          initial={{ opacity: 0, scale: 0.88 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.28, delay: 0.08 * i }}
        >
          <circle cx={node.x} cy={node.y} r="18" fill={`${node.color}1a`} stroke={`${node.color}66`} strokeWidth="1.2" />
          <circle cx={node.x} cy={node.y} r="5" fill={node.color} filter="url(#agent-glow)" />
          <text x={node.x} y={node.y + 32} textAnchor="middle" fill="#9ca3af" fontSize="10" fontFamily="JetBrains Mono, monospace">
            {node.label}
          </text>
        </motion.g>
      ))}
    </svg>
  );
}
