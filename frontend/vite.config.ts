import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { apiFinte } from "./dev/mock-api.ts";

// In sviluppo /api/* e' simulato da dev/mock-api.ts (nessun Cloudflare). In produzione
// lo serve il Worker (worker/index.ts), configurato in wrangler.jsonc.
export default defineConfig({
  plugins: [react(), tailwindcss(), apiFinte()],
  build: { outDir: "dist", sourcemap: false },
});
