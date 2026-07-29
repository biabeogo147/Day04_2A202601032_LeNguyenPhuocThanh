import type { components } from "./generated/openapi";

export type Profile = components["schemas"]["ProfileRead"];
export type ProfileDraft = Required<components["schemas"]["ProfileCreate"]>;
export type Session = components["schemas"]["SessionRead"];

export type Recommendation = {
  product_id: string;
  name: string;
  price_vnd: number;
  dosage_form: string;
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
  disclaimer: string;
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
