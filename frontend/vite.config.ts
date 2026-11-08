// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// Never set ssr.external or resolve.external: the Worker has no runtime module resolution, so
// the build fails. Never add compression (compressPublicAssets, vite-plugin-compression):
// hosting already compresses at the edge.
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// Backends run separately. In dev the browser talks to one Vite origin; paths are proxied.
//   /api/v1/*  → PNC customer API on the same server (override with PNC_API_URL; default :8010)
//   /api/*     → Learn API (override with LEARN_API_URL; default :8010; /api prefix stripped)
const pncApi = process.env["PNC_API_URL"] ?? "http://127.0.0.1:8010";
const learnApi = process.env["LEARN_API_URL"] ?? "http://127.0.0.1:8010";

export default defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  vite: {
    server: {
      proxy: {
        "/api/v1": {
          target: pncApi,
        },
        "/api": {
          target: learnApi,
          rewrite: (path: string) => path.replace(/^\/api/, ""),
        },
      },
    },
  },
});
