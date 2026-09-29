import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  use: { baseURL: "http://127.0.0.1:13001", trace: "retain-on-failure" },
  webServer: [
    { command: "node tests/mock-api.mjs", port: 4010, reuseExistingServer: false },
    { command: "npm run build && npm run start -- --hostname 127.0.0.1 --port 13001", port: 13001, reuseExistingServer: false, env: { ...process.env, NEXT_DIST_DIR: ".next-e2e", NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:4010" } },
  ],
});
