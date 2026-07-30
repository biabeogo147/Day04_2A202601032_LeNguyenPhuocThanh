import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App, { AnswerView, splitList } from "./App";

describe("mentor dashboard", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => [],
      }),
    );
  });

  it("starts with chat ready and no profile gate", () => {
    render(<App />);

    expect(screen.getByRole("main", { name: "Trò chuyện tư vấn" })).toBeVisible();
    expect(screen.getByRole("complementary", { name: "ReAct inspector" })).toBeVisible();
    expect(screen.queryByRole("complementary", { name: "Hồ sơ tư vấn" })).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("Hỏi về mục tiêu, thành phần hoặc sản phẩm…")).toBeEnabled();
    expect(screen.getByRole("button", { name: /Cuộc trò chuyện mới/ })).toBeVisible();
  });

  it("fills the composer from a starter question", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Omega-3 phù hợp/i }));

    expect(screen.getByRole("textbox")).toHaveValue(
      "Tìm sản phẩm Omega-3 phù hợp ngân sách 500.000đ",
    );
  });

  it("states that raw chain-of-thought is not shown", () => {
    render(<App />);
    expect(screen.getByText("Không hiển thị chain-of-thought.")).toBeVisible();
  });
  it("shows the agent follow-up question in the chat answer", () => {
    render(
      <AnswerView
        answer={{
          status: "warning",
          final_judgment: "Need more context.",
          recommendations: [],
          limitations: [],
          follow_up_question: "Would you like to add your age group?",
          professional_review_required: true,
          disclaimer: "Supplement disclaimer.",
          dataset_fingerprint: "test",
        }}
      />,
    );

    expect(screen.getByText("Would you like to add your age group?")).toBeVisible();
  });

  it("converts the no-value sentinel to an empty context list", () => {
    expect(splitList("__none__")).toEqual([]);
  });

  it("shows canonical dosage and nutrient facts in a recommendation", () => {
    render(
      <AnswerView
        answer={{
          status: "success",
          final_judgment: "Catalog result.",
          recommendations: [
            {
              product_id: "p1",
              name: "Fish Oil",
              price_vnd: 450000,
              dosage_form: "Softgel",
              daily_dosage: "2 capsules/day",
              usage: "After meals",
              fit_score: 100,
              source_row: 2,
              reasons: ["Exact match"],
              safety: { status: "checked", evidence: "Catalog only" },
              nutrients: [{ name: "Omega-3", amount: 1000, unit: "mg" }],
            },
          ],
          limitations: [],
          professional_review_required: false,
          disclaimer: "Supplement disclaimer.",
          dataset_fingerprint: "test",
        }}
      />,
    );

    expect(screen.getByText("2 capsules/day")).toBeVisible();
    expect(screen.getByText("Omega-3 1.000 mg")).toBeVisible();
  });
});
