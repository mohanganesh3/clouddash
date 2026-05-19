"use client";

import type { Citation } from "@/lib/types";

interface Props {
  citations: Citation[];
  content: string;
}

// renders inline [KB-XXX §N] references as hoverable spans
export function CitationTooltip({ citations, content }: Props) {
  if (!citations || citations.length === 0) return <span>{content}</span>;

  // build a map from kb_id to citation for quick lookup
  const citMap: Record<string, Citation> = {};
  for (const c of citations) citMap[c.kb_id] = c;

  // split content on [KB-XXX § N] patterns
  const parts = content.split(/(\[KB-[A-Z0-9_-]+\s*§\s*\d+\])/g);

  return (
    <span>
      {parts.map((part, i) => {
        const match = part.match(/\[([A-Z0-9_-]+)\s*§\s*(\d+)\]/);
        if (!match) return <span key={i}>{part}</span>;
        const kbId = match[1];
        const cit = citMap[kbId];
        if (!cit) return <span key={i} className="text-blue-400 font-mono text-xs">{part}</span>;

        return (
          <span key={i} className="group relative inline-block">
            <button className="text-blue-400 font-mono text-xs hover:text-blue-300 underline decoration-dotted">
              {part}
            </button>
            {/* hover tooltip */}
            <div className="absolute bottom-full left-0 z-50 hidden group-hover:block w-72 rounded-lg border border-slate-700 bg-slate-900 p-3 shadow-xl text-xs">
              <div className="font-semibold text-slate-200 mb-1">{cit.title}</div>
              <div className="text-slate-400 leading-relaxed">{cit.snippet || "No preview available."}</div>
              <div className="mt-2 text-slate-500 font-mono">
                Score: {(cit.relevance_score * 100).toFixed(0)}%
              </div>
            </div>
          </span>
        );
      })}
    </span>
  );
}
