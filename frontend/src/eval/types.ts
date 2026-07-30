import type { ConversationContext, Run, TraceEvent } from "../types";

export type EvalTurn = {
  message: string;
  resume_patch?: ConversationContext;
};

export type EvalExpectations = {
  required_tools: string[];
  forbidden_tools?: string[];
  grounded: boolean;
  exact_name_top_1?: string;
  max_recommendations?: number;
  max_price_vnd?: number;
  dosage_form?: string;
  status?: string;
  focus_nutrients?: string[];
  interrupt_required?: boolean;
  max_interrupts?: number;
  expected_requested_fields?: string[];
  forbidden_requested_fields?: string[];
  professional_review_required?: boolean;
  safety_conflict_recall?: boolean;
  safety_status?: string;
  explicit_conflicts_excluded?: boolean;
  excluded_product_names?: string[];
  required_limitation_phrases?: string[];
  forbidden_answer_phrases?: string[];
  forbidden_recommendation_ids?: string[];
  injection_resistance?: boolean;
};

export type EvalCase = {
  id: string;
  title: string;
  category: "retrieval" | "context" | "safety" | "grounding" | "injection";
  tags: string[];
  kind: string;
  initial_context: ConversationContext;
  turns: EvalTurn[];
  expects: EvalExpectations;
};

export type EvalExecution = {
  caseId: string;
  sessionId: string;
  run: Run;
  events: TraceEvent[];
  elapsedMs: number;
};

export type TokenUsage = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export type EvalResult = EvalExecution & {
  title: string;
  category: EvalCase["category"];
  passed: boolean;
  failures: string[];
  actualTools: string[];
  routingPass: boolean;
  groundingPass: boolean;
  safetyApplicable: boolean;
  safetyPass: boolean;
  injectionApplicable: boolean;
  injectionPass: boolean;
  contextPass: boolean;
  constraintPass: boolean;
  guardrailViolations: string[];
  requestedFields: string[];
  interruptCount: number;
  tokenUsage: TokenUsage;
  latencyMs: number;
};

export type EvalCaseStatus = "idle" | "queued" | "running" | "passed" | "failed";
