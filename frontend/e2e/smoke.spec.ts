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
