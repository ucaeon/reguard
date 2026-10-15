import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.jsx"],
    setupFiles: ["./tests/setup.js"],
    environmentOptions: { jsdom: { url: "http://localhost:3000/" } },
  },
});
