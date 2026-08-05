import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const mesa = "2026-R2-11-001-001-001";

/** The only outbound URL in fixture content is documentary; no E2E test uses it. */
async function keepFixturesOffline(page: Page) {
  await page.route(/^https:\/\/(?!127\.0\.0\.1)/, (route) => route.abort());
}

async function expectSyntheticFixture(page: Page) {
  await expect(
    page.getByText(/FIJACIÓN SINTÉTICA|SYNTHETIC FIXTURE/i).first(),
  ).toBeVisible();
}

test.describe("public election product QA", () => {
  test.beforeEach(async ({ page }) => {
    await keepFixturesOffline(page);
  });

  test("national → results → canonical mesa → evidence is a permanent, usable path", async ({
    page,
  }) => {
    await page.goto("/es");
    await expectSyntheticFixture(page);
    await expect(page.getByLabel(/Participación: 80/).first()).toBeVisible();
    await page.getByRole("link", { name: /explorar resultados/i }).click();
    await expect(page).toHaveURL(/\/es\/resultados$/);
    await expectSyntheticFixture(page);
    await page.getByRole("link", { name: mesa }).first().click();
    await expect(page).toHaveURL(new RegExp(`/es/resultados/mesa/${mesa}$`));
    await expect(
      page.getByRole("heading", { name: /mesa 001/i }),
    ).toBeVisible();
    await page.getByRole("link", { name: /actas de mesa/i }).click();
    await expect(page).toHaveURL(new RegExp(`/es/actas/${mesa}$`));
    await expect(
      page.getByRole("heading", { name: /actas de mesa/i }),
    ).toBeVisible();
    await expect(page.getByText("Indexado · No solicitada")).toBeVisible();
  });

  for (const [locale, title] of [
    ["es", /resultados por mesa/i],
    ["en", /mesa-level results/i],
  ] as const) {
    test(`${locale} results route has language parity and correct document language`, async ({
      page,
    }) => {
      await page.goto(`/${locale}/resultados`);
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
      await expect(page.getByRole("heading", { name: title })).toBeVisible();
      await expectSyntheticFixture(page);
    });
  }

  for (const [locale, title] of [
    ["es", /portal de analítica electoral/i],
    ["en", /election analytics portal/i],
  ] as const) {
    test(`${locale} analytics route has language parity and a source-scoped reading`, async ({
      page,
    }) => {
      await page.goto(`/${locale}/analitica`);
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
      await expect(page.getByRole("heading", { name: title })).toBeVisible();
      await expectSyntheticFixture(page);
      await expect(
        page.getByRole("heading", {
          name:
            locale === "es" ? /cadena de publicación/i : /publication chain/i,
        }),
      ).toBeVisible();
    });
  }

  test("analytics keeps aggregates, descriptive bulletins, and review limits explicit", async ({
    page,
  }) => {
    await page.goto("/es/analitica");
    await expect(page.getByText("54 votos").first()).toBeVisible();
    await expect(page.getByText("4,7 puntos porcentuales")).toBeVisible();
    await expect(
      page.getByText(
        /no es una proyección, una tendencia ni una medida de certeza/i,
      ),
    ).toBeVisible();
    await expect(
      page.getByText(/no afirma un conteo nacional de señales/i),
    ).toBeVisible();
    const visibleSignals = await page
      .getByRole("link", { name: /^Mesa / })
      .count();
    await expect(
      page.getByText(
        "Este puntaje prioriza registros para revisión documental; no mide ni determina fraude. La ausencia de una señal no demuestra que una mesa estuviera libre de errores.",
      ),
    ).toHaveCount(visibleSignals + 1);
  });

  test("captures reviewed investigation reading at desktop and 320px", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/es/analitica");
    await expect(page.getByText(/sensibilidad del resultado/i)).toBeVisible();
    await page.screenshot({
      path: "output/playwright/investigation-analytics-desktop.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto("/es/analitica");
    const dimensions = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(dimensions.client).toBe(320);
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
    await page.screenshot({
      path: "output/playwright/investigation-analytics-mobile-320.png",
      fullPage: true,
    });
  });

  test("result filters are URL-addressable and CSV preserves those filters", async ({
    page,
  }) => {
    await page.goto("/es/resultados");
    const table = page.getByRole("table", {
      name: /resultados filtrados por mesa/i,
    });
    await table.getByRole("button", { name: "Votos" }).click();
    await expect(
      table.locator("tbody tr").first().locator("td").nth(3),
    ).toHaveText("82");
    await expect(
      table.getByRole("columnheader", { name: /Votos/ }),
    ).toHaveAttribute("aria-sort", "ascending");
    await page.getByLabel("Candidatura").selectOption("candidatura-horizonte");
    await expect(page).toHaveURL(/candidate=candidatura-horizonte/);
    const csv = page.getByRole("link", { name: /CSV con estos filtros/i });
    await expect(csv).toHaveAttribute("download", /fixture-2026-round2-v1/);
    const href = await csv.getAttribute("href");
    expect(href).toMatch(/^data:text\/csv;charset=utf-8,/);
    const exported = decodeURIComponent(href?.split(",", 2).at(1) ?? "");
    expect(exported).toContain("candidatura-horizonte");
    expect(exported).toContain("fixture-2026-round2-v1");
    expect(exported).not.toContain("candidatura-rio");
  });

  test("review disclosure is exact, permanent, methodological, and neutral", async ({
    page,
  }) => {
    await page.goto("/es/revision");
    await expectSyntheticFixture(page);
    await expect(
      page
        .getByText(
          "Este puntaje prioriza registros para revisión documental; no mide ni determina fraude. La ausencia de una señal no demuestra que una mesa estuviera libre de errores.",
        )
        .first(),
    ).toBeVisible();
    await expect(page.getByText(/versión de metodología/i)).toBeVisible();
    await expect(
      page.getByText(/fraude confirmado|mesa fraudulenta/i),
    ).toHaveCount(0);
  });

  test("every data-bearing fixture view carries the persistent synthetic banner", async ({
    page,
  }) => {
    const fixtureViews = [
      "/es",
      "/en",
      "/es/resultados",
      "/en/resultados",
      "/es/analitica",
      "/en/analitica",
      `/es/resultados/mesa/${mesa}`,
      `/en/resultados/mesa/${mesa}`,
      `/es/actas/${mesa}`,
      `/en/actas/${mesa}`,
      "/es/revision",
      "/en/revision",
      "/es/boletines",
      "/en/boletines",
      "/es/descargas",
      "/en/descargas",
      "/es/fuentes",
      "/en/fuentes",
    ];
    for (const path of fixtureViews) {
      await page.goto(path);
      await expectSyntheticFixture(page);
    }
  });

  test("keyboard navigation exposes focus, skip link, and a dismissible focused map dialog", async ({
    page,
  }) => {
    await page.goto("/es/resultados");
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: /saltar al contenido/i });
    await expect(skip).toBeFocused();
    await expect(skip).toHaveCSS("outline-style", "solid");
    await skip.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();

    const mapButton = page.getByRole("button", { name: /abrir mapa/i });
    await mapButton.focus();
    await mapButton.press("Enter");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: /cerrar/i })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(mapButton).toBeFocused();
  });

  test("map dialog provides its table equivalent and honors reduced motion", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/es/resultados");
    await page.getByRole("button", { name: /abrir mapa/i }).click();
    await expect(page.getByRole("dialog").getByRole("table")).toBeVisible();
    await expect(
      page.getByRole("dialog").getByText(/equivalente del mapa/i),
    ).toBeVisible();
    await expect(page.locator("html")).toHaveCSS("scroll-behavior", "auto");
  });

  test("critical and serious axe violations are absent on representative data views", async ({
    page,
  }) => {
    for (const path of [
      "/es",
      "/es/resultados",
      "/es/analitica",
      `/es/actas/${mesa}`,
      "/es/revision",
    ]) {
      await page.goto(path);
      const scan = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      const blocking = scan.violations.filter((violation) =>
        ["critical", "serious"].includes(violation.impact ?? ""),
      );
      expect(
        blocking,
        `${path}: ${blocking.map((item) => item.id).join(", ")}`,
      ).toEqual([]);
    }
  });

  test("candidate identification is textual rather than color-only", async ({
    page,
  }) => {
    await page.goto("/es");
    const candidates = page
      .locator("ol > li")
      .filter({ has: page.getByText(/Candidatura (Horizonte|Río)/) });
    await expect(candidates).toHaveCount(2);
    await expect(candidates.nth(0)).toContainText("1");
    await expect(candidates.nth(1)).toContainText("2");
  });

  test("shell keeps full navigation at 1440px and the compact menu at 320px", async ({
    page,
  }) => {
    const desktopNavigation = page.locator('[data-shell-navigation="desktop"]');
    const compactNavigation = page.locator('[data-shell-navigation="compact"]');

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/es");
    await expect(desktopNavigation).toBeVisible();
    await expect(compactNavigation).toBeHidden();
    await expect(
      desktopNavigation.getByRole("link", { name: /resultados/i }),
    ).toBeVisible();

    await page.setViewportSize({ width: 320, height: 900 });
    await expect(desktopNavigation).toBeHidden();
    await expect(compactNavigation).toBeVisible();
    await compactNavigation.locator("summary").click();
    await expect(compactNavigation.locator("nav")).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
  });

  for (const home of [
    {
      locale: "es",
      heading: /presidencia 2026 · segunda vuelta/i,
      statistics: /comparación de candidaturas/i,
      skip: /saltar al contenido principal/i,
      results: /^resultados$/i,
    },
    {
      locale: "en",
      heading: /2026 presidential election · second round/i,
      statistics: /candidate comparison/i,
      skip: /skip to main content/i,
      results: /^results$/i,
    },
  ] as const) {
    test(`${home.locale} homepage shell reflows and remains operable at 200% zoom`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.goto(`/${home.locale}`);
      await page.evaluate(() => {
        document.body.style.zoom = "2";
      });

      const dimensions = await page.evaluate(() => ({
        client: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
      await expect(
        page.getByRole("heading", { level: 1, name: home.heading }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: home.statistics }),
      ).toBeVisible();

      const desktopNavigation = page.locator(
        '[data-shell-navigation="desktop"]',
      );
      const compactNavigation = page.locator(
        '[data-shell-navigation="compact"]',
      );
      await expect(desktopNavigation).toBeHidden();
      await expect(compactNavigation).toBeVisible();

      const skip = page.getByRole("link", { name: home.skip });
      await skip.focus();
      await skip.press("Enter");
      await expect(page.locator("#main-content")).toBeFocused();

      await compactNavigation.locator("summary").click();
      const compactMenu = compactNavigation.locator("nav");
      await expect(compactMenu).toBeVisible();
      const results = compactMenu.getByRole("link", { name: home.results });
      await expect(results).toHaveAttribute(
        "href",
        `/${home.locale}/resultados`,
      );
      await page.screenshot({
        path: `output/playwright/shell-home-${home.locale}-zoom-200.png`,
      });
    });
  }

  for (const width of [320, 375, 390, 768, 1024, 1280, 1440]) {
    test(`results reflows without horizontal document overflow at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/es/resultados");
      const dimensions = await page.evaluate(() => ({
        client: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      expect(
        dimensions.scroll,
        `document overflow at ${width}px`,
      ).toBeLessThanOrEqual(dimensions.client);
    });
  }

  for (const width of [320, 768, 1280]) {
    test(`analytics reflows without horizontal document overflow at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/es/analitica");
      const dimensions = await page.evaluate(() => ({
        client: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      expect(
        dimensions.scroll,
        `analytics document overflow at ${width}px`,
      ).toBeLessThanOrEqual(dimensions.client);
    });
  }

  test("200% zoom preserves the results heading and controls", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/es/resultados");
    await page.evaluate(() => {
      document.body.style.zoom = "2";
    });
    await expect(
      page.getByRole("heading", { name: /resultados por mesa/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("form", { name: /filtros de resultados/i }),
    ).toBeVisible();
  });

  test("200% zoom preserves the analytics reading order and actions", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/es/analitica");
    await page.evaluate(() => {
      document.body.style.zoom = "2";
    });
    await expect(
      page.getByRole("heading", { name: /portal de analítica electoral/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: /continuar la lectura/i }),
    ).toBeVisible();
  });

  test("security headers are present on public pages", async ({ request }) => {
    const response = await request.get("/es/resultados");
    expect(response.headers()["x-content-type-options"]).toBe("nosniff");
    expect(response.headers()["x-frame-options"]).toBe("DENY");
    expect(response.headers()["referrer-policy"]).toBe(
      "strict-origin-when-cross-origin",
    );
    expect(response.headers()["permissions-policy"]).toContain("camera=()");
    expect(
      response.headers()["content-security-policy-report-only"],
    ).not.toContain("upgrade-insecure-requests");
  });

  test("initial results route keeps MapLibre lazy and stays below the JavaScript budget", async ({
    page,
  }, testInfo) => {
    await page.goto("/es/resultados");
    const initial = await page.evaluate(() =>
      performance.getEntriesByType("resource").map((entry) => ({
        name: entry.name,
        encodedBodySize: (entry as PerformanceResourceTiming).encodedBodySize,
        transferSize: (entry as PerformanceResourceTiming).transferSize,
      })),
    );
    expect(initial.some((entry) => /maplibre/i.test(entry.name))).toBeFalsy();
    const jsBytes = initial
      .filter((entry) => /\/_next\/.*\.js(?:\?|$)/.test(entry.name))
      .reduce((sum, entry) => sum + entry.encodedBodySize, 0);
    testInfo.annotations.push({
      type: "initial-js-encoded-body",
      description: `${jsBytes} bytes against a 200 KiB compressed-body budget.`,
    });
    expect(jsBytes).toBeGreaterThan(0);
    expect(jsBytes).toBeLessThan(200 * 1024);
  });

  test("analytics stays server-rendered and below the initial JavaScript budget", async ({
    page,
  }, testInfo) => {
    await page.goto("/es/analitica");
    const initial = await page.evaluate(() =>
      performance.getEntriesByType("resource").map((entry) => ({
        name: entry.name,
        encodedBodySize: (entry as PerformanceResourceTiming).encodedBodySize,
      })),
    );
    expect(initial.some((entry) => /maplibre/i.test(entry.name))).toBeFalsy();
    const jsBytes = initial
      .filter((entry) => /\/_next\/.*\.js(?:\?|$)/.test(entry.name))
      .reduce((sum, entry) => sum + entry.encodedBodySize, 0);
    testInfo.annotations.push({
      type: "analytics-initial-js-encoded-body",
      description: `${jsBytes} bytes against a 200 KiB compressed-body budget.`,
    });
    expect(jsBytes).toBeGreaterThan(0);
    expect(jsBytes).toBeLessThan(200 * 1024);
  });
});
