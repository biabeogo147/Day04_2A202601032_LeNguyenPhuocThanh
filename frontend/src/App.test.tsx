import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

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

  it("renders the three working areas", async () => {
    render(<App />);

    expect(screen.getByRole("complementary", { name: "Hồ sơ tư vấn" })).toBeVisible();
    expect(screen.getByRole("main", { name: "Trò chuyện tư vấn" })).toBeVisible();
    expect(screen.getByRole("complementary", { name: "ReAct inspector" })).toBeVisible();
    expect(await screen.findByText("Tạo hồ sơ demo")).toBeVisible();
  });

  it("states that raw chain-of-thought is not shown", () => {
    render(<App />);
    expect(screen.getByText("Không hiển thị chain-of-thought.")).toBeVisible();
  });
});
