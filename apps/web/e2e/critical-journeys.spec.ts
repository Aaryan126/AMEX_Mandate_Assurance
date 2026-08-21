import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function authenticate(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /interpret mandate/i }).click();
  await expect(page.getByText(/total budget/i)).toBeVisible();
  await page.getByRole("button", { name: /confirm & authenticate/i }).click();
  await expect(page.getByRole("button", { name: /valid itinerary/i })).toBeEnabled();
}

test("valid merchant evidence is approved", async ({ page }) => {
  await authenticate(page);
  await page.getByRole("button", { name: /valid itinerary/i }).click();
  await expect(page.getByRole("heading", { name: "Approved" })).toBeVisible();
});

test("budget breach steps up and can be resolved", async ({ page }) => {
  await authenticate(page);
  await page.getByRole("button", { name: /budget breach/i }).click();
  await expect(page.getByRole("heading", { name: /confirmation needed/i })).toBeVisible();
  await page.getByRole("button", { name: /approve once/i }).click();
  await expect(page.getByText(/approved once by the card member/i)).toBeVisible();
});

test("semantic substitution escalates without a model-only hold", async ({ page }) => {
  await authenticate(page);
  await page.getByRole("button", { name: /semantic substitution/i }).click();
  await expect(page.getByRole("heading", { name: /confirmation needed/i })).toBeVisible();
  await expect(page.getByLabel("Decision reasons").getByText("REQUIRED_ATTRIBUTE_CONTRADICTED")).toBeVisible();
});

test("scenario isolation keeps earlier approvals from changing later outcomes", async ({ page }) => {
  await authenticate(page);
  await page.getByRole("button", { name: /valid itinerary/i }).click();
  await expect(page.getByRole("heading", { name: "Approved" })).toBeVisible();
  await page.getByRole("button", { name: /semantic substitution/i }).click();
  await expect(page.getByRole("heading", { name: /confirmation needed/i })).toBeVisible();
});

for (const [scenario, reason] of [
  ["Injected add-on", "EXPLICIT_PROHIBITED_ITEM_OR_CATEGORY"],
  ["Cumulative breach", "CUMULATIVE_BUDGET_EXCEEDED"],
] as const) {
  test(`${scenario} is held`, async ({ page }) => {
    await authenticate(page);
    await page.getByRole("button", { name: new RegExp(scenario, "i") }).click();
    await expect(page.getByRole("heading", { name: /held for protection/i })).toBeVisible();
    await expect(page.getByLabel("Decision reasons").getByText(reason)).toBeVisible();
    if (scenario === "Cumulative breach") {
      await expect(page.getByText("First fulfillment")).toBeVisible();
      await expect(page.getByText("Second fulfillment")).toBeVisible();
      await expect(page.getByText("S$500.00")).toHaveCount(2);
    }
  });
}

test("missing evidence requests confirmation", async ({ page }) => {
  await authenticate(page);
  await page.getByRole("button", { name: /missing evidence/i }).click();
  await expect(page.getByRole("heading", { name: /confirmation needed/i })).toBeVisible();
  await expect(page.getByLabel("Decision reasons").getByText("REQUIRED_ATTRIBUTE_EVIDENCE_MISSING")).toBeVisible();
});

test("a step-up can enter the mandate replacement workflow", async ({ page }) => {
  await authenticate(page);
  await page.getByRole("button", { name: /budget breach/i }).click();
  await expect(page.getByRole("heading", { name: /confirmation needed/i })).toBeVisible();
  await page.getByRole("button", { name: /modify mandate/i }).click();
  await expect(page.getByText(/revise the objective/i)).toBeVisible();
  await page.getByLabel(/what should the agent purchase/i).fill(
    "Book a refundable economy flight from Singapore to Tokyo, departing 7 September and returning 10 September, nonstop if available, total fare under S$1,000. Do not purchase add-ons.",
  );
  await page.getByRole("button", { name: /interpret mandate/i }).click();
  await page.getByRole("button", { name: /confirm modified mandate/i }).click();
  await expect(page.getByText(/modified mandate confirmed and authenticated/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /valid itinerary/i })).toBeEnabled();
});

test("development v3 evidence is labeled with its failed promotion status", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /load benchmark results/i }).click();
  await expect(page.getByText("0.9667")).toBeVisible();
  await expect(page.getByText("79.93%")).toBeVisible();
  await expect(page.getByText(/LOCKED_NON_PROMOTABLE/)).toBeVisible();
  await expect(page.getByText(/two recall gates prevent promotion/i)).toBeVisible();
});

test("authenticated workspace has no serious accessibility violations", async ({ page }) => {
  await authenticate(page);
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter((violation) =>
      ["serious", "critical"].includes(violation.impact ?? ""),
    ),
  ).toEqual([]);
});
