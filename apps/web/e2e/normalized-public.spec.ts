import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const release = "candidate-2026-r2-dacb28aa766eec87";
const election = "presidencia-2026-segunda-vuelta";
const scope = `release=${release}&election=${election}`;

test.describe("normalized public release explorer", () => {
  test("analysis is plain-language first and gates research outputs", async ({
    page,
  }) => {
    await page.goto(`/es/analitica?${scope}`);
    await expect(page.locator("#main-content")).toHaveAttribute(
      "data-design-version",
      "v2",
    );
    await expect(page.locator("[data-analysis-section]")).toHaveCount(8);
    await expect(
      page.getByRole("heading", {
        name: /qué encontró el análisis.*qué no puede afirmar/i,
      }),
    ).toBeVisible();
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
      "content",
      /noindex.*nofollow/i,
    );
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      /\/es\/resultados$/,
    );
    await expect(
      page.getByRole("heading", {
        name: /vista de investigación.*no es una conclusión pública/i,
      }),
    ).toBeVisible();
    await expect(
      page.getByText(
        /no puede publicarse una conclusión estadística definitiva/i,
      ),
    ).toBeVisible();
    await expect(
      page
        .getByText(/no es una probabilidad ni un hallazgo de fraude/i)
        .first(),
    ).toBeVisible();
    await expect(page.getByText("70/100")).toBeVisible();
    await expect(
      page.getByText(/no se pudo evaluar una explicación/i).first(),
    ).toBeVisible();

    await page
      .getByRole("button", { name: /aplicar filtros/i })
      .scrollIntoViewIfNeeded();
    await page.getByLabel("Tipo de regla").selectOption("peer_distribution");
    await page.getByRole("button", { name: /aplicar filtros/i }).click();
    await expect(page).toHaveURL(/tipo=peer_distribution/);
    await expect(page.getByText("MESA-002", { exact: false })).toBeVisible();
    await expect(page.getByText("0/100", { exact: true })).toBeVisible();
    await expect(page.getByText("MESA-001", { exact: false })).toHaveCount(0);

    await page.goto(`/es/analitica?${scope}`);
    await page
      .getByRole("heading", {
        name: /diagnósticos.*validación.*procedencia.*descargas/i,
      })
      .scrollIntoViewIfNeeded();
    await page.getByText(/validación.*vista de investigación/i).click();
    await expect(page.getByText("false_discovery_rate")).toBeVisible();
    await expect(
      page
        .getByRole("table", { name: "Validación", exact: true })
        .getByRole("cell", { name: "0", exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("Release, elección y análisis")).toHaveCount(
      1,
    );
    await expect(page.getByLabel("Release", { exact: true })).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: /descargar artefacto inmutable/i }),
    ).toHaveAttribute(
      "href",
      /analysis_release=analysis-c0861cb0e75421d1aef02335/,
    );
  });

  test("anomaly detail keeps detection, explanation, and priority separate", async ({
    page,
  }) => {
    await page.goto(`/es/analitica?${scope}&tipo=cross_source_documentary`);
    await page.getByRole("link", { name: /abrir evidencia completa/i }).click();
    await expect(page).toHaveURL(
      new RegExp(
        `/es/analitica/anomalias/analysis-anomaly-001.*release=${release}.*election=${election}`,
      ),
    );
    await expect(
      page.getByRole("heading", { name: /análisis de mesa.*mesa-001/i }),
    ).toBeVisible();
    await expect(page.locator("#main-content")).toHaveAttribute(
      "data-design-version",
      "v2",
    );
    await expect(
      page.getByRole("heading", {
        name: /no se pudo evaluar una explicación/i,
      }),
    ).toBeVisible();
    await expect(page.getByText("70/100")).toBeVisible();
    await expect(page.getByText(/126.*120.*6 votes/i)).toBeVisible();
    await expect(
      page.getByText(
        /límite mecánico.*no una estimación de votos fraudulentos/i,
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /ver resultado de la mesa/i }),
    ).toHaveAttribute("href", /release=candidate-2026-r2-dacb28aa766eec87/);
    await page.screenshot({
      path: "output/playwright/analysis-detail-desktop.png",
      fullPage: true,
    });

    await page.goto(`/es/analitica/anomalias/no-existe?${scope}`);
    await expect(page.locator("#main-content")).toHaveAttribute(
      "data-design-version",
      "v2",
    );
    await expect(
      page.getByRole("heading", { name: /análisis no encontrado/i }),
    ).toBeVisible();
    await expect(
      page.getByText(/no se sustituyen recursos ausentes/i),
    ).toBeVisible();
  });

  test("analysis remains table-first, keyboard-safe, and bounded at 320px", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto(`/en/analitica?${scope}`);
    await expect(
      page.getByRole("heading", {
        name: /research view.*not yet a public conclusion/i,
      }),
    ).toBeVisible();
    await expect(page.locator("#main-content")).toHaveCount(1);
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: /skip to main content/i });
    await expect(skip).toBeFocused();
    await skip.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
    const width = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(width.scroll).toBeLessThanOrEqual(width.client);
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      scan.violations.filter((item) =>
        ["critical", "serious"].includes(item.impact ?? ""),
      ),
    ).toEqual([]);
    await page.screenshot({
      path: "output/playwright/analysis-public-mobile-320.png",
      fullPage: true,
    });
  });

  test("captures final analysis desktop and proves ES/EN at 200% zoom", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`/es/analitica?${scope}`);
    await expect(
      page.getByRole("heading", {
        name: /qué encontró el análisis.*qué no puede afirmar/i,
      }),
    ).toBeVisible();
    await page.screenshot({
      path: "output/playwright/analysis-public-desktop.png",
      fullPage: true,
    });

    for (const locale of ["es", "en"] as const) {
      await page.goto(`/${locale}/analitica?${scope}`);
      await expect(page.locator("#main-content")).toHaveCount(1);
      await page.evaluate(() => {
        document.body.style.zoom = "2";
      });
      const dimensions = await page.evaluate(() => ({
        client: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
      await expect(
        page.getByRole("form", {
          name:
            locale === "es"
              ? /explore registro por registro/i
              : /explore record by record/i,
        }),
      ).toBeVisible();
      await page.screenshot({
        path: `output/playwright/analysis-public-${locale}-zoom-200.png`,
      });
    }
  });

  test("selector exposes the preliminary source plus three published contexts", async ({
    page,
  }) => {
    await page.goto(`/es/resultados?${scope}`);
    await expect(
      page.getByRole("heading", { name: /resultados preliminares/i }),
    ).toBeVisible();
    const releases = page.getByLabel("Release");
    await expect(releases.locator("option")).toHaveCount(4);
    await expect(releases.locator("option").first()).toContainText(
      "candidate-2026-r2-dacb28aa766eec87",
    );
    await expect(
      page.getByRole("table", { name: /resultados preliminares/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "Municipio", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "Mesa", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "Preconteo", exact: true }).first(),
    ).toBeVisible();

    await page.goto(
      `/es/resultados?release=candidate-secret&election=${election}`,
    );
    await expect(
      page.getByRole("option", { name: /selección no publicada/i }),
    ).toBeAttached();
    await expect(page.getByText(/candidate-secret/i)).toHaveCount(0);
  });

  test("municipality → polling place → mesa is canonical and shareable", async ({
    page,
  }) => {
    await page.goto(
      `/es/resultados/geografia/MUN-001?${scope}&source=pre_count&level=polling_place`,
    );
    await expect(page.getByRole("heading", { name: "Bogotá" })).toBeVisible();
    await expect(page.getByText("Municipio", { exact: true })).toBeVisible();
    await expect(
      page.getByText("1 unidad hija", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "Puesto de votación", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /siguiente página/i }),
    ).toHaveAttribute("href", /cursor=geo-next/);
    await page.getByRole("link", { name: /ver siguiente nivel/i }).click();
    await expect(page).toHaveURL(
      new RegExp(
        `/es/resultados/geografia/PLACE-01.*release=${release}.*source=pre_count`,
      ),
    );
    await expect(
      page.getByRole("heading", { name: "Colegio Central" }),
    ).toBeVisible();
    await page.getByRole("link", { name: /abrir mesa/i }).click();
    await expect(page).toHaveURL(
      new RegExp(
        `/es/resultados/mesa/MESA-001.*release=${release}.*source=pre_count`,
      ),
    );
    await expect(page.getByRole("heading", { name: "Mesa 001" })).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Bogotá", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "Preconteo", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "Preliminar", exact: true }),
    ).toBeVisible();

    const shared = page.url();
    await page.goto("about:blank");
    await page.goto(shared);
    await expect(page.getByRole("heading", { name: "Mesa 001" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Fuente" })).toHaveValue(
      "pre_count",
    );
  });

  test("direct mesa URL preserves filters across locale switch", async ({
    page,
  }) => {
    await page.goto(`/es/resultados/mesa/MESA-001?${scope}&source=pre_count`);
    await page.getByRole("button", { name: "Idioma" }).click();
    await page.getByText("English", { exact: true }).click();
    await expect(page).toHaveURL(
      new RegExp(
        `/en/resultados/mesa/MESA-001.*release=${release}.*source=pre_count`,
      ),
    );
    await expect(page.getByRole("heading", { name: "Mesa 001" })).toBeVisible();
    await expect(
      page.getByRole("form", { name: /filter mesa sources/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("option", { name: "Pre-count", exact: true }),
    ).toBeAttached();
    await expect(
      page.getByRole("cell", { name: "Preliminary", exact: true }),
    ).toBeVisible();
  });

  test("typed 404 and source-unavailable states never display a made-up zero", async ({
    page,
  }) => {
    await page.goto(`/es/resultados/mesa/NO-EXISTE?${scope}`);
    await expect(
      page.getByRole("heading", { name: /mesa no disponible/i }),
    ).toBeVisible();
    await expect(
      page.getByText(/404.*no existe una publicación/i),
    ).toBeVisible();

    await page.goto(`/es/resultados/mesa/MESA-001?${scope}&source=scrutiny`);
    await expect(
      page.getByText(/no hay un hecho publicado para esta fuente/i),
    ).toBeVisible();
    await expect(page.getByText(/no se muestra cero/i)).toBeVisible();
  });

  test("keyboard and mobile keep the bounded geography table first", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto(`/es/resultados/geografia/MUN-001?${scope}`);
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: /saltar al contenido/i });
    await expect(skip).toBeFocused();
    await skip.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
    await expect(
      page.getByRole("table", { name: /unidades geográficas hijas/i }),
    ).toBeVisible();
    const width = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(width.scroll).toBeLessThanOrEqual(width.client);
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      scan.violations.filter((item) =>
        ["critical", "serious"].includes(item.impact ?? ""),
      ),
    ).toEqual([]);
  });

  test("category depth is lazy and MapLibre stays outside the initial budget", async ({
    page,
  }, testInfo) => {
    await page.goto(`/es/resultados?${scope}`);
    const initial = await page.evaluate(() =>
      performance.getEntriesByType("resource").map((entry) => ({
        name: entry.name,
        bytes: (entry as PerformanceResourceTiming).encodedBodySize,
      })),
    );
    expect(initial.some((entry) => /maplibre/i.test(entry.name))).toBeFalsy();
    const jsBytes = initial
      .filter((entry) => /\/_next\/.*\.js(?:\?|$)/.test(entry.name))
      .reduce((total, entry) => total + entry.bytes, 0);
    testInfo.annotations.push({
      type: "normalized-initial-js",
      description: `${jsBytes} bytes`,
    });
    expect(jsBytes).toBeLessThan(200 * 1024);
    await page
      .getByText(/profundizar: categorías y procedencia/i)
      .first()
      .click();
    await expect(page.getByText("Votos válidos").first()).toBeVisible();
  });

  test("captures normalized desktop and mobile evidence", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`/es/resultados?${scope}`);
    await page.screenshot({
      path: "output/playwright/normalized-results-desktop.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto(`/es/resultados/geografia/MUN-001?${scope}`);
    await page.screenshot({
      path: "output/playwright/normalized-geography-mobile-320.png",
      fullPage: true,
    });
  });
});
