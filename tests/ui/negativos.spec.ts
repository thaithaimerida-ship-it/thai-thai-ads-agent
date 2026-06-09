import { expect, test } from "@playwright/test";

test("negativos V2 renders a read-only review inbox", async ({ page }) => {
  const requests: string[] = [];
  const forbiddenCalls: string[] = [];
  const forbiddenPaths = new Set([
    "/execute-optimization",
    "/apply-budget-changes",
    "/budget-recommendations/apply-approved"
  ]);

  await page.route("**/*", async (route) => {
    const requestUrl = new URL(route.request().url());
    requests.push(requestUrl.pathname);

    if (forbiddenPaths.has(requestUrl.pathname) || route.request().method() !== "GET") {
      forbiddenCalls.push(`${route.request().method()} ${requestUrl.pathname}`);
      await route.abort();
      return;
    }

    if (requestUrl.pathname === "/negativos/preview-v2") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          date_range: "LAST_7_DAYS",
          total: 4,
          data_floor: { clicks_min: 12, cost_min_mxn: 120 },
          state_counts: {
            competidor_por_confirmar: 1,
            revisar_con_cuidado: 1,
            protegido: 1,
            bloqueado: 1
          },
          recommended_action_counts: { no_action: 3, needs_confirmation: 1 },
          items: [
            {
              term: "restaurante cercano para comer",
              campaign: "Thai Mérida - Experiencia",
              clicks: 14,
              cost_mxn: 144,
              conversions: 0,
              state: "competidor_por_confirmar",
              recommended_action: "needs_confirmation",
              reason_human: "Parece otro restaurante o negocio.",
              block_allowed: false,
              enough_data: true
            },
            {
              term: "hacienda teya merida",
              campaign: "Thai Mérida - Delivery",
              clicks: 3,
              cost_mxn: 18,
              conversions: 3,
              state: "revisar_con_cuidado",
              recommended_action: "no_action",
              reason_human: "Senales mixtas.",
              block_allowed: false,
              enough_data: false
            },
            {
              term: "comida tailandesa merida",
              campaign: "Thai Mérida - Experiencia",
              clicks: 10,
              cost_mxn: 16,
              conversions: 2,
              state: "protegido",
              recommended_action: "no_action",
              reason_human: "Busqueda util.",
              block_allowed: false,
              enough_data: false
            },
            {
              term: "termino ya bloqueado",
              campaign: "Thai Mérida - Delivery",
              clicks: 1,
              cost_mxn: 4,
              conversions: 0,
              state: "bloqueado",
              recommended_action: "no_action",
              reason_human: "Ya bloqueado.",
              block_allowed: false,
              enough_data: false
            }
          ]
        })
      });
      return;
    }

    await route.continue();
  });

  await page.goto("/negativos");

  await expect(page).toHaveTitle(/Bandeja V2/i);
  await expect(page.getByRole("heading", { name: "Bandeja de revisión de términos" })).toBeVisible();
  await expect(page.getByText("Modo seguro - Solo lectura")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Necesitan tu decisión" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Revisar con cuidado" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Protegidos · no se tocan" })).toBeVisible();

  await expect(page.getByText("Restaurante o negocio externo por confirmar")).toBeVisible();
  await page.getByRole("heading", { name: "Revisar con cuidado" }).click();
  await expect(page.getByText("Restaurante externo con señales locales. Requiere revisión humana.")).toBeVisible();
  await expect(page.getByText("semantic_class")).toHaveCount(0);
  await expect(page.getByText("negative_allowed")).toHaveCount(0);
  await expect(page.getByText("weak_local_action")).toHaveCount(0);

  await expect(page.getByRole("button", { name: /Aplicar/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Confirmar bloqueo/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Confirmar competidor/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Ver detalle" }).first()).toBeVisible();

  const previewCalls = requests.filter((path) => path === "/negativos/preview-v2");
  expect(previewCalls.length).toBeGreaterThan(0);
  expect(forbiddenCalls).toEqual([]);
});
