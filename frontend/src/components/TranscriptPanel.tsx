import { useEffect, useRef } from 'react';
import type { Utterance } from '../types';
import { PreviewBubble } from './PreviewBubble';

interface TranscriptPanelProps {
  utterances: Utterance[];
  preview: Utterance | null;
  interviewerLabel: string;
  responderLabel: string;
}

export function TranscriptPanel({
  utterances,
  preview,
  interviewerLabel,
  responderLabel,
}: TranscriptPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new utterances or preview changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [utterances.length, preview]);

  if (utterances.length === 0 && !preview) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
        <div className="w-16 h-16 rounded-full bg-[#252d42] flex items-center justify-center mb-4">
          <svg className="w-7 h-7 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>
        <p className="text-slate-400 font-medium">Transcript will appear here</p>
        <p className="text-slate-600 text-sm mt-1">Press Play to start the simulation</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto py-2">
      {utterances.map((utt) => (
        <CommittedUtterance
          key={utt.id}
          utterance={utt}
          interviewerLabel={interviewerLabel}
          responderLabel={responderLabel}
        />
      ))}

      {/* Preview bubble — pinned just below the last committed utterance */}
      {preview && (
        <div className="animate-fadeIn">
          <PreviewBubble
            utterance={preview}
            interviewerLabel={interviewerLabel}
            responderLabel={responderLabel}
          />
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}

interface CommittedUtteranceProps {
  utterance: Utterance;
  interviewerLabel: string;
  responderLabel: string;
}

function CommittedUtterance({ utterance, interviewerLabel, responderLabel }: CommittedUtteranceProps) {
  const isInterviewer = utterance.speaker === 'interviewer';
  const label = isInterviewer ? interviewerLabel : responderLabel;

  return (
    <div className={`flex flex-col gap-1 px-4 py-2 ${isInterviewer ? 'items-start' : 'items-end'}`}>
      <div className={`flex items-center gap-2 ${isInterviewer ? '' : 'flex-row-reverse'}`}>
        <span className="text-xs font-medium text-slate-500 px-1">{label}</span>
        <span className="text-xs text-slate-600">{formatTimestamp(utterance.timestamp)}</span>
      </div>
      <div
        className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
          isInterviewer
            ? 'bg-[#1e2d4a] border border-blue-800/40 text-blue-50 rounded-tl-sm'
            : 'bg-[#1a3028] border border-green-800/40 text-green-50 rounded-tr-sm'
        }`}
      >
        {utterance.text}
      </div>
    </div>
  );
}

function formatTimestamp(ts: string): string {
  // "00:01:23.500" → "1:23"
  const parts = ts.split(':');
  if (parts.length < 3) return ts;
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  const s = Math.floor(parseFloat(parts[2]));
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}
