import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatMessage } from '../types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const MIN_RECORDING_MS = 1500;

interface ChatPanelProps {
  messages: ChatMessage[];
  isThinking: boolean;
  onSend: (text: string) => void;
  waiting: boolean;
  isEnded?: boolean;
}

export function ChatPanel({ messages, isThinking, onSend, waiting, isEnded = false }: ChatPanelProps) {
  const [text, setText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [micError, setMicError] = useState('');

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recordingStartRef = useRef<number>(0);

  // Auto-scroll to bottom when messages change or thinking starts
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

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

  useEffect(() => {
    if (micError) {
      const t = setTimeout(() => setMicError(''), 4000);
      return () => clearTimeout(t);
    }
  }, [micError]);

  const stopRecordingTracks = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const sendAudioForTranscription = useCallback(async (blob: Blob) => {
    setIsTranscribing(true);
    try {
      const form = new FormData();
      form.append('file', blob, 'recording.webm');
      const res = await fetch(`${API_BASE}/api/transcribe`, {
        method: 'POST',
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? 'Transcription failed');
      }
      const { text: transcribed } = await res.json();
      if (transcribed) {
        setText((prev) => (prev ? `${prev} ${transcribed}` : transcribed));
        inputRef.current?.focus();
      }
    } catch (err) {
      setMicError(err instanceof Error ? err.message : 'Transcription failed');
    } finally {
      setIsTranscribing(false);
    }
  }, []);

  const startRecording = useCallback(async () => {
    setMicError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        chunksRef.current = [];
        stopRecordingTracks();
        if (blob.size > 0) {
          sendAudioForTranscription(blob);
        }
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      recordingStartRef.current = Date.now();
      setIsRecording(true);
    } catch {
      setMicError('Microphone access denied');
      stopRecordingTracks();
    }
  }, [sendAudioForTranscription, stopRecordingTracks]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    const elapsed = Date.now() - recordingStartRef.current;

    if (elapsed < MIN_RECORDING_MS) {
      if (recorder && recorder.state !== 'inactive') {
        recorder.ondataavailable = null;
        recorder.onstop = null;
        recorder.stop();
      }
      stopRecordingTracks();
      mediaRecorderRef.current = null;
      setIsRecording(false);
      setMicError('Recording too short — hold the mic button longer');
      return;
    }

    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    mediaRecorderRef.current = null;
    setIsRecording(false);
  }, [stopRecordingTracks]);

  const toggleRecording = useCallback(() => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

  useEffect(() => {
    return () => {
      stopRecording();
      stopRecordingTracks();
    };
  }, [stopRecording, stopRecordingTracks]);

  const inputDisabled = waiting || isEnded;
  const micDisabled = waiting || isTranscribing || isEnded;

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.speaker === 'patient' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                msg.speaker === 'patient'
                  ? 'bg-indigo-600 text-white rounded-br-md'
                  : 'bg-[#1e2538] border border-[#2d3555] text-slate-200 rounded-bl-md'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] font-semibold uppercase tracking-wider ${
                  msg.speaker === 'patient' ? 'text-indigo-200' : 'text-emerald-400'
                }`}>
                  {msg.speaker === 'patient' ? 'You' : 'Doctor'}
                </span>
              </div>
              <p className="whitespace-pre-wrap">{msg.text}</p>
            </div>
          </div>
        ))}

        {/* Thinking indicator */}
        {isThinking && (
          <div className="flex justify-start">
            <div className="bg-[#1e2538] border border-[#2d3555] rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400">Doctor</span>
              </div>
              <div className="typing-indicator mt-1">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <div className="flex-shrink-0 border-t border-[#2d3555] bg-[#141927] px-4 py-3">
        {isEnded && (
          <div className="mb-2 text-xs text-emerald-400 bg-emerald-400/10 border border-emerald-500/20 rounded px-3 py-2 text-center">
            Consultation has ended. Use "End Consultation" above to start a new session.
          </div>
        )}
        {micError && (
          <div className="mb-2 text-xs text-red-400 bg-red-400/10 rounded px-2 py-1">
            {micError}
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isEnded
                ? 'Consultation ended'
                : isTranscribing
                  ? 'Transcribing audio...'
                  : waiting
                    ? 'Doctor is thinking...'
                    : 'Describe your symptoms...'
            }
            disabled={inputDisabled}
            rows={1}
            className="flex-1 bg-[#252d42] border border-[#3d4a6b] text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none disabled:opacity-50 disabled:cursor-not-allowed placeholder-slate-500"
          />

          {/* Mic button */}
          <button
            onClick={toggleRecording}
            disabled={micDisabled}
            title={isRecording ? 'Stop recording' : 'Start voice input'}
            className={`p-2 rounded-lg transition-colors flex-shrink-0 ${
              isRecording
                ? 'bg-red-600 hover:bg-red-500 animate-pulse'
                : isTranscribing
                  ? 'bg-[#252d42] opacity-50 cursor-not-allowed'
                  : 'bg-[#252d42] hover:bg-[#3d4a6b] border border-[#3d4a6b]'
            } disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            {isTranscribing ? (
              <svg className="w-5 h-5 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg
                className={`w-5 h-5 ${isRecording ? 'text-white' : 'text-slate-400'}`}
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <path d="M12 14a3 3 0 003-3V5a3 3 0 00-6 0v6a3 3 0 003 3zm5-3a5 5 0 01-10 0H5a7 7 0 0014 0h-2zm-4 7.93A7.001 7.001 0 0012 19a7.001 7.001 0 01-1 .001V22h2v-3.07z" />
              </svg>
            )}
          </button>

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!text.trim() || inputDisabled}
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
    </div>
  );
}
