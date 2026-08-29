import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function authenticate(page: import("@playwright/test").Page) {
  await page.goto("/");
  await expect(page.getByLabel("Active runtime contract")).toContainText("Semantic");
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

test("guided judge tour explains approve, step-up, and hold", async ({ page }) => {
  await page.goto("/");
  if (process.env.ACE_E2E_MODEL_MODE !== "development_artifact") {
    await expect(page.getByText(/lightweight public demo · deterministic runtime/i)).toBeVisible();
  }
  const businessValue = page.getByLabel("Business value");
  await expect(businessValue).toContainText("Protection");
  await expect(businessValue).toContainText("Growth");
  await expect(businessValue).toContainText("Productivity");

  const tour = page.getByLabel("Guided judge tour");
  await tour.getByRole("button", { name: /start 90-second guided demo/i }).click();
  await tour.getByRole("button", { name: /confirm authenticated mandate/i }).click();
  await tour.getByRole("button", { name: /run matching purchase/i }).click();
  await expect(page.getByRole("heading", { name: "Approved" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /confirmed mandate vs proposed outcome/i })).toBeVisible();

  await tour.getByRole("button", { name: /change refundability/i }).click();
  await expect(page.getByRole("heading", { name: /confirmation needed/i })).toBeVisible();
  await expect(page.getByText(/refundability changed from a required term/i)).toBeVisible();

  await tour.getByRole("button", { name: /inject prohibited add-on/i }).click();
  await expect(page.getByRole("heading", { name: /held for protection/i })).toBeVisible();
  await expect(page.getByText(/gift-card subscription was inserted/i)).toBeVisible();
  await expect(tour.getByRole("button", { name: /explore all six scenarios/i })).toBeVisible();
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
  if (process.env.ACE_E2E_MODEL_MODE === "development_artifact") {
    await page.getByText("Inspect decision evidence").click();
    await expect(page.getByLabel("Semantic model results")).toBeVisible();
    const contract = page.getByLabel("Decision runtime contract");
    await expect(contract).toContainText("english-nli-v3");
    await expect(contract).toContainText("catboost-v1");
    await expect(contract).toContainText("platt-calibrator-v3");
    await expect(contract).toContainText("0.7599");
    await expect(contract).toContainText("LOCKED_NON_PROMOTABLE");
    await expect(contract).toContainText("Ed25519 verified");
  }
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
