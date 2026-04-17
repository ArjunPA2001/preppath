import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API = "http://localhost:8000";
const proxyPaths = [
  "/users",
  "/candidates",
  "/sessions",
  "/assessments",
  "/questions",
  "/pipelines",
];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      proxyPaths.map((p) => [p, { target: API, changeOrigin: true }])
    ),
  },
});
