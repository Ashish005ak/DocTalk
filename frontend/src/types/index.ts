// ---------------------------------------------------------------------------
// Phase 6 — Types matching the backend agent API contract
// ---------------------------------------------------------------------------

export type Phase = 'intake' | 'exploring' | 'narrowing' | 'summary';

export type ConsultationEnding = 'none' | 'landing' | 'emergency' | 'closed';

export type Confidence = 'low' | 'medium' | 'high';

export interface HypothesisEntry {
  id: string;
  name: string;
  score: number;
}

export interface HypothesisView {
  leading: HypothesisEntry | null;
  differential: HypothesisEntry[];
  ruled_out: HypothesisEntry[];
}

export interface ClinicalStateView {
  phase: Phase;
  turn_count: number;
  information_gathered: Record<string, string>;
  denied_symptoms: string[];
  hypothesis: HypothesisView | null;
  confidence: Confidence;
  remaining_gaps: string[];
  confirmed_red_flag_ids: string[];
  conversation_history: { speaker: string; text: string }[];
  consultation_ending: ConsultationEnding;
}

export interface ChatMessage {
  id: string;
  speaker: 'patient' | 'doctor';
  text: string;
  timestamp: number;
}

// ---------------------------------------------------------------------------
// WebSocket message protocol (server → client)
// ---------------------------------------------------------------------------

export type WSAgentMessage =
  | { type: 'connected'; session_id: string }
  | { type: 'thinking' }
  | { type: 'response'; text: string; phase: Phase; state: ClinicalStateView; consultation_ended?: boolean }
  | { type: 'error'; message: string };
