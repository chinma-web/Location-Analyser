import { test as base, expect, chromium } from "@playwright/test";
// Isolated browser per test also supports single-process Chromium in sandboxes.
const test = base.extend({
  page: async ({ baseURL, launchOptions }, use) => {
    const browser = await chromium.launch(launchOptions);
    try {
      const page = await browser.newPage({
        baseURL,
        viewport: { width: 1440, height: 1050 },
        acceptDownloads: true,
      });
      await use(page);
    } finally {
      await browser.close();
    }
  },
});
import fs from "node:fs/promises";

const sections = [
  ["Executive verdict", "Balanced assessment"],
  ["Deep sentiment", "Emotion distribution"],
  ["Authenticity", "Linguistic analysis"],
  ["Visitor guide", "Actionable visitor tips"],
  ["Verification & audit", "Field-by-field cross-verification"],
  ["Raw data & export", "Scraped reviews"],
];
async function open(page) {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "The Courtyard Café", exact: true }),
  ).toBeVisible();
}

test("all six original report sections, charts, metadata and evidence navigation", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page);
  await page.locator(".report-metadata:not(.content-coverage) summary").click();
  await expect(page.getByText("Monday–Friday:")).toBeVisible();
  for (const [tab, heading] of sections) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
  }
  await page.getByRole("tab", { name: "Deep sentiment", exact: true }).click();
  await expect(page.locator(".recharts-surface").first()).toBeVisible();
  const chartDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download chart SVG" })
    .first()
    .click();
  expect((await chartDownload).suggestedFilename()).toMatch(/\.svg$/);
  await expect(
    page.getByRole("heading", { name: "Temporal sentiment trend" }),
  ).toBeVisible();
  await page
    .getByRole("tab", { name: "Verification & audit", exact: true })
    .click();
  await page.getByRole("button", { name: "Read 2 linked reviews" }).click();
  await expect(page.locator(".review")).toHaveCount(2);
  expect(errors).toEqual([]);
});

test("raw reviews search, sorting, pagination, CSV and lossless JSON export", async ({
  page,
}) => {
  await open(page);
  await page
    .getByRole("tab", { name: "Raw data & export", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Search raw reviews" })
    .fill("Saturday");
  await expect(page.locator(".report-table tbody tr")).toHaveCount(1);
  const csvPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download reviews CSV" }).click();
  const csv = await fs.readFile(await (await csvPromise).path(), "utf8");
  expect(csv).toContain("Saturday");
  expect(csv).not.toContain("weekday mornings");
  await page.getByRole("textbox", { name: "Search raw reviews" }).fill("");
  await page.getByRole("button", { name: /Rating ↕/ }).click();
  await expect(page.locator(".report-table tbody tr").first()).toContainText(
    "Very crowded",
  );
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.locator(".report-table tbody tr")).toHaveCount(2);
  const jsonPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download full report (.json)" })
    .click();
  const data = JSON.parse(
    await fs.readFile(await (await jsonPromise).path(), "utf8"),
  );
  expect(data.guardrail.linguistic_analysis).toBeDefined();
  expect(data.sentiment.emotion_distribution).toBeDefined();
  expect(data.verification.corrections).toHaveLength(1);
});

test("custom review limit reaches the live request", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Analysis settings" }).click();
  const slider = page.getByRole("slider", { name: /Max reviews/ });
  await slider.press("End");
  await expect(slider).toHaveValue("100");
  await page
    .getByRole("button", { name: "Live analysis", exact: true })
    .click();
  await page.getByRole("button", { name: "Paste Maps link" }).click();
  await page
    .getByRole("textbox", { name: "GOOGLE MAPS URL" })
    .fill("https://maps.app.goo.gl/example");
  let payload;
  await page.route("**/api/analyze", (r) => {
    payload = r.request().postDataJSON();
    return r.fulfill({
      status: 503,
      json: { detail: "Mocked submission accepted" },
    });
  });
  await page.getByRole("button", { name: "Analyze place" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  expect(payload.max_reviews).toBe(100);
});

test("all original report sections fit a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  for (const [tab, heading] of sections) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("partial unavailable reports never become fabricated successful audits", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/demo", (r) =>
    r.fulfill({
      json: {
        location: "Partial report",
        place_info: { name: "Partial report" },
        reviews: [],
        sentiment: {},
        recommendation: {},
        verification: { status: "UNAVAILABLE", accuracy: null },
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Partial report", exact: true }),
  ).toBeVisible();
  for (const [tab, heading] of sections) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
  }
  await expect(page.locator("body")).not.toContainText("94%");
  await expect(page.locator(".report-status-strip")).toContainText(
    "UNAVAILABLE",
  );
  expect(errors).toEqual([]);
});

test("coverage and every extracted topic remain visible in verdict and visitor guidance", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const response = await page.request.get("http://127.0.0.1:8000/api/demo");
  const report = await response.json();
  await page.goto("/");
  await page.locator(".content-coverage summary").click();
  await expect(page.locator(".content-coverage")).toContainText(
    "12 / 12 reviews analyzed",
  );
  await expect(page.locator(".content-coverage")).toContainText("0 / 12");
  await page
    .getByRole("tab", { name: "Executive verdict", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Topic-by-topic assessment",
      exact: true,
    }),
  ).toBeVisible();
  const titles = report.sentiment.topic_inventory.map((t) =>
    t.topic.replaceAll("_", " "),
  );
  for (const title of titles)
    await expect(
      page
        .locator(".report-theme h3")
        .filter({ hasText: new RegExp(`^${title}$`, "i") })
        .first(),
    ).toBeVisible();
  await page.getByRole("tab", { name: "Deep sentiment", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Complete topic evidence inventory",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Visitor guide", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Topic-by-topic visitor guidance",
      exact: true,
    }),
  ).toBeVisible();
  for (const title of titles)
    await expect(
      page
        .locator(".report-theme h3")
        .filter({ hasText: new RegExp(`^${title}$`, "i") })
        .first(),
    ).toBeVisible();
  expect(errors).toEqual([]);
});
