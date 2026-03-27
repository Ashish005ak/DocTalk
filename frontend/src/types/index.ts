// ---------------------------------------------------------------------------
// Core data types — mirror the Python Pydantic models exactly
// ---------------------------------------------------------------------------

export interface Utterance {
  id: string;
  timestamp: string; // "HH:MM:SS.mmm"
  speaker: 'interviewer' | 'responder';
  text: string;
  is_preview: boolean;
}

export interface TranscriptMeta {
  id: string;
  domain: Domain;
  title: string;
  description: string;
  turn_count: number;
}

export interface Transcript {
  id: string;
  domain: Domain;
  title: string;
  description: string;
  utterances: Utterance[];
}

export type SessionMode = 'simulation' | 'chat';

export interface SessionConfig {
  transcript_id?: string;
  domain: string;
  mode: SessionMode;
  interviewer_label: string;
  responder_label: string;
  speed: Speed;
}

export interface SessionState {
  state: ReplayState;
  transcript_id: string | null;
  domain: string | null;
  turn_count: number;
  current_turn: number;
  speed: Speed;
}

// ---------------------------------------------------------------------------
// Domain
// ---------------------------------------------------------------------------

// Known built-in domains — open string allows any custom domain to pass through
export type Domain = string;

export type BuiltinDomain =
  | 'medical'
  | 'legal'
  | 'hr'
  | 'journalism'
  | 'ux_research'
  | 'custom';

export interface DomainStub {
  id: Domain;
  label: string;
  description: string;
}

export interface DomainProfile {
  id: string;
  name: string;
  description: string;
  framework: string;
  role_labels: Record<string, string>;
  gap_categories: string[];
  signal_types: string[];
  priority_rules: string[];
  system_prompt_fragment: string;
  opening_message: string;
}

// ---------------------------------------------------------------------------
// Context (Phase 2.3)
// ---------------------------------------------------------------------------

export interface InformationItem {
  key: string;
  value: string;
  source_utt: string;
}

export interface Signal {
  type: string;
  detail: string;
  source_utt: string;
}

export interface ContextObject {
  session_id: string;
  core_topic: string;
  information_gathered: InformationItem[];
  questions_asked: string[];
  gaps: string[];
  signals: Signal[];
  turn_count: number;
}

// ---------------------------------------------------------------------------
// Suggestions (Phase 3)
// ---------------------------------------------------------------------------

export interface Suggestion {
  id: string;
  priority: 'high' | 'medium' | 'low';
  question: string;
  rationale: string;
}

export interface SuggestionOutput {
  trigger_utt: string;
  context_summary: string;
  suggestions: Suggestion[];
}

// ---------------------------------------------------------------------------
// Replay
// ---------------------------------------------------------------------------

export type ReplayState = 'idle' | 'playing' | 'paused' | 'finished';
export type Speed = 0.5 | 1.0 | 2.0 | 4.0;

export interface ReplayStateData {
  state: ReplayState;
  turn: number;
  speed: Speed;
  transcript_id: string | null;
}

// ---------------------------------------------------------------------------
// WebSocket message protocol
// ---------------------------------------------------------------------------

export type WSMessageType =
  | 'connection_ack'
  | 'utterance_preview'
  | 'utterance_commit'
  | 'replay_state'
  | 'session_start'
  | 'session_end'
  | 'context_updated'
  | 'suggestions_updated'
  | 'ack'
  | 'error';

export interface WSMessage<T = unknown> {
  type: WSMessageType;
  data?: T;
}

export interface WSConnectionAck {
  client_id: string;
  connections: number;
}

export interface WSError {
  message: string;
}

// ---------------------------------------------------------------------------
// WebSocket action protocol (client → server)
// ---------------------------------------------------------------------------

export type WSAction =
  | { action: 'start' }
  | { action: 'pause' }
  | { action: 'resume' }
  | { action: 'stop' }
  | { action: 'set_speed'; speed: Speed }
  | { action: 'load_transcript'; transcript_id: string }
  | { action: 'use_suggestion'; suggestion_id: string }
  | { action: 'chat_message'; text: string };
