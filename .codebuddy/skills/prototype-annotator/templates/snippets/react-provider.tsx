import React, { PropsWithChildren, useEffect } from "react";

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

export type PrototypeAnnotatorProviderProps = PropsWithChildren<{
  data?: PrototypeAnnotationsData;
  annotationsUrl?: string;
  pageKey?: string;
  enabled?: boolean;
  runtimeBase?: string;
  apiEndpoint?: string;
  autoSave?: boolean;
  rootClass?: string;
}>;

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

const RUNTIME_FILES = [
  "markdown-renderer.js",
  "mermaid-loader.js",
  "prototype-annotator.js",
];

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

async function resolveAnnotationsData(data: PrototypeAnnotationsData | undefined, runtimeBase: string, annotationsUrl?: string) {
  if (data) return data;
  const url = annotationsUrl ?? `${normalizeBase(runtimeBase)}annotations.json`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to load annotations data: ${response.status} ${url}`);
  return await response.json() as PrototypeAnnotationsData;
}

export function PrototypeAnnotatorProvider({
  data,
  annotationsUrl,
  pageKey,
  enabled = true,
  runtimeBase = "/prototype-annotator/",
  apiEndpoint = "/.prototype-annotator/api/annotations",
  autoSave = true,
  rootClass = "pa-root",
  children,
}: PrototypeAnnotatorProviderProps) {
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    let cancelled = false;
    window.PROTOTYPE_ANNOTATOR_CONFIG = {
      apiEndpoint,
      autoSave,
      rootClass,
    };
    ensureMetaPageKey(pageKey);

    resolveAnnotationsData(data, runtimeBase, annotationsUrl).then((resolvedData) => {
      if (cancelled) return;
      window.PROTOTYPE_ANNOTATIONS = resolvedData;
      return loadRuntime(runtimeBase).then(() => {
        if (cancelled) return;
        if (window.PrototypeAnnotator) {
          window.PrototypeAnnotator.setData(resolvedData);
          window.PrototypeAnnotator.refresh();
        }
      });
    }).catch((error) => {
      console.error("Prototype Annotator failed to initialize", error);
    });

    return () => {
      cancelled = true;
    };
  }, [annotationsUrl, apiEndpoint, autoSave, data, enabled, pageKey, rootClass, runtimeBase]);

  return <>{children}</>;
}

export default PrototypeAnnotatorProvider;
