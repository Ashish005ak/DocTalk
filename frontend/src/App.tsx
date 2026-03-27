import { useCallback, useEffect, useRef, useState } from 'react';
import { ChatPanel } from './components/ChatPanel';
import { ContextPanel } from './components/ContextPanel';
import { SessionSetup } from './components/SessionSetup';
import { SimulationControls } from './components/SimulationControls';
import { SuggestionCards } from './components/SuggestionCards';
import { TranscriptPanel } from './components/TranscriptPanel';
import { useWebSocket } from './hooks/useWebSocket';
import type {
  ContextObject,
  DomainProfile,
  ReplayState,
  ReplayStateData,
  SessionConfig,
  Speed,
  SuggestionOutput,
  Transcript,
  Utterance,
  WSAction,
  WSMessage,
} from './types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export default function App() {
  // Session setup visibility
  const [showSetup, setShowSetup] = useState(true);
  const [sessionConfig, setSessionConfig] = useState<SessionConfig | null>(null);
  const [transcriptTitle, setTranscriptTitle] = useState('');
  const [totalTurns, setTotalTurns] = useState(0);

  // Replay state (driven by WebSocket messages)
  const [replayState, setReplayState] = useState<ReplayState>('idle');
  const [speed, setSpeed] = useState<Speed>(1.0);
  const [currentTurn, setCurrentTurn] = useState(0);

  // Transcript display state
  const [utterances, setUtterances] = useState<Utterance[]>([]);
  const [preview, setPreview] = useState<Utterance | null>(null);

  // Context engine state
  const [contextObject, setContextObject] = useState<ContextObject | null>(null);
  const [domainProfile, setDomainProfile] = useState<DomainProfile | null>(null);

  // Suggestion engine state
  const [suggestions, setSuggestions] = useState<SuggestionOutput | null>(null);

  // Chat mode state
  const [chatWaiting, setChatWaiting] = useState(false);

  // Resizable split between Context and Suggestions panels (percentage for Context)
  const [splitPct, setSplitPct] = useState(50);
  const rightColumnRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  const onDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current || !rightColumnRef.current) return;
      const rect = rightColumnRef.current.getBoundingClientRect();
      const y = e.clientY - rect.top;
      const pct = Math.min(85, Math.max(15, (y / rect.height) * 100));
      setSplitPct(pct);
    };
    const onMouseUp = () => {
      if (isDragging.current) {
        isDragging.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'utterance_preview': {
        const utt = msg.data as Utterance;
        setPreview(utt);
        break;
      }
      case 'utterance_commit': {
        const utt = msg.data as Utterance;
        setPreview(null);
        setUtterances((prev) => {
          if (prev.some((u) => u.id === utt.id)) return prev;
          return [...prev, utt];
        });
        if (utt.speaker === 'interviewer') {
          setChatWaiting(false);
        }
        break;
      }
      case 'replay_state': {
        const data = msg.data as ReplayStateData;
        setReplayState(data.state);
        setSpeed(data.speed as Speed);
        setCurrentTurn(data.turn);
        break;
      }
      case 'session_start': {
        const config = msg.data as SessionConfig;
        setSessionConfig(config);
        if (config.mode !== 'chat' && config.transcript_id) {
          fetchTranscriptMeta(config.transcript_id);
        }
        break;
      }
      case 'context_updated': {
        const ctx = msg.data as ContextObject;
        setContextObject(ctx);
        break;
      }
      case 'suggestions_updated': {
        const output = msg.data as SuggestionOutput;
        setSuggestions(output);
        break;
      }
      case 'session_end': {
        setReplayState('idle');
        setUtterances([]);
        setPreview(null);
        setCurrentTurn(0);
        setContextObject(null);
        setSuggestions(null);
        break;
      }
    }
  }, []);

  const fetchTranscriptMeta = async (transcriptId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/transcripts/${transcriptId}`);
      if (res.ok) {
        const data: Transcript = await res.json();
        setTranscriptTitle(data.title);
        setTotalTurns(data.utterances.length);
      }
    } catch {
      // Not critical
    }
  };

  const { connectionState, send, reconnect } = useWebSocket(handleMessage);

  const handleAction = useCallback(
    (action: WSAction) => {
      send(action);
      // Optimistically update speed in UI
      if (action.action === 'set_speed') {
        setSpeed(action.speed);
      }
    },
    [send],
  );

  const fetchDomainProfile = async (domainId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/domains/${domainId}`);
      if (res.ok) {
        const data: DomainProfile = await res.json();
        setDomainProfile(data);
      }
    } catch {
      // Non-critical
    }
  };

  const handleSessionStart = (config: SessionConfig) => {
    setSessionConfig(config);
    setShowSetup(false);
    setUtterances([]);
    setPreview(null);
    setCurrentTurn(0);
    setReplayState('idle');
    setContextObject(null);
    setSuggestions(null);
    setChatWaiting(false);
    fetchDomainProfile(config.domain);
    if (config.mode === 'chat') {
      setTranscriptTitle('Live Chat');
      setTotalTurns(0);
    } else {
      if (config.transcript_id) fetchTranscriptMeta(config.transcript_id);
      setTimeout(() => send({ action: 'start' }), 100);
    }
  };

  const handleReset = () => {
    send({ action: 'stop' });
    setShowSetup(true);
    setUtterances([]);
    setPreview(null);
    setCurrentTurn(0);
    setReplayState('idle');
    setContextObject(null);
    setSuggestions(null);
    setChatWaiting(false);
  };

  const sendChatMessage = useCallback(
    (text: string) => {
      setChatWaiting(true);
      send({ action: 'chat_message', text });
    },
    [send],
  );

  const interviewerLabel = sessionConfig?.interviewer_label ?? 'Interviewer';
  const responderLabel = sessionConfig?.responder_label ?? 'Responder';
  const isChatMode = sessionConfig?.mode === 'chat';

  return (
    <div className="flex flex-col h-screen bg-[#0f1117]">

      {/* Session setup modal */}
      {showSetup && <SessionSetup onSessionStart={handleSessionStart} />}

      {/* Top control bar — simulation uses full controls, chat uses a minimal header */}
      {isChatMode ? (
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#2d3555] bg-[#141927]">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center text-white font-bold text-xs">C</div>
            <div>
              <span className="text-sm font-semibold text-white">Live Chat</span>
              <span className="text-xs text-slate-400 ml-2">Medical &mdash; SOCRATES</span>
            </div>
            <span className={`w-2 h-2 rounded-full ${connectionState === 'connected' ? 'bg-emerald-400' : 'bg-red-400'}`} />
          </div>
          <button
            onClick={handleReset}
            className="px-3 py-1.5 text-xs bg-red-600/20 border border-red-500/30 text-red-400 rounded-lg hover:bg-red-600/30 transition-colors"
          >
            End Chat
          </button>
        </div>
      ) : (
        <SimulationControls
          replayState={replayState}
          speed={speed}
          currentTurn={currentTurn}
          totalTurns={totalTurns}
          transcriptTitle={transcriptTitle}
          connectionState={connectionState}
          onAction={handleAction}
          onReset={handleReset}
        />
      )}

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left — Transcript panel (60%) + optional chat input */}
        <div className="flex flex-col w-[60%] border-r border-[#2d3555]">
          <div className="px-4 py-2.5 border-b border-[#2d3555] bg-[#141927]">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              {isChatMode ? 'Conversation' : 'Live Transcript'}
            </h2>
          </div>
          <TranscriptPanel
            utterances={utterances}
            preview={preview}
            interviewerLabel={interviewerLabel}
            responderLabel={responderLabel}
          />
          {isChatMode && (
            <ChatPanel onSend={sendChatMessage} waiting={chatWaiting} />
          )}
        </div>

        {/* Right — Context + Suggestions (40%), resizable split */}
        <div ref={rightColumnRef} className="flex flex-col w-[40%] overflow-hidden">

          {/* Context panel */}
          <div
            className="flex flex-col min-h-0 overflow-hidden"
            style={{ height: isChatMode ? '100%' : `${splitPct}%` }}
          >
            <div className="px-4 py-2.5 border-b border-[#2d3555] bg-[#141927]">
              <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                Context
                {contextObject && contextObject.turn_count > 0 && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                )}
              </h2>
            </div>
            <ContextPanel
              context={contextObject}
              gapCategories={domainProfile?.gap_categories ?? []}
            />
          </div>

          {/* Drag divider + Suggestions panel (simulation mode only) */}
          {!isChatMode && (
          <>
          <div
            onMouseDown={onDividerMouseDown}
            className="flex-shrink-0 h-1.5 cursor-row-resize group relative z-10 flex items-center justify-center bg-[#141927] border-y border-[#2d3555] hover:border-indigo-500/40 transition-colors"
          >
            <div className="w-8 h-0.5 rounded-full bg-slate-700 group-hover:bg-indigo-400 transition-colors" />
          </div>

          <div
            className="flex flex-col min-h-0 overflow-hidden"
            style={{ height: `${100 - splitPct}%` }}
          >
            <div className="px-4 py-2.5 border-b border-[#2d3555] bg-[#141927]">
              <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                Suggestions
                {suggestions && suggestions.suggestions.length > 0 && (
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
                )}
              </h2>
            </div>
            <SuggestionCards suggestions={suggestions} onAction={handleAction} />
          </div>
          </>
          )}
        </div>
      </div>

      {/* Connection lost banner */}
      {connectionState === 'disconnected' && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-red-900/90 border border-red-700 text-red-200 text-sm px-4 py-2.5 rounded-lg flex items-center gap-3 shadow-xl">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          Connection lost — reconnecting…
          <button onClick={reconnect} className="underline hover:no-underline text-red-300">
            Retry now
          </button>
        </div>
      )}
    </div>
  );
}
