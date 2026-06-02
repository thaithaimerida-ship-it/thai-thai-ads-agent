import { expect, test } from "@playwright/test";

test("negativos renders read-only review sections without mutating", async ({ page }) => {
  const forbiddenCalls: string[] = [];
  const forbiddenPaths = new Set([
    "/execute-optimization",
    "/apply-budget-changes",
    "/budget-recommendations/apply-approved"
  ]);

  await page.route("**/*", async (route) => {
    const requestUrl = new URL(route.request().url());
    if (forbiddenPaths.has(requestUrl.pathname)) {
      forbiddenCalls.push(route.request().url());
      await route.abort();
      return;
    }
    await route.continue();
  });

  await page.addInitScript(() => {
    window.localStorage.setItem(
      "tt_admin_token",
      "not-a-real-token-read-only-ui-gate"
    );
  });

  await page.goto("/negativos");

  await expect(page).toHaveTitle(/Negativos/i);
  await expect(page.getByRole("heading", { name: /Negativos/i })).toBeVisible();
  await page.getByRole("button", { name: "Cargar" }).click();

  const expectedVisibleSections = [
    "Listos para aplicar",
    "Ya negativos",
    "Revisar entidad ajena",
    "Protegidos",
    "Monitoreo"
  ];

  for (const section of expectedVisibleSections) {
    await expect(page.getByRole("heading", { name: new RegExp(section) })).toBeVisible();
  }

  // Empty buckets are intentionally omitted by sectionHtml(), so "Rojo bloqueado"
  // and "Ambiguos / pueden traer clientes" may be absent in production data.
  const headings = await page.locator("h2.sec").allTextContents();
  expect(headings.length).toBeGreaterThan(0);

  await expect(page.locator(".pick:checked")).toHaveCount(0);
  await expect(page.locator(".review-pick:checked")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Confirmar y enviar/i })).toHaveCount(0);
  expect(forbiddenCalls).toEqual([]);
});
