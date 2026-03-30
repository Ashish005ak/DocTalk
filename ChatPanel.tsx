import { useCallback, useEffect, useRef, useState } from 'react';

interface ChatPanelProps {
  onSend: (text: string) => void;
  waiting: boolean;
}

export function ChatPanel({ onSend, waiting }: ChatPanelProps) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || waiting) return;
    onSend(trimmed);
    setText('');
    inputRef.current?.focus();
  }, [text, waiting, onSend]);

  useEffect(() => {
    if (!waiting) {
      inputRef.current?.focus();
    }
  }, [waiting]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <div className="flex-shrink-0 border-t border-[#2d3555] bg-[#141927] px-4 py-3">
      <div className="flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={waiting ? 'Doctor is typing...' : 'Type your message...'}
          disabled={waiting}
          rows={1}
          className="flex-1 bg-[#252d42] border border-[#3d4a6b] text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none disabled:opacity-50 disabled:cursor-not-allowed placeholder-slate-500"
        />
        <button
          onClick={handleSend}
          disabled={!text.trim() || waiting}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex-shrink-0"
        >
          {waiting ? (
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-white/60 animate-pulse" />
              Waiting
            </span>
          ) : (
            'Send'
          )}
        </button>
      </div>
    </div>
  );
}
