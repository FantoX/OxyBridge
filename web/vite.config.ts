import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: Object.fromEntries(
      ["/api", "/hooks", "/health", "/metrics", "/docs", "/openapi.json"].map(
        (path) => [path, "http://127.0.0.1:8000"],
      ),
    ),
  },
});
