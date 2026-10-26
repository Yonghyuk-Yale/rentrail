import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev only: the UI runs on 5460 and forwards /api to the Rentrail server on 8460.
// In production the server itself serves the built files (frontend/dist), so there is one port.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5460,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8460" },
  },
});
