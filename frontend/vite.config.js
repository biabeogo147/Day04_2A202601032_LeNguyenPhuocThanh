import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        fs: {
            allow: [fileURLToPath(new URL("..", import.meta.url))],
        },
        proxy: {
            "/api": "http://127.0.0.1:8000",
        },
    },
    test: {
        environment: "jsdom",
        setupFiles: "./src/test/setup.ts",
        include: ["src/**/*.test.{ts,tsx}"],
    },
});
