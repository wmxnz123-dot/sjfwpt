# Prototype Adapters

Use the simplest adapter that keeps behavior consistent across prototype types:
write annotation data and runtime assets into the original project by default.
Do not create a `-annotated` static copy unless the user explicitly asks for a
separate deliverable.

## 目录

- [Static HTML](#static-html)
- [React / Vue / Vite](#react--vue--vite)
- [Vite Write API](#vite-write-api)
- [Clearing Results](#clearing-results)
- [React Adapter](#react-adapter)
- [Vue Adapter](#vue-adapter)
- [SPA Page Keys](#spa-page-keys)
- [Runtime Asset Base](#runtime-asset-base)
- [Iframe or Exported Prototypes](#iframe-or-exported-prototypes)

## Static HTML

Use:

```bash
python3 scripts/inject_annotations.py ./index.html
```

This injects the runtime into `index.html` in place and writes generated assets
under the same directory's `prototype-annotator/`.

For a static directory:

```bash
python3 scripts/inject_annotations.py ./prototype
```

Static HTML injection writes managed annotation assets under:

```text
prototype-annotator/
  annotations.json
  history.jsonl
  README.md
  runtime/
    prototype-annotator.css
    markdown-renderer.js
    mermaid-loader.js
    prototype-annotator.js
```

Before publishing an injected static HTML prototype to Netlify, Vercel, or any
other static host, run:

```bash
python3 scripts/inject_annotations.py ./prototype
python3 scripts/validate_annotations.py ./prototype --deploy-check
```

For static HTML projects, `--deploy-check` validates the files referenced by
the injected HTML in place. Static HTML uses one deploy-safe directory for both
local review and production display:

```text
prototype-annotator/
  annotations.json
  assets/
  runtime/
    prototype-annotator.css
    markdown-renderer.js
    mermaid-loader.js
    prototype-annotator.js
  history.jsonl
  page-map.json
  annotation-candidates.json
```

The injected static HTML references `./prototype-annotator/annotations.json`
and `./prototype-annotator/runtime/...`. This avoids relying on whether a host
serves dot-prefixed directories such as `.prototype-annotations/`. The old
`.prototype-annotations/` directory is still read as a migration source when a
legacy prototype is reinjected.

If a user explicitly asks for a separate copy, pass `--output`:

```bash
python3 scripts/inject_annotations.py ./prototype --output ./prototype-copy
```

Injected HTML pages set `window.PROTOTYPE_ANNOTATOR_CONFIG.dataUrl` to
`prototype-annotator/annotations.json`. When the page is served over HTTP, the
runtime reads that project file first. The inline JSON block is only an offline
fallback snapshot.

If an older annotated output has runtime files in the prototype root, normalize
it only when maintaining that legacy output:

```bash
python3 scripts/organize_runtime_assets.py ./legacy-annotated-output
```

This command also refreshes `prototype-annotator/runtime/` from the current
skill templates so an old annotated output does not keep stale JS/CSS behavior.

## React / Vue / Vite

Preferred workflow:

1. Run the app locally.
2. Scan rendered routes with the running dev server.
3. Generate `prototype-annotator/annotations.json`.
4. Install framework adapter assets.
5. Wire the adapter into the app shell or root component.

Rendered route scan:

```bash
npm run dev
node scripts/scan_rendered_routes.mjs ./my-app --base-url http://localhost:5173
```

The scanner reads routes from `prototype-annotator/annotations.json` or
`prototype-annotator/page-map.json` when either file already has
`pages[].route`. You can also pass routes explicitly:

```bash
node scripts/scan_rendered_routes.mjs ./my-app --base-url http://localhost:5173 --routes /,/settings,/admin/users
```

Do not rely on `scan_prototype.py ./my-app` for React/Vue projects. That command
only parses static HTML files, so a SPA `index.html` usually contains no real
page controls. The result is an empty `elements[]` list for many routes and then
0 generated annotations.

Install adapter assets:

```bash
python3 scripts/install_framework_adapter.py ./my-app --framework react
python3 scripts/install_framework_adapter.py ./my-app --framework vue
```

The installer copies:

```text
public/prototype-annotator/
  prototype-annotator.css
  markdown-renderer.js
  mermaid-loader.js
  prototype-annotator.js

src/prototype-annotator/
  PrototypeAnnotatorProvider.tsx      # React
  prototypeAnnotatorPlugin.ts         # Vue
  prototypeAnnotatorVitePlugin.ts     # Vite dev-server write API, when Vite is detected
```

If `prototype-annotator/annotations.json` exists in the app root, the installer also copies it to `public/prototype-annotator/annotations.json` for convenience. Legacy `.prototype-annotations/annotations.json` is still accepted as a migration source.

For static hosting deploys, sync annotation images and deploy data before
running the Vite build:

```bash
python3 scripts/sync_deploy_assets.py ./my-app
python3 scripts/sync_deploy_assets.py ./my-app --check
python3 scripts/validate_annotations.py ./my-app --deploy-check
```

The sync command writes:

```text
public/prototype-annotator/
  annotations.json
  assets/
```

Vite copies `public/prototype-annotator/` into `dist/prototype-annotator/`,
so Markdown image references such as
`/prototype-annotator/assets/clipboard.png` continue to work on Netlify,
Vercel, and other static hosts.

### Vite Write API

Vite projects need a dev-server write API for browser edits. Without this
plugin, `PUT /.prototype-annotator/api/annotations` returns 404 and the runtime
can only save a browser `localStorage` draft.

After installing adapter assets, add the generated plugin to `vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import prototypeAnnotatorWritePlugin from "./src/prototype-annotator/prototypeAnnotatorVitePlugin";

export default defineConfig({
  plugins: [
    react(),
    prototypeAnnotatorWritePlugin(),
  ],
});
```

The plugin is active only during `vite serve`. It writes browser edits to:

```text
prototype-annotator/annotations.json
public/prototype-annotator/annotations.json
prototype-annotator/history.jsonl
```

Clipboard image uploads write to:

```text
prototype-annotator/assets/
public/prototype-annotator/assets/
```

This public copy is enabled by default. Disable it only when another build step
handles deploy assets:

```ts
prototypeAnnotatorWritePlugin({
  syncAssetsToPublic: false,
});
```

Before handing off, verify persistence by adding or editing one annotation in
the browser and checking that `history.jsonl` has a new event.

## Clearing Results

When the user wants to delete, clear, or reset annotation results, use one
command for HTML, static directories, React, Vue, and Vite projects:

```bash
python3 scripts/clear_annotations.py ./prototype-or-app
```

This removes visible annotation data, edit history, generated runtime asset
directories, public runtime copies, and static HTML runtime injection blocks. It
intentionally leaves React/Vue adapter source files in place because deleting
imported files can break the prototype build. Use `--purge-cache` only when the
user also wants to remove scan maps, candidate files, and anchor suggestions.

Validate React/Vue projects after route scanning:

```bash
python3 scripts/validate_annotations.py ./my-app
```

The validator auto-detects React/Vue from `package.json` and uses the rendered
`prototype-annotator/page-map.json`. For static HTML projects it still scans
the HTML directly.

Minimal app-shell integration without adapter:

```html
<link rel="stylesheet" href="/prototype-annotator.css">
<script>
window.PROTOTYPE_ANNOTATOR_CONFIG = Object.assign({}, window.PROTOTYPE_ANNOTATOR_CONFIG || {}, { dataUrl: "/prototype-annotator/annotations.json" });
</script>
<script id="prototype-annotations-data" type="application/json">{...}</script>
<script src="/markdown-renderer.js"></script>
<script src="/mermaid-loader.js"></script>
<script src="/prototype-annotator.js"></script>
```

For static development review, prefer `serve_annotation_review.py`; it serves
runtime assets and accepts local save requests. For source-mode Vite review,
use the Vite write plugin instead.

### React Adapter

Use `templates/snippets/react-provider.tsx` or the installed copy at `src/prototype-annotator/PrototypeAnnotatorProvider.tsx`.

Example with static imported JSON:

```tsx
import annotations from "../prototype-annotator/annotations.json";
import PrototypeAnnotatorProvider from "./prototype-annotator/PrototypeAnnotatorProvider";

export function AppShell() {
  return (
    <PrototypeAnnotatorProvider
      data={annotations}
      pageKey="P01"
      runtimeBase="/prototype-annotator/"
    >
      <App />
    </PrototypeAnnotatorProvider>
  );
}
```

Example with React Router:

```tsx
const pageKey = location.pathname === "/settings" ? "P02" : "P01";

<PrototypeAnnotatorProvider data={annotations} pageKey={pageKey}>
  <RouterProvider router={router} />
</PrototypeAnnotatorProvider>
```

The provider:

- Sets `window.PROTOTYPE_ANNOTATIONS`.
- Sets `<meta name="prototype-page-key">` for SPA route matching.
- Loads runtime CSS/JS once from `runtimeBase`.
- Calls `window.PrototypeAnnotator.setData(data)` when data or `pageKey` changes.

### Vue Adapter

Use `templates/snippets/vue-plugin.ts` or the installed copy at `src/prototype-annotator/prototypeAnnotatorPlugin.ts`.

Plugin-style setup:

```ts
import { createApp, ref } from "vue";
import App from "./App.vue";
import annotations from "../prototype-annotator/annotations.json";
import { createPrototypeAnnotator } from "./prototype-annotator/prototypeAnnotatorPlugin";

const pageKey = ref("P01");

createApp(App)
  .use(createPrototypeAnnotator({
    data: annotations,
    pageKey,
    runtimeBase: "/prototype-annotator/",
  }))
  .mount("#app");
```

Composition-style setup inside a root component:

```ts
import { computed } from "vue";
import { useRoute } from "vue-router";
import annotations from "../prototype-annotator/annotations.json";
import { usePrototypeAnnotatorSync } from "./prototype-annotator/prototypeAnnotatorPlugin";

const route = useRoute();
const pageKey = computed(() => route.path === "/settings" ? "P02" : "P01");

usePrototypeAnnotatorSync({
  data: annotations,
  pageKey,
  runtimeBase: "/prototype-annotator/",
});
```

The Vue adapter provides `usePrototypeAnnotator()` with:

- `setPageKey(pageKey)`
- `refresh()`
- `exportData()`

## SPA Page Keys

For SPAs, set one of:

- `<meta name="prototype-page-key" content="P01">`
- `data-page-key="P01"` on a root page container
- route mapping in `annotations.json.pages[].route`

Runtime resolves page key by:

1. Explicit meta or root attribute.
2. Exact route match.
3. Current HTML path.
4. First page in `pages[]`.

React/Vue adapters should pass `pageKey` explicitly when routes do not map cleanly to `annotations.json.pages[].route`.

## Runtime Asset Base

The default adapter `runtimeBase` is:

```text
/prototype-annotator/
```

This assumes files exist under:

```text
public/prototype-annotator/
```

If the app is deployed under a subpath, pass a subpath-aware base, for example:

```tsx
<PrototypeAnnotatorProvider runtimeBase={`${import.meta.env.BASE_URL}prototype-annotator/`} ... />
```

## Iframe or Exported Prototypes

If the prototype is rendered inside an iframe:

- Inject into the iframe HTML when possible.
- If not possible, use a browser extension or manual review outside this skill.

This skill does not depend on Chrome extension APIs.
