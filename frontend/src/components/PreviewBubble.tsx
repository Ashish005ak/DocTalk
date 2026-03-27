import type { Utterance } from '../types';

interface PreviewBubbleProps {
  utterance: Utterance;
  interviewerLabel: string;
  responderLabel: string;
}

export function PreviewBubble({ utterance, interviewerLabel, responderLabel }: PreviewBubbleProps) {
  const isInterviewer = utterance.speaker === 'interviewer';
  const label = isInterviewer ? interviewerLabel : responderLabel;

  return (
    <div className={`flex flex-col gap-1 px-4 py-2 ${isInterviewer ? 'items-start' : 'items-end'}`}>
      <span className="text-xs font-medium text-slate-500 px-1">{label}</span>
      <div
        className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
          isInterviewer
            ? 'bg-blue-900/30 border border-blue-700/30 text-blue-100 rounded-tl-sm'
            : 'bg-green-900/30 border border-green-700/30 text-green-100 rounded-tr-sm'
        } opacity-70`}
      >
        <span>{utterance.text}</span>
        {/* Typing indicator — three pulsing dots */}
        <span className="inline-flex items-center gap-0.5 ml-2 relative top-0.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className={`inline-block w-1 h-1 rounded-full ${isInterviewer ? 'bg-blue-400' : 'bg-green-400'} animate-bounce`}
              style={{ animationDelay: `${i * 0.15}s`, animationDuration: '0.8s' }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}
