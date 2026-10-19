import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    watch: {
      awaitWriteFinish: { stabilityThreshold: 200, pollInterval: 50 },
    },
    proxy: {
      "/api":
        loadEnv(mode, ".", "").LYRICLENS_API_URL || "http://127.0.0.1:8011",
    },
  },
}));
