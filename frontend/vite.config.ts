import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En développement, les appels /api sont redirigés vers l'API locale.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});
