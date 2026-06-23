import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// For the optional local-dev path (`npm run dev`), proxy /api to nginx (8080)
// so the browser talks to the same origin it would in Docker.
const API_TARGET = process.env.VITE_API_TARGET || "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
});
