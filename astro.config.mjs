import node from "@astrojs/node";
import react from "@astrojs/react";
import tailwind from "@astrojs/tailwind";
import { defineConfig } from "astro/config";

const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  output: "server",
  adapter: node({ mode: "standalone" }),
  integrations: [react(), tailwind({ applyBaseStyles: false })],
  devToolbar: {
    enabled: process.env.E2E_TEST_MODE !== "true",
  },
  vite: {
    build: {
      // Mermaid publishes optional diagram engines as lazy vendor chunks.
      chunkSizeWarningLimit: 1500,
    },
    server: {
      proxy: {
        "/api": apiProxyTarget,
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 4321,
  },
});
