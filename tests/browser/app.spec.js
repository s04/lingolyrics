const { test, expect } = require("@playwright/test");

test("demo, repeated swaps, reader controls and export", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Try the demo/ }).click();
  await expect(
    page.getByRole("heading", { name: "Une fenêtre ouverte" }),
  ).toBeVisible();
  await expect(page.locator(".lyric-line")).toHaveCount(6);
  await page
    .getByRole("checkbox", { name: "Translations", exact: true })
    .uncheck();
  await expect(page.locator(".translation-line").first()).toBeHidden();
  await page
    .getByRole("checkbox", { name: "Translations", exact: true })
    .check();
  await page
    .getByRole("checkbox", { name: "Pronunciation", exact: true })
    .uncheck();
  await expect(page.locator(".phonetics").first()).toBeHidden();
  await page.getByRole("button", { name: "Toggle focus mode" }).click();
  await expect(page.locator(".sidebar")).toBeHidden();
  await page.getByRole("button", { name: "Toggle focus mode" }).click();
  await page.getByRole("button", { name: "Play demo timer" }).click();
  await expect(
    page.getByRole("button", { name: "Pause demo timer" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pause demo timer" }).click();
  await expect(page.locator("#playback-status")).toContainText("paused");
  for (let i = 0; i < 3; i++) {
    await page.getByRole("button", { name: /Try the demo/ }).click();
    await expect(page.locator(".lyric-line")).toHaveCount(6);
    await page.getByRole("button", { name: "Add IPA" }).click();
    await expect(page.locator(".phonetics")).toHaveCount(6);
  }
  await page.getByRole("button", { name: "Copy lyrics" }).click();
  await expect(page.locator("#notice")).toContainText("Lyrics copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "La lumière",
  );
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download lyrics" }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("lingolyrics.txt");
  expect(errors).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("language filter, saved settings, custom provider and failure state", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByPlaceholder("Search languages…").fill("French");
  await expect(page.locator(".language-option:visible")).toHaveCount(1);
  await page.getByRole("checkbox", { name: "French" }).check();
  await page
    .getByLabel("Translation model", { exact: true })
    .selectOption("openrouter/custom");
  await page.getByLabel("OpenRouter model ID").fill("provider/model");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.locator("#settings-status")).toContainText(
    "Settings saved.",
  );
  await page.reload();
  await expect(page.getByRole("checkbox", { name: "French" })).toBeChecked();
  await expect(page.getByLabel("OpenRouter model ID")).toHaveValue(
    "provider/model",
  );
  await page.getByRole("button", { name: /Try the demo/ }).click();
  await page.getByRole("button", { name: "Load from Spotify" }).click();
  await expect(page.locator("#notice")).toContainText("Spotify credentials");
  await expect(page.locator(".lyric-line")).toHaveCount(6);
});

test("welcome and lyric reader have no serious accessibility violations", async ({
  page,
}) => {
  const AxeBuilder = require("@axe-core/playwright").default;
  await page.goto("/");
  for (const demo of [false, true]) {
    if (demo) {
      await page.getByRole("button", { name: /Try the demo/ }).click();
      await expect(page.locator(".lyric-line")).toHaveCount(6);
    }
    const result = await new AxeBuilder({ page }).analyze();
    expect(
      result.violations
        .filter((item) => ["serious", "critical"].includes(item.impact))
        .map((item) => ({
          id: item.id,
          nodes: item.nodes.map((node) => ({
            target: node.target,
            message: node.failureSummary,
          })),
        })),
    ).toEqual([]);
  }
});
