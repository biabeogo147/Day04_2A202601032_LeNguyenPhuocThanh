import { expect, test } from "@playwright/test";

test("chat starts immediately in a two-column mentor workspace", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("main", { name: "Trò chuyện tư vấn" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "ReAct inspector" })).toBeVisible();
  await expect(page.getByLabel("Câu hỏi tư vấn")).toBeEnabled();
  await expect(page.getByText("Bắt đầu ngay, không cần tạo hồ sơ")).toBeVisible();
  await expect(page.getByRole("button", { name: /Cuộc trò chuyện mới/ })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Hồ sơ tư vấn" })).toHaveCount(0);

  const columnCount = await page.locator(".dashboard").evaluate((element) =>
    getComputedStyle(element).gridTemplateColumns.split(" ").length,
  );
  expect(columnCount).toBe(2);
});

test("narrow viewport has no page-level horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 900 });
  await page.goto("/");

  const hasOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasOverflow).toBe(false);
  await expect(page.getByLabel("Câu hỏi tư vấn")).toBeVisible();
});

test("desktop keeps scrolling inside panels instead of the whole page", async ({ page }) => {
  await page.setViewportSize({ width: 980, height: 680 });
  await page.goto("/");

  const pageScrolls = await page.evaluate(
    () => document.documentElement.scrollHeight > document.documentElement.clientHeight,
  );
  expect(pageScrolls).toBe(false);
});

test("eval lab renders the canonical suite without horizontal overflow", async ({ page }) => {
  await page.route("**/api/v1/health", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ status: "ok" }),
  }));
  await page.setViewportSize({ width: 1180, height: 780 });
  await page.goto("/eval");

  await expect(page.getByRole("heading", { name: "Eval Lab" })).toBeVisible();
  await expect(page.getByText("30 cases", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Concurrency")).toHaveValue("3");
  await expect(page.getByText("Tra cứu chính xác tên sản phẩm")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
});

test("one failed eval worker does not block another case", async ({ page }) => {
  let sessionCount = 0;
  let runCount = 0;
  await page.route("**/api/v1/health", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/sessions", async (route) => {
    sessionCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: `s${sessionCount}`, context: {}, version_id: "version_1", provider: "openai" }),
    });
  });
  await page.route("**/api/v1/sessions/*/runs", async (route) => {
    runCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: `r${runCount}`, session_id: `s${runCount}`, status: "queued", query: "eval", answer: null, error_code: null, created_at: "", updated_at: "" }),
    });
  });
  await page.route("**/api/v1/runs/*/events*", async (route) => {
    const first = route.request().url().includes("/r1/");
    const tools = ["search_product_catalog", "get_product_details", "assess_product_safety", "rank_product_fit", "submit_consultation"];
    const chunks = tools.map((tool, index) => `id: ${index + 1}\nevent: tool.requested\ndata: ${JSON.stringify({ tool })}\n\n`);
    chunks.push(`id: 6\nevent: retrieval.candidates\ndata: ${JSON.stringify({ candidates: [{ name: "Blackmores Fish Oil 1000mg" }] })}\n\n`);
    chunks.push(`id: 7\nevent: ${first ? "run.failed" : "answer.completed"}\ndata: {}\n\n`);
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: chunks.join("") });
  });
  await page.route("**/api/v1/runs/*", async (route) => {
    const first = route.request().url().endsWith("/r1");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: first ? "r1" : "r2", session_id: first ? "s1" : "s2",
        status: first ? "failed" : "completed", query: "eval",
        error_code: first ? "scripted_failure" : null, created_at: "", updated_at: "",
        answer: first ? null : {
          status: "answered", final_judgment: "Grounded answer", recommendations: [], limitations: [],
          professional_review_required: false, disclaimer: "TPCN không phải thuốc", dataset_fingerprint: "abc",
        },
      }),
    });
  });

  await page.goto("/eval");
  await page.getByLabel("Chọn nhóm đang xem").uncheck();
  await page.getByLabel("Chọn Tra cứu chính xác tên sản phẩm").check();
  await page.getByLabel("Chọn Tên sản phẩm không dấu và thừa dấu câu").check();
  await page.getByRole("button", { name: "▶ Chạy 2 case" }).click();

  await expect(page.locator(".case-status.failed")).toHaveCount(1);
  await expect(page.locator(".case-status.passed")).toHaveCount(1);
  await expect(page.getByText("2/2")).toBeVisible();
});
