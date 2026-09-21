const { defineConfig, devices } = require("@playwright/test");
module.exports = defineConfig({
  testDir: "./tests/browser",
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8765", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: {
    command: `${process.env.PYTHON || ".venv/bin/python"} -m uvicorn main:app --host 127.0.0.1 --port 8765`,
    url: "http://127.0.0.1:8765/health",
    reuseExistingServer: false,
    env: {
      LINGOLYRICS_LOAD_ENV: "0",
      LINGOLYRICS_PREFERENCES: "test-results/preferences.json",
      SPOTIPY_CLIENT_ID: "",
      SPOTIPY_CLIENT_SECRET: "",
      SPOTIPY_REDIRECT_URI: "",
      GEMINI_API_KEY: "",
      GOOGLE_API_KEY: "",
      OPENROUTER_API_KEY: "",
    },
  },
});
