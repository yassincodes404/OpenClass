import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/control": "http://127.0.0.1:7400" } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replaceAll("\\", "/");
          if (normalizedId.includes("node_modules")) {
            if (
              normalizedId.includes("/react/") ||
              normalizedId.includes("/react-dom/") ||
              normalizedId.includes("/react-router") ||
              normalizedId.includes("/scheduler/")
            ) {
              return "vendor-react";
            }
            if (
              normalizedId.includes("keycloak-js") ||
              normalizedId.includes("@tanstack/react-query") ||
              normalizedId.includes("@tanstack/query-core") ||
              normalizedId.includes("zustand")
            ) {
              return "vendor-auth";
            }
            if (
              normalizedId.includes("zod") ||
              normalizedId.includes("react-hook-form") ||
              normalizedId.includes("@hookform/resolvers")
            ) {
              return "vendor-forms";
            }
          }
          if (
            normalizedId.includes("observatory-sections.tsx") ||
            normalizedId.includes("open-world-stage.tsx")
          ) {
            return "observatory-sections";
          }
          if (normalizedId.includes("/src/analytics.tsx")) {
            return "analytics-pages";
          }
          return undefined;
        },
      },
    },
  },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});
