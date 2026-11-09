// V3 visual prototype. Isolated from the production Astro app in src/:
// it has its own entry, its own styles and only mock data. No API calls.
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 4341,
    strictPort: true,
  },
  preview: {
    host: "127.0.0.1",
    port: 4341,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
