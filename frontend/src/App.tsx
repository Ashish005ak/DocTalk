import { useCallback, useState } from 'react';
import { ChatPanel } from './components/ChatPanel';
import { ContextPanel } from './components/ContextPanel';
import { SessionSetup } from './components/SessionSetup';
import { useWebSocket } from './hooks/useWebSocket';
import type { ChatMessage, ClinicalStateView, Phase, WSAgentMessage } from './types';

const PHASE_LABELS: Record<Phase, { label: string; color: string }> = {
  intake: { label: 'Intake', color: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  exploring: { label: 'Exploring', color: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30' },
  narrowing: { label: 'Narrowing', color: 'bg-amber-500/20 text-amber-400 border-amber-500/30' },
  summary: { label: 'Summary', color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' },
};

let msgCounter = 0;
function nextMsgId(): string {
  return `msg-${++msgCounter}-${Date.now()}`;
}

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [clinicalState, setClinicalState] = useState<ClinicalStateView | null>(null);
  const [phase, setPhase] = useState<Phase>('intake');
  const [isEnded, setIsEnded] = useState(false);

  const handleWsMessage = useCallback((msg: WSAgentMessage) => {
    if (msg.type === 'response') {
      setMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          speaker: 'doctor',
          text: msg.text,
          timestamp: Date.now(),
        },
      ]);
      setClinicalState(msg.state);
      setPhase(msg.phase);
      if (msg.consultation_ended) {
        setIsEnded(true);
      }
    }
  }, []);

  const { connectionState, isThinking, send, reconnect } = useWebSocket(sessionId, handleWsMessage);

  const handleSessionStart = (sid: string, openingMessage: string) => {
    setSessionId(sid);
    setMessages([
      {
        id: nextMsgId(),
        speaker: 'doctor',
        text: openingMessage,
        timestamp: Date.now(),
      },
    ]);
    setClinicalState(null);
    setPhase('intake');
    setIsEnded(false);
  };

  const handleSend = useCallback(
    (text: string) => {
      setMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          speaker: 'patient',
          text,
          timestamp: Date.now(),
        },
      ]);
      send(text);
    },
    [send],
  );

  const handleEndConsultation = () => {
    setSessionId(null);
    setMessages([]);
    setClinicalState(null);
    setPhase('intake');
    setIsEnded(false);
  };

  const showSetup = sessionId === null;
  const phaseInfo = PHASE_LABELS[phase];

  return (
    <div className="flex flex-col h-screen bg-[#0f1117]">

      {showSetup && <SessionSetup onSessionStart={handleSessionStart} />}

      {/* Top bar */}
      {!showSetup && (
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#2d3555] bg-[#141927]">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center text-white font-bold text-xs">D</div>
            <div>
              <span className="text-sm font-semibold text-white">DocTalk</span>
              <span className="text-xs text-slate-400 ml-2">Medical Consultation</span>
            </div>
            <span className={`w-2 h-2 rounded-full ${connectionState === 'connected' ? 'bg-emerald-400' : 'bg-red-400'}`} />
          </div>
          <div className="flex items-center gap-3">
            <span className={`px-2.5 py-1 rounded-md text-xs font-medium border ${phaseInfo.color}`}>
              {phaseInfo.label}
            </span>
            <button
              onClick={handleEndConsultation}
              className="px-3 py-1.5 text-xs bg-red-600/20 border border-red-500/30 text-red-400 rounded-lg hover:bg-red-600/30 transition-colors"
            >
              End Consultation
            </button>
          </div>
        </div>
      )}

      {/* Main content */}
      {!showSetup && (
        <div className="flex flex-1 overflow-hidden">
          {/* Left — Chat (60%) */}
          <div className="flex flex-col w-[60%] border-r border-[#2d3555]">
            <ChatPanel
              messages={messages}
              isThinking={isThinking}
              onSend={handleSend}
              waiting={isThinking}
              isEnded={isEnded}
            />
          </div>

          {/* Right — Clinical State (40%) */}
          <div className="flex flex-col w-[40%] overflow-hidden">
            <div className="px-4 py-2.5 border-b border-[#2d3555] bg-[#141927]">
              <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                Clinical Context
                {clinicalState && clinicalState.turn_count > 0 && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                )}
              </h2>
            </div>
            <ContextPanel state={clinicalState} />
          </div>
        </div>
      )}

      {/* Connection lost banner */}
      {!showSetup && connectionState === 'disconnected' && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-red-900/90 border border-red-700 text-red-200 text-sm px-4 py-2.5 rounded-lg flex items-center gap-3 shadow-xl">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          Connection lost &mdash; reconnecting&hellip;
          <button onClick={reconnect} className="underline hover:no-underline text-red-300">
            Retry now
          </button>
        </div>
      )}
    </div>
  );
}
