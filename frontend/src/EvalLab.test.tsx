import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EvalLab from "./EvalLab";

describe("Eval Lab", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok" }),
    }));
  });

  it("restores the latest redacted browser report after a reload", () => {
    localStorage.setItem("tpcn-eval-report-v1", JSON.stringify({
      results: [{
        caseId: "retrieval_exact_name", title: "Tra cứu chính xác tên sản phẩm", category: "retrieval",
        sessionId: "s1", run: { id: "r1", session_id: "s1", status: "completed", query: "q", answer: null, error_code: null, created_at: "", updated_at: "" },
        events: [], elapsedMs: 1, passed: true, failures: [], actualTools: [], routingPass: true,
        groundingPass: true, safetyApplicable: false, safetyPass: true, injectionApplicable: false,
        injectionPass: true, contextPass: true, constraintPass: true, guardrailViolations: [],
        requestedFields: [], interruptCount: 0,
        tokenUsage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 }, latencyMs: 1,
      }],
    }));

    render(<EvalLab />);

    expect(document.querySelectorAll(".case-status.passed")).toHaveLength(1);
    expect(screen.getByText("2", { selector: ".eval-summary strong" })).toBeVisible();
  });

  it("loads the canonical 30-case suite with concurrency three", async () => {
    render(<EvalLab />);

    expect(screen.getByRole("heading", { name: "Eval Lab" })).toBeVisible();
    expect(screen.getByText("30 cases")).toBeVisible();
    expect(screen.getByLabelText("Concurrency")).toHaveValue("3");
    expect(screen.getByText("Tra cứu chính xác tên sản phẩm")).toBeVisible();
  });
});
