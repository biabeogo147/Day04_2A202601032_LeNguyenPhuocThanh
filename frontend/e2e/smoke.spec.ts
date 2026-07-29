import { expect, test } from "@playwright/test";

test("mentor dashboard shell", async ({ page }) => {
  await page.route("**/api/v1/profiles", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.goto("/");
  await expect(page.getByRole("main", { name: "Trò chuyện tư vấn" })).toBeVisible();
  await expect(page.getByText("Tạo hồ sơ demo")).toBeVisible();
  await expect(page.getByText("ReAct Inspector")).toBeVisible();
});
