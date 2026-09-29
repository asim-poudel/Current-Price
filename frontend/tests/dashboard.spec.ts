import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:4010/__test/mode/healthy");
});

test("forecast cards, table, Q&A, palette, and responsive layout", async ({ page }) => {
  await page.goto("/");

  const title = page.getByRole("heading", { name: "Current Price" });
  await expect(title).toBeVisible();
  await expect(title).toHaveCSS("color", "rgb(42, 89, 69)");
  const icon = title.locator(".title-icon");
  await expect(icon).toBeVisible();
  const desktopIcon = await icon.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return { width: box.width, height: box.height, fontSize: Number.parseFloat(getComputedStyle(element.closest("h1")!).fontSize) };
  });
  expect(Math.abs(desktopIcon.width - desktopIcon.fontSize)).toBeLessThan(1);
  expect(Math.abs(desktopIcon.height - desktopIcon.fontSize)).toBeLessThan(1);
  const cornerAlpha = await icon.evaluate(async (element) => {
    const image = element as HTMLImageElement;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    return context.getImageData(0, 0, 1, 1).data[3];
  });
  expect(cornerAlpha).toBe(0);
  await expect(page.getByText("Germany - Day-ahead market")).toHaveCSS("color", "rgb(64, 126, 140)");
  await expect(page.getByText(/Current Price uses recent SMARD market and grid data/)).toBeVisible();
  await expect(page.getByTestId("model-card")).toContainText("CNN LSTM");
  await expect(page.locator(".status-grid .meta-card")).toHaveCount(3);
  await expect(page.locator("section.dashboard-card")).toHaveCount(4);
  const metricCards = page.locator(".evaluation .metrics > .metric, .evaluation .metrics > .worst");
  await expect(metricCards).toHaveCount(5);
  expect(await metricCards.evaluateAll((cards) => cards.every((card) => getComputedStyle(card).boxShadow !== "none"))).toBe(true);

  const gridStyle = await page.evaluate(() => ({ image: getComputedStyle(document.body, "::before").backgroundImage, size: getComputedStyle(document.body, "::before").backgroundSize }));
  expect(gridStyle.image).toContain("0.067");
  expect(gridStyle.size).toBe("32px 32px, 32px 32px");

  const table = page.getByRole("table");
  await expect(table).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Berlin time (CEST +02:00)" })).toHaveCSS("color", "rgb(0, 78, 114)");
  await expect(page.getByRole("columnheader", { name: "Horizon" })).toHaveCount(0);
  await expect(page.getByRole("columnheader", { name: "Zone" })).toHaveCount(0);
  await expect(page.locator("tbody tr")).toHaveCount(24);
  await expect(page.getByRole("cell", { name: "-4.25" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hourly forecast" })).toHaveCSS("color", "rgb(9, 38, 52)");

  const desktopScroll = page.getByRole("region", { name: "Scrollable hourly electricity price forecast" });
  const desktopDimensions = await desktopScroll.evaluate((element) => ({ clientHeight: element.clientHeight, scrollHeight: element.scrollHeight, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }));
  expect(desktopDimensions.scrollHeight).toBeGreaterThan(desktopDimensions.clientHeight);
  expect(desktopDimensions.scrollWidth).toBe(desktopDimensions.clientWidth);

  await page.getByLabel("Question").fill("What was yesterday's MAE?");
  const askButton = page.getByRole("button", { name: "Ask" });
  await expect(askButton).toHaveCSS("background-color", "rgb(157, 208, 182)");
  await expect(askButton).toHaveCSS("color", "rgb(9, 38, 52)");
  await askButton.click();
  await expect(page.getByText("Yesterday's MAE was 5.20 EUR/MWh.")).toBeVisible();
  await expect(page.getByText("dynamic:previous_evaluation")).toBeVisible();
  await expect(page.locator("footer")).toHaveText("• notjustauser • DATA SOURCE: SMARD");

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileIcon = await icon.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return { width: box.width, height: box.height, fontSize: Number.parseFloat(getComputedStyle(element.closest("h1")!).fontSize) };
  });
  expect(Math.abs(mobileIcon.width - mobileIcon.fontSize)).toBeLessThan(1);
  expect(Math.abs(mobileIcon.height - mobileIcon.fontSize)).toBeLessThan(1);
  await expect(table).toBeHidden();
  const mobileScroll = page.getByRole("region", { name: "Scrollable hourly electricity price cards" });
  await expect(mobileScroll).toBeVisible();
  const mobileRows = page.getByRole("list", { name: "All 24 hourly forecast values" }).getByRole("listitem");
  await expect(mobileRows).toHaveCount(24);
  const mobileBounds = await mobileScroll.evaluate((region) => {
    const rows = [...region.querySelectorAll("li")];
    const regionBox = region.getBoundingClientRect();
    return {
      clientHeight: region.clientHeight,
      scrollHeight: region.scrollHeight,
      sixthBottom: rows[5].getBoundingClientRect().bottom,
      seventhTop: rows[6].getBoundingClientRect().top,
      regionBottom: regionBox.bottom,
    };
  });
  expect(mobileBounds.scrollHeight).toBeGreaterThan(mobileBounds.clientHeight);
  expect(mobileBounds.sixthBottom).toBeLessThanOrEqual(mobileBounds.regionBottom + 1);
  expect(mobileBounds.seventhTop).toBeGreaterThanOrEqual(mobileBounds.regionBottom);
  const mobileMetaCards = await page.locator(".meta-card").evaluateAll((cards) => cards.map((card) => card.getBoundingClientRect()).map(({ x, y, width }) => ({ x, y, width })));
  expect(mobileMetaCards[1].y).toBeGreaterThan(mobileMetaCards[0].y);
  expect(Math.abs(mobileMetaCards[0].width - mobileMetaCards[1].width)).toBeLessThan(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(table).toBeVisible();
  await expect(mobileScroll).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(768);
  const tabletDimensions = await desktopScroll.evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }));
  expect(tabletDimensions.scrollWidth).toBe(tabletDimensions.clientWidth);
});

test("uses winter and mixed DST table headings", async ({ page, request }) => {
  await request.post("http://127.0.0.1:4010/__test/mode/winter");
  await page.goto("/");
  await expect(page.getByRole("columnheader", { name: "Berlin time (CET +01:00)" })).toBeVisible();

  await request.post("http://127.0.0.1:4010/__test/mode/mixed");
  await page.goto("/");
  await expect(page.getByRole("columnheader", { name: "Berlin time (CET/CEST)" })).toBeVisible();
  await expect(page.locator(".inline-zone").first()).toHaveText("CET");
  await expect(page.locator(".inline-zone").nth(1)).toHaveText("CEST");
});

test("shows a boxed database degradation state", async ({ page, request }) => {
  await request.post("http://127.0.0.1:4010/__test/mode/degraded");
  await page.goto("/");
  await expect(page.getByText("Database unavailable", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Ask" })).toBeDisabled();
  await expect(page.getByText("Questions are unavailable until the database is connected.")).toBeVisible();
  await expect(page.locator(".service-notice")).toBeVisible();
});

test("handles incompatible, unavailable, and empty backends", async ({ page, request }) => {
  await request.post("http://127.0.0.1:4010/__test/mode/incompatible");
  await page.goto("/");
  await expect(page.getByText("Wrong backend is running", { exact: true })).toBeVisible();

  await request.post("http://127.0.0.1:4010/__test/mode/unavailable");
  await page.goto("/");
  await expect(page.getByText("Backend unavailable", { exact: true })).toBeVisible();

  await request.post("http://127.0.0.1:4010/__test/mode/empty");
  await page.goto("/");
  await expect(page.getByText("Awaiting first forecast", { exact: true })).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
});
