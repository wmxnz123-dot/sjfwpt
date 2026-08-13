import type { App, InjectionKey, Ref } from "vue";
import { inject, onMounted, ref, watch } from "vue";

export type PrototypeAnnotationTarget = {
  selector: string;
  fallbackText?: string;
  strategy?: string;
  boundsHint?: {
    tag?: string;
    text?: string;
  };
};

export type PrototypeAnnotation = {
  id: string;
  pageKey: string;
  target: PrototypeAnnotationTarget;
  title: string;
  contentMarkdown: string;
  kind?: string;
  priority?: "high" | "medium" | "low";
  visible?: boolean;
  source?: {
    type: "prd" | "prototype" | "manual" | "ai-inference" | "mixed";
    ref?: string;
  };
  createdBy?: "ai" | "manual";
  updatedAt?: string;
  order?: number;
};

export type PrototypeAnnotationsData = {
  version: 1;
  project?: {
    id?: string;
    name?: string;
    source?: string;
  };
  pages: Array<{
    pageKey: string;
    title?: string;
    path?: string;
    route?: string;
  }>;
  annotations: PrototypeAnnotation[];
};

export type PrototypeAnnotatorOptions = {
  data?: PrototypeAnnotationsData | Ref<PrototypeAnnotationsData | undefined>;
  annotationsUrl?: string;
  pageKey?: string | Ref<string | undefined>;
  enabled?: boolean | Ref<boolean>;
  runtimeBase?: string;
  apiEndpoint?: string;
  autoSave?: boolean;
  rootClass?: string;
};

type PrototypeAnnotatorApi = {
  setPageKey: (pageKey?: string) => void;
  refresh: () => void;
  exportData: () => void;
};

declare global {
  interface Window {
    PROTOTYPE_ANNOTATIONS?: PrototypeAnnotationsData;
    PROTOTYPE_ANNOTATOR_CONFIG?: Record<string, unknown>;
    PrototypeAnnotator?: {
      setData: (data: PrototypeAnnotationsData) => void;
      refresh: () => void;
      exportData: () => void;
      getData: () => PrototypeAnnotationsData;
    };
  }
}

const PrototypeAnnotatorKey: InjectionKey<PrototypeAnnotatorApi> = Symbol("PrototypeAnnotator");
const RUNTIME_FILES = ["markdown-renderer.js", "mermaid-loader.js", "prototype-annotator.js"];

function valueOf<T>(value: T | Ref<T>): T {
  return value && typeof value === "object" && "value" in value ? value.value : value as T;
}

function normalizeBase(base: string) {
  return base.endsWith("/") ? base : `${base}/`;
}

function ensureMetaPageKey(pageKey?: string) {
  const existing = document.querySelector<HTMLMetaElement>('meta[name="prototype-page-key"]');
  if (!pageKey) {
    existing?.remove();
    return;
  }
  const meta = existing ?? document.createElement("meta");
  meta.name = "prototype-page-key";
  meta.content = pageKey;
  if (!existing) document.head.appendChild(meta);
}

function ensureStylesheet(id: string, href: string) {
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

function loadScriptOnce(id: string, src: string) {
  const existing = document.getElementById(id) as HTMLScriptElement | null;
  if (existing) {
    if (existing.dataset.loaded === "true") return Promise.resolve();
    return new Promise<void>((resolve, reject) => {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), { once: true });
    });
  }

  return new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.id = id;
    script.src = src;
    script.async = false;
    script.onload = () => {
      script.dataset.loaded = "true";
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.body.appendChild(script);
  });
}

async function loadRuntime(runtimeBase: string) {
  const base = normalizeBase(runtimeBase);
  ensureStylesheet("prototype-annotator-css", `${base}prototype-annotator.css`);
  for (const file of RUNTIME_FILES) {
    await loadScriptOnce(`prototype-annotator-${file}`, `${base}${file}`);
  }
}

async function resolveAnnotationsData(options: PrototypeAnnotatorOptions) {
  const data = options.data ? valueOf(options.data) : undefined;
  if (data) return data;
  const runtimeBase = options.runtimeBase ?? "/prototype-annotator/";
  const url = options.annotationsUrl ?? `${normalizeBase(runtimeBase)}annotations.json`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to load annotations data: ${response.status} ${url}`);
  return await response.json() as PrototypeAnnotationsData;
}

async function syncRuntime(options: PrototypeAnnotatorOptions) {
  const data = await resolveAnnotationsData(options);
  const pageKey = options.pageKey ? valueOf(options.pageKey) : undefined;
  window.PROTOTYPE_ANNOTATIONS = data;
  ensureMetaPageKey(pageKey);
  if (window.PrototypeAnnotator) {
    window.PrototypeAnnotator.setData(data);
    window.PrototypeAnnotator.refresh();
  }
}

export function createPrototypeAnnotator(options: PrototypeAnnotatorOptions) {
  async function initializeRuntime() {
    const data = await resolveAnnotationsData(options);
    const pageKey = options.pageKey ? valueOf(options.pageKey) : undefined;
    window.PROTOTYPE_ANNOTATIONS = data;
    ensureMetaPageKey(pageKey);
    await loadRuntime(options.runtimeBase ?? "/prototype-annotator/");
    await syncRuntime(options);
  }

  const api: PrototypeAnnotatorApi = {
    setPageKey(pageKey?: string) {
      ensureMetaPageKey(pageKey);
      resolveAnnotationsData(options).then((data) => {
        window.PrototypeAnnotator?.setData(data);
        window.PrototypeAnnotator?.refresh();
      });
    },
    refresh() {
      window.PrototypeAnnotator?.refresh();
    },
    exportData() {
      window.PrototypeAnnotator?.exportData();
    },
  };

  return {
    install(app: App) {
      if (typeof window === "undefined") return;
      app.provide(PrototypeAnnotatorKey, api);

      const enabled = options.enabled == null ? true : valueOf(options.enabled);
      if (!enabled) return;

      window.PROTOTYPE_ANNOTATOR_CONFIG = {
        apiEndpoint: options.apiEndpoint ?? "/.prototype-annotator/api/annotations",
        autoSave: options.autoSave ?? true,
        rootClass: options.rootClass ?? "pa-root",
      };
      initializeRuntime().catch((error) => {
        console.error("Prototype Annotator failed to initialize", error);
      });
    },
  };
}

export function usePrototypeAnnotator() {
  return inject(PrototypeAnnotatorKey);
}

export function usePrototypeAnnotatorSync(options: PrototypeAnnotatorOptions) {
  const ready = ref(false);

  onMounted(() => {
    if (typeof window === "undefined") return;
    window.PROTOTYPE_ANNOTATOR_CONFIG = {
      apiEndpoint: options.apiEndpoint ?? "/.prototype-annotator/api/annotations",
      autoSave: options.autoSave ?? true,
      rootClass: options.rootClass ?? "pa-root",
    };
    resolveAnnotationsData(options).then((data) => {
      const pageKey = options.pageKey ? valueOf(options.pageKey) : undefined;
      window.PROTOTYPE_ANNOTATIONS = data;
      ensureMetaPageKey(pageKey);
      return loadRuntime(options.runtimeBase ?? "/prototype-annotator/");
    }).then(() => {
      return syncRuntime(options);
    }).then(() => {
      ready.value = true;
    }).catch((error) => {
      console.error("Prototype Annotator failed to initialize", error);
    });
  });

  watch(
    () => [valueOf(options.data), options.pageKey ? valueOf(options.pageKey) : undefined, options.enabled ? valueOf(options.enabled) : true],
    () => {
      if (typeof window === "undefined") return;
      if (options.enabled != null && !valueOf(options.enabled)) return;
      syncRuntime(options).catch((error) => {
        console.error("Prototype Annotator failed to sync data", error);
      });
    },
    { deep: true }
  );

  return { ready };
}
