import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command:
        "ACE_CORS_ORIGINS=http://127.0.0.1:3100 python3 -m uvicorn app.main:app --app-dir ../../services/api --port 8100",
      url: "http://127.0.0.1:8100/health",
      reuseExistingServer: false,
    },
    {
      command:
        "NEXT_PUBLIC_API_URL=http://127.0.0.1:8100 npm run dev -- --hostname 127.0.0.1 --port 3100",
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
    }
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
