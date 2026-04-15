import { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

interface SessionSetupProps {
  onSessionStart: (sessionId: string, openingMessage: string) => void;
}

export function SessionSetup({ onSessionStart }: SessionSetupProps) {
  const [domainId] = useState('general_medicine');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStart = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/session?domain_id=${encodeURIComponent(domainId)}`, {
        method: 'POST',
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail ?? `Failed to create session (${res.status})`);
      }
      const data: { session_id: string; opening_message: string } = await res.json();
      onSessionStart(data.session_id, data.opening_message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-[#1a1f2e] border border-[#2d3555] rounded-2xl shadow-2xl w-full max-w-md">

        {/* Header */}
        <div className="px-6 py-5 border-b border-[#2d3555]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-600 flex items-center justify-center text-white font-bold text-sm">D</div>
            <div>
              <h1 className="text-lg font-semibold text-white">DocTalk</h1>
              <p className="text-xs text-slate-400">AI Medical Consultation</p>
            </div>
          </div>
        </div>

        <div className="px-6 py-6 space-y-5">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-4 py-3">
            <p className="text-sm text-emerald-400">
              The AI will act as a doctor conducting a medical history. You play the patient.
            </p>
          </div>

          {/* Domain display */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">Specialty</label>
            <div className="w-full bg-[#252d42] border border-[#3d4a6b] text-slate-300 rounded-lg px-3 py-2.5 text-sm">
              General Medicine
            </div>
            <p className="mt-1.5 text-xs text-slate-500">
              Additional specialties will be available in future updates.
            </p>
          </div>

          {/* Start button */}
          <button
            onClick={handleStart}
            disabled={loading}
            className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors"
          >
            {loading ? 'Starting...' : 'Start Consultation'}
          </button>
        </div>
      </div>
    </div>
  );
}
