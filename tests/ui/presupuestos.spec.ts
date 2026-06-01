import { expect, test } from "@playwright/test";

test("presupuestos history renders read-only audit state", async ({ page }) => {
  const forbiddenCalls: string[] = [];
  const forbiddenPaths = [
    "/budget-recommendations/apply-approved",
    "/apply-budget-changes"
  ];

  for (const path of forbiddenPaths) {
    await page.route(`**${path}**`, async (route) => {
      forbiddenCalls.push(route.request().url());
      await route.abort();
    });
  }

  await page.goto("/presupuestos");
  await page.getByRole("button", { name: "Solo ver" }).click();

  await expect(page.getByText("Sin propuestas guardadas pendientes.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Historial de presupuestos" })).toBeVisible();

  const history = page.locator("#historyWrap");
  await expect(history).toContainText("Thai Mérida - Delivery");
  await expect(history).toContainText("Aplicado");
  await expect(history).toContainText("$50.00");
  await expect(history).toContainText("$55.00");
  await expect(history).toContainText("Google Ads OK");
  await expect(history).toContainText("validate_only OK / apply OK");

  await expect(history.locator(".pick")).toHaveCount(0);
  await expect(history.getByRole("button", { name: /Aplicar presupuesto/i })).toHaveCount(0);
  expect(forbiddenCalls).toEqual([]);
});
