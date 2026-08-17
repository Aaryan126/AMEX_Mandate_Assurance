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
  await expect(page.getByText("REQUIRED_ATTRIBUTE_CONTRADICTED")).toBeVisible();
});

for (const [scenario, reason] of [
  ["Injected add-on", "PROHIBITED_OR_UNRELATED_ITEM"],
  ["Cumulative breach", "CUMULATIVE_BUDGET_EXCEEDED"],
] as const) {
  test(`${scenario} is held`, async ({ page }) => {
    await authenticate(page);
    await page.getByRole("button", { name: new RegExp(scenario, "i") }).click();
    await expect(page.getByRole("heading", { name: /held for protection/i })).toBeVisible();
    await expect(page.getByText(reason)).toBeVisible();
  });
}

test("missing evidence requests confirmation", async ({ page }) => {
  await authenticate(page);
  await page.getByRole("button", { name: /missing evidence/i }).click();
  await expect(page.getByRole("heading", { name: /confirmation needed/i })).toBeVisible();
  await expect(page.getByText("REQUIRED_ATTRIBUTE_EVIDENCE_MISSING")).toBeVisible();
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
