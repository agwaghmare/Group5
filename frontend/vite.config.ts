// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// Never set ssr.external or resolve.external: the Worker has no runtime module resolution, so
// the build fails. Never add compression (compressPublicAssets, vite-plugin-compression):
// hosting already compresses at the edge.
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { createRequire } from "node:module";
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

const require = createRequire(import.meta.url);
const bufferPath = require.resolve("buffer/");

function polyfillNodeBuffer() {
  return {
    name: "polyfill-node-buffer",
    enforce: "pre" as const,
    resolveId(id: string) {
      if (id === "node:buffer" || id === "buffer") return bufferPath;
      return null;
    },
  };
}

// Backends run separately. In dev the browser talks to one Vite origin; paths are proxied.
//   /api/v1/*  → PNC customer + auth API (override with PNC_API_URL; default :8002)
//   /api/*     → Learn API on the same server (override with LEARN_API_URL; default :8002; /api prefix stripped)
const pncApi = process.env["PNC_API_URL"] ?? "http://127.0.0.1:8002";
const learnApi = process.env["LEARN_API_URL"] ?? "http://127.0.0.1:8002";

export default defineConfig({
  plugins: [polyfillNodeBuffer()],
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  vite: {
    define: {
      global: "globalThis",
    },
    resolve: {
      alias: {
        "node:buffer": bufferPath,
        buffer: bufferPath,
      },
    },
    optimizeDeps: {
      include: ["buffer", "@solana/web3.js", "@solana/spl-token"],
      esbuildOptions: {
        define: {
          global: "globalThis",
        },
      },
    },
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
