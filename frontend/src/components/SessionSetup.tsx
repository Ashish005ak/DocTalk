import { useEffect, useRef, useState } from 'react';
import type { DomainProfile, SessionConfig, SessionMode, Speed, TranscriptMeta, Utterance } from '../types';
 
const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
 
interface SessionSetupProps {
  onSessionStart: (config: SessionConfig, openingUtterance?: Utterance) => void;
}
 
const SPEED_OPTIONS: { value: Speed; label: string }[] = [
  { value: 0.5, label: '0.5×' },
  { value: 1.0, label: '1×' },
  { value: 2.0, label: '2×' },
  { value: 4.0, label: '4×' },
];
 
type Step = 'home' | 'transcript-setup' | 'chat-setup';
 
export function SessionSetup({ onSessionStart }: SessionSetupProps) {
  const [step, setStep] = useState<Step>('home');
 
  const [transcripts, setTranscripts] = useState<TranscriptMeta[]>([]);
  const [domainProfiles, setDomainProfiles] = useState<DomainProfile[]>([]);
  const [selectedTranscript, setSelectedTranscript] = useState<string>('');
  const [speed, setSpeed] = useState<Speed>(1.0);
  const [interviewerLabel, setInterviewerLabel] = useState('Interviewer');
  const [responderLabel, setResponderLabel] = useState('Responder');
  const [domain, setDomain] = useState<string>('medical');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
 
  const [showCustomUpload, setShowCustomUpload] = useState(false);
  const [customJson, setCustomJson] = useState('');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
 
  useEffect(() => {
    fetch(`${API_BASE}/api/transcripts`)
      .then((r) => r.json())
      .then((data: TranscriptMeta[]) => {
        setTranscripts(data);
        if (data.length > 0) {
          setSelectedTranscript(data[0].id);
          setDomain(data[0].domain);
        }
      })
      .catch(() => setError('Could not load transcripts. Is the backend running?'));
 
    fetch(`${API_BASE}/api/domains`)
      .then((r) => r.json())
      .then((data: DomainProfile[]) => setDomainProfiles(data))
      .catch(() => { /* domain list is non-critical */ });
  }, []);
 
  const selectedProfile = domainProfiles.find((p) => p.id === domain);
 
  const applyDomainLabels = (domainId: string) => {
    const profile = domainProfiles.find((p) => p.id === domainId);
    if (profile?.role_labels) {
      setInterviewerLabel(profile.role_labels.interviewer ?? 'Interviewer');
      setResponderLabel(profile.role_labels.responder ?? 'Responder');
    }
  };
 
  const handleTranscriptChange = (id: string) => {
    setSelectedTranscript(id);
    const t = transcripts.find((tr) => tr.id === id);
    if (t) {
      setDomain(t.domain);
      applyDomainLabels(t.domain);
    }
  };
 
  const handleDomainChange = (domainId: string) => {
    setDomain(domainId);
    applyDomainLabels(domainId);
  };
 
  const handleFileUpload = async (file: File) => {
    setUploading(true);
    setUploadError(null);
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/api/transcripts/upload`, {
        method: 'POST',
        body: form,
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message ?? JSON.stringify(err.detail));
      }
      const meta: TranscriptMeta = await res.json();
      setTranscripts((prev) => [...prev.filter((t) => t.id !== meta.id), meta]);
      setSelectedTranscript(meta.id);
      setDomain(meta.domain);
      setShowCustomUpload(false);
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };
 
  const handleJsonPaste = async () => {
    setUploading(true);
    setUploadError(null);
    try {
      const data = JSON.parse(customJson);
      const res = await fetch(`${API_BASE}/api/transcripts/upload-json`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message ?? JSON.stringify(err.detail));
      }
      const meta: TranscriptMeta = await res.json();
      setTranscripts((prev) => [...prev.filter((t) => t.id !== meta.id), meta]);
      setSelectedTranscript(meta.id);
      setDomain(meta.domain);
      setCustomJson('');
      setShowCustomUpload(false);
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };
 
  const mode: SessionMode = step === 'chat-setup' ? 'chat' : 'simulation';
 
  const handleStart = async () => {
    const isChatMode = mode === 'chat';
    if (!isChatMode && !selectedTranscript) return;
    setLoading(true);
    setError(null);
    const config: SessionConfig = {
      transcript_id: isChatMode ? undefined : selectedTranscript,
      domain,
      mode,
      interviewer_label: interviewerLabel,
      responder_label: responderLabel,
      speed,
    };
    try {
      const res = await fetch(`${API_BASE}/api/session/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail ?? 'Failed to configure session');
      }
      const responseData = await res.json().catch(() => ({}));
      onSessionStart(config, responseData.opening_utterance);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
 
  const selectedMeta = transcripts.find((t) => t.id === selectedTranscript);
 
  const handleSelectChat = () => {
    setDomain('medical');
    applyDomainLabels('medical');
    setStep('chat-setup');
  };
 
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-[#1a1f2e] border border-[#2d3555] rounded-2xl shadow-2xl w-full max-w-lg">
 
        {/* Header */}
        <div className="px-6 py-5 border-b border-[#2d3555]">
          <div className="flex items-center gap-3">
            {step !== 'home' && (
              <button
                onClick={() => setStep('home')}
                className="w-8 h-8 rounded-lg bg-[#252d42] border border-[#3d4a6b] flex items-center justify-center text-slate-400 hover:text-white hover:bg-[#2d3a56] transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                  <path fillRule="evenodd" d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z" clipRule="evenodd" />
                </svg>
              </button>
            )}
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-sm">C</div>
            <div>
              <h1 className="text-lg font-semibold text-white">ConvoNudge</h1>
              <p className="text-xs text-slate-400">Real-Time Conversation Intelligence</p>
            </div>
          </div>
        </div>
 
        <div className="px-6 py-5 space-y-5">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}
 
          {/* ── Step: Home ── */}
          {step === 'home' && (
            <div className="space-y-4">
              <p className="text-sm text-slate-400 text-center">Choose how you'd like to start</p>
              <div className="grid grid-cols-2 gap-3">
                {/* Transcript Session card */}
                <button
                  onClick={() => setStep('transcript-setup')}
                  className="group flex flex-col items-center gap-3 p-5 bg-[#141927] border border-[#2d3555] rounded-xl hover:border-indigo-500/50 hover:bg-[#1a2240] transition-all text-left"
                >
                  <div className="w-12 h-12 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center group-hover:bg-indigo-600/30 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6 text-indigo-400">
                      <path fillRule="evenodd" d="M4.5 5.653c0-1.427 1.529-2.33 2.779-1.643l11.54 6.347c1.295.712 1.295 2.573 0 3.286L7.28 19.99c-1.25.687-2.779-.217-2.779-1.643V5.653Z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="text-center">
                    <h3 className="text-sm font-semibold text-white mb-1">Transcript Session</h3>
                    <p className="text-xs text-slate-500 leading-relaxed">
                      Replay a transcript with AI-powered analysis
                    </p>
                  </div>
                </button>
 
                {/* Chat Session card */}
                <button
                  onClick={handleSelectChat}
                  className="group flex flex-col items-center gap-3 p-5 bg-[#141927] border border-[#2d3555] rounded-xl hover:border-emerald-500/50 hover:bg-[#1a2240] transition-all text-left"
                >
                  <div className="w-12 h-12 rounded-xl bg-emerald-600/20 border border-emerald-500/30 flex items-center justify-center group-hover:bg-emerald-600/30 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6 text-emerald-400">
                      <path fillRule="evenodd" d="M4.848 2.771A49.144 49.144 0 0 1 12 2.25c2.43 0 4.817.178 7.152.52 1.978.292 3.348 2.024 3.348 3.97v6.02c0 1.946-1.37 3.678-3.348 3.97a48.901 48.901 0 0 1-3.476.383.39.39 0 0 0-.297.17l-2.755 4.133a.75.75 0 0 1-1.248 0l-2.755-4.133a.39.39 0 0 0-.297-.17 48.9 48.9 0 0 1-3.476-.384c-1.978-.29-3.348-2.024-3.348-3.97V6.741c0-1.946 1.37-3.68 3.348-3.97ZM6.75 8.25a.75.75 0 0 1 .75-.75h9a.75.75 0 0 1 0 1.5h-9a.75.75 0 0 1-.75-.75Zm.75 2.25a.75.75 0 0 0 0 1.5H12a.75.75 0 0 0 0-1.5H7.5Z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="text-center">
                    <h3 className="text-sm font-semibold text-white mb-1">Chat Session</h3>
                    <p className="text-xs text-slate-500 leading-relaxed">
                      Live conversation with an AI doctor
                    </p>
                  </div>
                </button>
              </div>
            </div>
          )}
 
          {/* ── Step: Transcript Setup ── */}
          {step === 'transcript-setup' && (
            <>
              {/* Transcript picker */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-slate-300">Transcript</label>
                  <button
                    onClick={() => setShowCustomUpload(!showCustomUpload)}
                    className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                      showCustomUpload
                        ? 'bg-indigo-600 border-indigo-500 text-white'
                        : 'bg-[#252d42] border-[#3d4a6b] text-slate-400 hover:text-white hover:bg-[#2d3a56]'
                    }`}
                  >
                    + Custom
                  </button>
                </div>
                <select
                  value={selectedTranscript}
                  onChange={(e) => handleTranscriptChange(e.target.value)}
                  className="w-full bg-[#252d42] border border-[#3d4a6b] text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {transcripts.map((t) => {
                    const dp = domainProfiles.find((p) => p.id === t.domain);
                    const label = dp?.name ?? t.domain.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                    return (
                      <option key={t.id} value={t.id}>
                        [{label}] {t.title} ({t.turn_count} turns)
                      </option>
                    );
                  })}
                </select>
                {selectedMeta && (
                  <p className="mt-1.5 text-xs text-slate-500">{selectedMeta.description}</p>
                )}
              </div>
 
              {/* Custom upload panel */}
              {showCustomUpload && (
                <div className="bg-[#141927] border border-[#2d3555] rounded-lg p-4 space-y-3">
                  <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Upload Custom Transcript</p>
                  {uploadError && (
                    <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-xs rounded px-3 py-2">
                      {uploadError}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="flex-1 py-2 px-3 bg-[#252d42] border border-dashed border-[#3d4a6b] text-slate-400 rounded-lg text-xs hover:bg-[#2d3a56] transition-colors"
                    >
                      Choose .json file
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".json"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) handleFileUpload(f);
                      }}
                    />
                  </div>
                  <p className="text-xs text-slate-500 text-center">— or paste JSON —</p>
                  <textarea
                    value={customJson}
                    onChange={(e) => setCustomJson(e.target.value)}
                    placeholder='{"id": "my_transcript", "domain": "medical", ...}'
                    rows={4}
                    className="w-full bg-[#0f1117] border border-[#2d3555] text-slate-300 text-xs rounded-lg px-3 py-2 font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
                  />
                  <button
                    onClick={handleJsonPaste}
                    disabled={!customJson.trim() || uploading}
                    className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm rounded-lg transition-colors"
                  >
                    {uploading ? 'Uploading...' : 'Load Transcript'}
                  </button>
                </div>
              )}
 
              {/* Domain selector */}
              {domainProfiles.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Domain</label>
                  <select
                    value={domain}
                    onChange={(e) => handleDomainChange(e.target.value)}
                    className="w-full bg-[#252d42] border border-[#3d4a6b] text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {domainProfiles.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                  {selectedProfile && (
                    <div className="mt-1.5 space-y-0.5">
                      <p className="text-xs text-indigo-400">Framework: {selectedProfile.framework}</p>
                      <p className="text-xs text-slate-500">{selectedProfile.description}</p>
                    </div>
                  )}
                </div>
              )}
 
              {/* Role labels */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Interviewer Label</label>
                  <input
                    value={interviewerLabel}
                    onChange={(e) => setInterviewerLabel(e.target.value)}
                    className="w-full bg-[#252d42] border border-[#3d4a6b] text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Responder Label</label>
                  <input
                    value={responderLabel}
                    onChange={(e) => setResponderLabel(e.target.value)}
                    className="w-full bg-[#252d42] border border-[#3d4a6b] text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
 
              {/* Playback Speed */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Playback Speed</label>
                <div className="flex gap-2">
                  {SPEED_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setSpeed(opt.value)}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                        speed === opt.value
                          ? 'bg-indigo-600 text-white'
                          : 'bg-[#252d42] border border-[#3d4a6b] text-slate-300 hover:bg-[#2d3a56]'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
 
              {/* Start button */}
              <button
                onClick={handleStart}
                disabled={!selectedTranscript || loading}
                className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors"
              >
                {loading ? 'Starting...' : 'Start Session'}
              </button>
            </>
          )}
 
          {/* ── Step: Chat Setup ── */}
          {step === 'chat-setup' && (
            <>
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-4 py-3">
                <p className="text-sm text-emerald-400">
                  The LLM will act as the doctor. You play the patient.
                </p>
              </div>
 
              {/* Domain (locked to medical) */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Domain</label>
                <div className="w-full bg-[#252d42] border border-[#3d4a6b] text-slate-400 rounded-lg px-3 py-2 text-sm">
                  Medical — SOCRATES Framework
                </div>
                <p className="mt-1.5 text-xs text-slate-500">
                  Chat mode is currently available for the medical domain.
                </p>
              </div>
 
              {/* Role labels */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Doctor Label</label>
                  <input
                    value={interviewerLabel}
                    onChange={(e) => setInterviewerLabel(e.target.value)}
                    className="w-full bg-[#252d42] border border-[#3d4a6b] text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Patient Label</label>
                  <input
                    value={responderLabel}
                    onChange={(e) => setResponderLabel(e.target.value)}
                    className="w-full bg-[#252d42] border border-[#3d4a6b] text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
 
              {/* Start button */}
              <button
                onClick={handleStart}
                disabled={loading}
                className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors"
              >
                {loading ? 'Starting...' : 'Start Chat'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
 
 