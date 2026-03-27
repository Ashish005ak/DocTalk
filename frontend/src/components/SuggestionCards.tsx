import { useCallback, useEffect, useRef, useState } from 'react';
import type { Suggestion, SuggestionOutput, WSAction } from '../types';

interface SuggestionCardsProps {
  suggestions: SuggestionOutput | null;
  onAction: (action: WSAction) => void;
}

const PRIORITY_STYLES: Record<string, { accent: string; bg: string; border: string; badge: string }> = {
  high: {
    accent: 'text-orange-400',
    bg: 'bg-orange-500/8',
    border: 'border-orange-500/25',
    badge: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  },
  medium: {
    accent: 'text-yellow-400',
    bg: 'bg-yellow-500/8',
    border: 'border-yellow-500/25',
    badge: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  },
  low: {
    accent: 'text-sky-400',
    bg: 'bg-sky-500/8',
    border: 'border-sky-500/25',
    badge: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  },
};

function PriorityBadge({ priority }: { priority: string }) {
  const style = PRIORITY_STYLES[priority] ?? PRIORITY_STYLES.low;
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border ${style.badge}`}>
      {priority}
    </span>
  );
}

function SuggestionCard({
  suggestion,
  index,
  onUse,
}: {
  suggestion: Suggestion;
  index: number;
  onUse: (id: string) => void;
}) {
  const style = PRIORITY_STYLES[suggestion.priority] ?? PRIORITY_STYLES.low;

  return (
    <div
      className={`animate-slideIn rounded-lg border px-3 py-2.5 ${style.bg} ${style.border} transition-colors`}
      style={{ animationDelay: `${index * 0.06}s` }}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <PriorityBadge priority={suggestion.priority} />
        <button
          onClick={() => onUse(suggestion.id)}
          className="flex-shrink-0 text-[11px] font-medium px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 transition-colors"
        >
          Use
        </button>
      </div>
      <p className={`text-sm font-medium leading-snug ${style.accent} mb-1`}>
        {suggestion.question}
      </p>
      <p className="text-[11px] text-slate-500 leading-relaxed">
        {suggestion.rationale}
      </p>
    </div>
  );
}

export function SuggestionCards({ suggestions, onAction }: SuggestionCardsProps) {
  const [history, setHistory] = useState<SuggestionOutput[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const prevIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!suggestions || suggestions.suggestions.length === 0) {
      setHistory([]);
      setShowHistory(false);
      prevIdRef.current = null;
      return;
    }
    const currentId = suggestions.suggestions.map((s) => s.id).join(',');
    if (currentId === prevIdRef.current) return;
    prevIdRef.current = currentId;
    setHistory((prev) => {
      if (prev.length > 0) {
        const lastIds = prev[prev.length - 1].suggestions.map((s) => s.id).join(',');
        if (lastIds === currentId) return prev;
      }
      return [...prev, suggestions];
    });
  }, [suggestions]);

  const handleUse = useCallback(
    (suggestionId: string) => {
      onAction({ action: 'use_suggestion', suggestion_id: suggestionId });
    },
    [onAction],
  );

  if (!suggestions || suggestions.suggestions.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <div className="w-10 h-10 rounded-lg bg-[#1e2330] flex items-center justify-center mb-3">
          <svg className="w-5 h-5 text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <p className="text-sm text-slate-600">Waiting for suggestions...</p>
        <p className="text-xs text-slate-700 mt-1">AI-ranked questions will appear after enough context</p>
      </div>
    );
  }

  const previousBatches = history.slice(0, -1).reverse();

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      {/* Context summary */}
      {suggestions.context_summary && (
        <div className="px-4 pt-3 pb-1">
          <p className="text-[11px] text-slate-500 italic leading-relaxed">
            {suggestions.context_summary}
          </p>
        </div>
      )}

      {/* Current suggestions */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-2 space-y-2">
        {suggestions.suggestions.slice(0, 3).map((s, i) => (
          <SuggestionCard key={s.id} suggestion={s} index={i} onUse={handleUse} />
        ))}
      </div>

      {/* Previous suggestions toggle */}
      {previousBatches.length > 0 && (
        <div className="border-t border-[#2d3555]">
          <button
            onClick={() => setShowHistory((v) => !v)}
            className="w-full px-4 py-2 flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-slate-400 transition-colors"
          >
            <svg
              className={`w-3 h-3 transition-transform ${showHistory ? 'rotate-90' : ''}`}
              viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={2}
            >
              <path d="M4 2l4 4-4 4" />
            </svg>
            Previous suggestions ({previousBatches.length})
          </button>

          {showHistory && (
            <div className="max-h-40 overflow-y-auto px-4 pb-2 space-y-1.5">
              {previousBatches.map((batch, bi) => (
                <div key={bi} className="space-y-1">
                  {batch.suggestions.map((s) => (
                    <div
                      key={s.id}
                      className="text-[11px] text-slate-600 bg-[#1a1f2e] border border-[#2d3555] rounded px-2.5 py-1.5"
                    >
                      <span className="text-slate-500 font-medium">{s.question}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
