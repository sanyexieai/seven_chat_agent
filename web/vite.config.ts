import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 18738,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:18737",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:18737",
        ws: true,
        changeOrigin: true,
      },
      "/ws-api": {
        target: "ws://127.0.0.1:18737",
        ws: true,
        changeOrigin: true,
      },
      "/cli-relay": {
        target: "ws://127.0.0.1:18737",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
