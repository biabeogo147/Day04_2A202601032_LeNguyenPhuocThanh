import type { components } from "./generated/openapi";

export type ConversationContext = {
  age_group?: string;
  goals?: string[];
  conditions?: string[];
  medications?: string[];
  allergies?: string[];
  pregnancy_status?: string;
  budget_max_vnd?: number;
  preferred_dosage_forms?: string[];
};
export type Session = components["schemas"]["SessionRead"] & {
  context: ConversationContext;
};

export type Recommendation = {
  product_id: string;
  name: string;
  price_vnd: number;
  dosage_form: string;
  daily_dosage?: string;
  usage?: string;
  packaging?: string;
  function?: string;
  audience?: string;
  fit_score: number;
  source_row: number;
  reasons: string[];
  safety: { status: string; evidence: string };
  nutrients: Array<{ name: string; amount: number; unit: string }>;
};

export type Consultation = {
  status: string;
  final_judgment: string;
  recommendations: Recommendation[];
  limitations: string[];
  follow_up_question?: string | null;
  professional_review_required: boolean;
  disclaimer: string;
  dataset_fingerprint: string;
};

export type Run = Omit<components["schemas"]["RunRead"], "answer"> & {
  answer: Consultation | null;
};

export type TraceEvent = {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  receivedAt: number;
};
