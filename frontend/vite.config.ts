import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

const apiPaths = [
  "/workforce",
  "/legacy-import",
  "/domains",
  "/reports",
  "/recruitment",
  "/employee-portal",
  "/performance",
  "/access",
  "/auth",
  "/companies",
  "/branches",
  "/departments",
  "/job-titles",
  "/document-categories",
  "/leave-types",
  "/public-holidays",
  "/leave-balances",
  "/leave-requests",
  "/documents",
  "/employees",
  "/lifecycle",
  "/audit-logs",
  "/attendance",
  "/payroll",
  "/deduction-types",
  "/benefit-types",
  "/countries",
  "/platform",
  "/health",
] as const;

const apiPrefixes = apiPaths.map((path) => new RegExp(`^${path}`));
const apiProxy = Object.fromEntries(apiPaths.map((path) => [path, { target: "http://localhost:8000", changeOrigin: false }]));
const apiRuntime = new RegExp(
  `^\\/(?:${apiPaths.map((path) => path.slice(1)).join("|")})(?:\\/|$)`,
);

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: false,
      includeAssets: ["icons/icon.svg"],
      manifest: {
        id: "/app",
        name: "HRMS",
        short_name: "HRMS",
        description: "Workspace HR for your company",
        start_url: "/app",
        scope: "/",
        display: "standalone",
        background_color: "#f8fafc",
        theme_color: "#4f46e5",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/icon-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
        shortcuts: [
          {
            name: "Employees",
            short_name: "People",
            url: "/app/people",
            icons: [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
          },
          {
            name: "Add employee",
            short_name: "Add",
            url: "/app/people/new",
            icons: [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
          },
        ],
      },
      workbox: {
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        navigateFallback: "/index.html",
        navigateFallbackDenylist: apiPrefixes,
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"],
        runtimeCaching: [
          {
            urlPattern: apiRuntime,
            handler: "NetworkOnly",
          },
          {
            urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/i,
            handler: "StaleWhileRevalidate",
            options: { cacheName: "hrms-fonts" },
          },
        ],
      },
      devOptions: {
        enabled: true,
        navigateFallbackAllowlist: [/^\/$/, /^\/app(?:\/|$)/, /^\/employee(?:\/|$)/],
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
    allowedHosts: [".hrms.techtutor.co.ke",".ngrok-free.app", ".ngrok-free.dev", ".ngrok.app", ".ngrok.io", ".ngrok.dev"],
    proxy: apiProxy,
  },
});
