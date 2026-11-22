import { defineConfig } from "vitest/config";

// Unit tests for the web app's helpers and components; React's automatic JSX runtime.
export default defineConfig({
  esbuild: { jsx: "automatic" },
  test: { include: ["tests/**/*.test.{ts,tsx}"], environment: "node" },
});
