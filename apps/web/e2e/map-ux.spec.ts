import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("reviewed department map", () => {
  test("keeps a visual map and an accessible table equivalent on desktop", async ({
    page,
  }) => {
    await page.goto("/es/resultados");
    await page.getByRole("button", { name: /abrir mapa/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("heading", { name: /mapa de departamentos/i }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("table", { name: /equivalente tabular/i }),
    ).toBeVisible();
    await expect(
      dialog.getByText(/el color muestra presencia territorial/i),
    ).toBeVisible();
    await expect(
      dialog.getByText(/derivado local revisado de límites oficiales/i),
    ).toBeVisible();
    const canvas = dialog.locator("[data-testid=department-map-canvas] canvas");
    await expect(canvas).toHaveAttribute("aria-hidden", "true");
    await expect(canvas).toHaveJSProperty("tabIndex", -1);
    await expect(dialog.getByTestId("department-map-canvas")).toHaveAttribute(
      "data-rendered-features",
      "2",
    );
    expect(
      await dialog
        .getByTestId("department-map-svg-fallback")
        .locator("path")
        .count(),
    ).toBeGreaterThan(1);
    await dialog.screenshot({
      path: "output/playwright/map-reviewed-desktop.png",
    });
    const antioquia = dialog.getByRole("button", { name: "Antioquia" });
    await antioquia.click();
    await expect(antioquia).toHaveAttribute("aria-pressed", "true");
    await expect(
      dialog
        .getByTestId("department-map-svg-fallback")
        .locator('path[data-selected="true"]')
        .first(),
    ).toHaveAttribute("stroke-dasharray", "12 7");
    await dialog.screenshot({
      path: "output/playwright/map-reviewed-selected-desktop.png",
    });
    const scan = await new AxeBuilder({ page })
      .include('[role="dialog"]')
      .analyze();
    expect(
      scan.violations.filter((item) =>
        ["critical", "serious"].includes(item.impact ?? ""),
      ),
    ).toEqual([]);
    await dialog.getByRole("button", { name: /cerrar mapa/i }).click();
    await expect(
      page.getByRole("button", { name: /abrir mapa/i }),
    ).toBeFocused();
  });

  test("uses a full-screen mobile sheet without document overflow", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto("/es/resultados");
    await page.getByRole("button", { name: /abrir mapa/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: /cerrar mapa/i }),
    ).toBeVisible();
    await expect(
      dialog.getByText(/derivado local revisado de límites oficiales/i),
    ).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
    await dialog.screenshot({
      path: "output/playwright/map-reviewed-mobile-320.png",
    });
  });
});
