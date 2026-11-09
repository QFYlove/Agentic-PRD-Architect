// V4 design prototype. Isolated from the production Astro app in src/ and
// from design-preview/v3: own entry, own styles, mock data only. No API calls.
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 4342,
    strictPort: true,
  },
  preview: {
    host: "127.0.0.1",
    port: 4342,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
