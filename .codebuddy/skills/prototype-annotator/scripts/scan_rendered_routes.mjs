#!/usr/bin/env node
/**
 * Scan rendered React/Vue/Vite routes and write prototype-annotator/page-map.json.
 *
 * The target dev server must already be running. This script intentionally keeps
 * Playwright optional: install it in the target project or provide it from the
 * current Node environment.
 */

import { createRequire } from "node:module";
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const INTERESTING_SELECTOR = [
  "a",
  "button",
  "input",
  "select",
  "textarea",
  "form",
  "table",
  "dialog",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "nav",
  "main",
  "section",
  "header",
  "footer",
  "aside",
  "canvas",
  "[role='button']",
  "[role='link']",
  "[role='tab']",
  "[role='menuitem']",
  "[role='checkbox']",
  "[role='radio']",
  "[role='switch']",
  "[data-ann]",
  "[data-testid]",
  "[data-test]",
  "[data-cy]",
].join(",");

const DEFAULT_SURFACE_OPEN_SELECTORS = [
  ".ant-modal",
  ".ant-drawer",
  ".el-dialog",
  ".el-drawer",
  ".arco-modal",
  ".arco-drawer",
  ".n-modal",
  ".n-drawer",
  ".van-popup",
  ".van-dialog",
  "[role='dialog']",
  "[role='alertdialog']",
  "[aria-modal='true']",
  ".drawer.open",
  ".modal.open",
  ".drawer",
  ".modal",
].join(", ");

function usage() {
  console.error(`Usage:
  node scripts/scan_rendered_routes.mjs <project_root> --base-url http://localhost:5173 [options]

Options:
  --routes /,/settings       Comma-separated route list. Defaults to annotations/page-map routes.
  --out path                 Output page-map path. Defaults to <project>/prototype-annotator/page-map.json
  --interaction-plan path    Interaction plan path. Defaults to <project>/prototype-annotator/interaction-plan.json
  --wait-ms 300              Extra wait after each route loads.
  --timeout-ms 15000         Per-route navigation timeout.
  --include-hidden           Keep hidden elements in the base page scan.
`);
}

function parseArgs(argv) {
  const args = {
    projectRoot: null,
    baseUrl: null,
    routes: null,
    out: null,
    interactionPlan: null,
    waitMs: 300,
    timeoutMs: 15000,
    includeHidden: false,
  };
  const rest = [...argv];
  args.projectRoot = rest.shift() || null;
  while (rest.length) {
    const key = rest.shift();
    const value = rest[0];
    if (key === "--base-url") args.baseUrl = rest.shift();
    else if (key === "--routes") args.routes = rest.shift();
    else if (key === "--out") args.out = rest.shift();
    else if (key === "--interaction-plan") args.interactionPlan = rest.shift();
    else if (key === "--wait-ms") args.waitMs = Number(rest.shift());
    else if (key === "--timeout-ms") args.timeoutMs = Number(rest.shift());
    else if (key === "--include-hidden") args.includeHidden = true;
    else throw new Error(`Unknown option: ${key}${value ? ` ${value}` : ""}`);
  }
  if (!args.projectRoot || !args.baseUrl) {
    usage();
    process.exit(2);
  }
  return args;
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function writeJsonAtomic(path, payload) {
  mkdirSync(dirname(path), { recursive: true });
  const temp = `${path}.tmp`;
  writeFileSync(temp, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  renameSync(temp, path);
}

function loadExistingPages(projectRoot) {
  const annotationsPath = resolve(projectRoot, "prototype-annotator/annotations.json");
  const pageMapPath = resolve(projectRoot, "prototype-annotator/page-map.json");
  const legacyAnnotationsPath = resolve(projectRoot, ".prototype-annotations/annotations.json");
  const legacyPageMapPath = resolve(projectRoot, ".prototype-annotations/page-map.json");
  const sourcePath = existsSync(annotationsPath)
    ? annotationsPath
    : existsSync(pageMapPath)
      ? pageMapPath
      : existsSync(legacyAnnotationsPath)
        ? legacyAnnotationsPath
        : existsSync(legacyPageMapPath)
          ? legacyPageMapPath
          : null;
  if (!sourcePath) return [];
  const data = readJson(sourcePath);
  return Array.isArray(data.pages) ? data.pages : [];
}

function listSourceFiles(dir, limit = 500) {
  const out = [];
  function walk(current) {
    if (out.length >= limit || !existsSync(current)) return;
    for (const name of readdirSync(current)) {
      if (out.length >= limit) return;
      if (name === "node_modules" || name === "dist" || name.startsWith(".")) continue;
      const path = resolve(current, name);
      const stat = statSync(path);
      if (stat.isDirectory()) {
        walk(path);
      } else if (/\.(tsx?|jsx?)$/.test(name)) {
        out.push(path);
      }
    }
  }
  walk(dir);
  return out;
}

function collectLiteralRoutes(projectRoot) {
  const routes = new Set();
  const srcDir = resolve(projectRoot, "src");
  for (const file of listSourceFiles(srcDir)) {
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(/(?:href|to)=["'](\/[^"']+)["']/g)) {
      if (!match[1].includes(":")) routes.add(match[1].trim());
    }
    for (const match of text.matchAll(/navigate\(["'`](\/[^"'`]+)["'`]\)/g)) {
      if (!match[1].includes(":")) routes.add(match[1].trim());
    }
    for (const match of text.matchAll(/["'`](\/[A-Za-z0-9_./-]+)["'`]/g)) {
      const route = match[1].trim();
      if (route.length > 1 && !route.includes(":") && !route.includes("//")) routes.add(route);
    }
  }
  return Array.from(routes).sort((a, b) => a.localeCompare(b));
}

function routePatternToRegex(route) {
  const parts = normalizeRouteToken(route).split("/").filter(Boolean);
  const pattern = "^/" + parts.map((part) => {
    if (part.startsWith(":")) return "([^/]+)";
    return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }).join("/") + "$";
  return new RegExp(pattern);
}

function normalizeDiscoveredRoute(route, literalRoutes = []) {
  if (!route.includes(":")) return route;
  const normalized = normalizeRouteToken(route);
  const regex = routePatternToRegex(normalized);
  const matched = literalRoutes.find((candidate) => regex.test(normalizeRouteToken(candidate)));
  if (matched) return normalizeRouteToken(matched);
  return normalized
    .replace(/:kbId\b/g, "r_015")
    .replace(/:caseId\b/g, "c_001")
    .replace(/:resourceId\b/g, "r_001")
    .replace(/:sceneId\b/g, "s_prod_13")
    .replace(/:id\b/g, "r_001");
}

function discoverRoutesFromProject(projectRoot) {
  const candidates = [
    resolve(projectRoot, "src/App.tsx"),
    resolve(projectRoot, "src/App.jsx"),
    resolve(projectRoot, "src/router/index.tsx"),
    resolve(projectRoot, "src/router/index.jsx"),
  ];
  for (const file of candidates) {
    if (!existsSync(file)) continue;
    const text = readFileSync(file, "utf8");
    const literalRoutes = collectLiteralRoutes(projectRoot);
    const routes = new Set();
    for (const match of text.matchAll(/path=["']([^"']+)["']/g)) {
      const raw = match[1].trim();
      if (!raw || raw === "*") continue;
      routes.add(normalizeDiscoveredRoute(raw, literalRoutes));
    }
    if (routes.size) {
      return Array.from(routes)
        .sort((a, b) => a.localeCompare(b))
        .map((route, index) => ({
          pageKey: `P${String(index + 1).padStart(2, "0")}`,
          title: route,
          path: "index.html",
          route,
        }));
    }
  }
  return [];
}

function routesFromArgs(projectRoot, rawRoutes) {
  if (rawRoutes) {
    const literalRoutes = collectLiteralRoutes(projectRoot);
    return rawRoutes.split(",").map((route) => route.trim()).filter(Boolean).map((route, index) => ({
      pageKey: `P${String(index + 1).padStart(2, "0")}`,
      title: route,
      path: "index.html",
      route: normalizeDiscoveredRoute(route, literalRoutes),
    }));
  }
  const pages = loadExistingPages(projectRoot).filter((page) => page.pageKey && page.route);
  if (pages.length > 1) return pages;
  const discovered = discoverRoutesFromProject(projectRoot);
  if (discovered.length) return discovered;
  if (pages.length) return pages;
  const indexPath = existsSync(resolve(projectRoot, "index.html")) ? "index.html" : null;
  return [{
    pageKey: "P01",
    title: "Home",
    path: indexPath || "index.html",
    route: indexPath ? "/index.html" : "/",
  }];
}

function loadInteractionPlan(projectRoot, explicitPath) {
  const candidates = [
    explicitPath ? resolve(explicitPath) : null,
    resolve(projectRoot, "prototype-annotator/interaction-plan.json"),
    resolve(projectRoot, "input/prototype-annotator/interaction-plan.json"),
    resolve(projectRoot, ".prototype-annotations/interaction-plan.json"),
    resolve(projectRoot, "input/.prototype-annotations/interaction-plan.json"),
  ].filter(Boolean);
  for (const path of candidates) {
    if (existsSync(path)) {
      const data = readJson(path);
      return {
        path,
        interactions: Array.isArray(data.interactions) ? data.interactions : [],
      };
    }
  }
  return { path: null, interactions: [] };
}

function normalizeRouteToken(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(raw, "http://local");
    return url.pathname.replace(/\/+$/, "") || "/";
  } catch {
    const cleaned = raw.split("?")[0].split("#")[0].replace(/\/+$/, "");
    if (!cleaned) return "/";
    return cleaned.startsWith("/") ? cleaned : `/${cleaned}`;
  }
}

function routeAliases(route) {
  const normalized = normalizeRouteToken(route);
  const aliases = new Set([normalized]);
  if (normalized === "/") aliases.add("/index.html");
  if (normalized === "/index.html") aliases.add("/");
  if (normalized.endsWith("/index.html")) {
    aliases.add(normalized.slice(0, -"/index.html".length) || "/");
  }
  return aliases;
}

function routeMatches(pageInfo, pageRoute) {
  if (!pageRoute) return true;
  const targetAliases = routeAliases(pageRoute);
  const candidates = [
    pageInfo.route,
    pageInfo.path,
    pageInfo.path ? `/${pageInfo.path}` : null,
    pageInfo.path ? `/${String(pageInfo.path).replace(/^\/+/, "")}` : null,
  ];
  return candidates.some((candidate) => {
    const candidateAliases = routeAliases(candidate);
    for (const alias of targetAliases) {
      if (candidateAliases.has(alias)) return true;
    }
    return false;
  });
}

async function loadPlaywright(projectRoot) {
  const attempts = [];
  const projectPackage = resolve(projectRoot, "package.json");
  if (existsSync(projectPackage)) {
    const requireFromProject = createRequire(projectPackage);
    attempts.push(() => requireFromProject("playwright"));
    attempts.push(() => requireFromProject("playwright-core"));
  }
  attempts.push(() => import("playwright"));
  attempts.push(() => import("playwright-core"));

  for (const attempt of attempts) {
    try {
      const mod = await attempt();
      if (mod.chromium) return mod;
      if (mod.default?.chromium) return mod.default;
    } catch {
      // Try the next resolution location.
    }
  }
  throw new Error("Playwright is not available. Install playwright in the target project, then rerun this script.");
}

function joinUrl(baseUrl, route) {
  const base = new URL(baseUrl);
  base.pathname = route.startsWith("/") ? route : `/${route}`;
  base.search = "";
  base.hash = "";
  return base.toString();
}

async function collectElements(page, options) {
  return page.evaluate(({ selector, includeHidden, pageKey, rootSelector, surfaceId }) => {
    function normalize(value) {
      return String(value || "").replace(/\s+/g, " ").trim();
    }

    function cssString(value) {
      return String(value || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    }

    function cssId(value) {
      return /^[A-Za-z_][A-Za-z0-9_-]*$/.test(value)
        ? `#${value}`
        : `#${String(value).replace(/([^A-Za-z0-9_-])/g, "\\$1")}`;
    }

    function visible(el) {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.width === 0 && rect.height === 0) return false;
      if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) return false;
      let current = el;
      while (current && current !== document.body) {
        const parentStyle = window.getComputedStyle(current);
        if (parentStyle.display === "none" || parentStyle.visibility === "hidden") return false;
        current = current.parentElement;
      }
      return true;
    }

    function elementText(el) {
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
        return normalize(el.placeholder || el.getAttribute("aria-label") || el.name || el.value || "");
      }
      if (el instanceof HTMLSelectElement) {
        return normalize(el.getAttribute("aria-label") || el.textContent || "");
      }
      return normalize(el.innerText || el.textContent || el.getAttribute("aria-label") || "");
    }

    function typeOf(el) {
      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute("role");
      if (tag === "button" || tag === "a" || role === "button" || role === "link") return "interaction";
      if (["input", "select", "textarea", "form"].includes(tag)) return "form";
      if (tag === "table") return "table";
      if (["nav", "main", "section", "header", "footer", "aside"].includes(tag)) return "region";
      return "element";
    }

    function structuralSelector(el) {
      const parts = [];
      let current = el;
      while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body && parts.length < 5) {
        const tag = current.tagName.toLowerCase();
        let part = tag;
        const sameTag = Array.from(current.parentElement?.children || []).filter((child) => child.tagName === current.tagName);
        if (sameTag.length > 1) part += `:nth-of-type(${sameTag.indexOf(current) + 1})`;
        parts.unshift(part);
        current = current.parentElement;
      }
      return parts.join(" > ");
    }

    function isUniqueSelector(value) {
      try {
        return document.querySelectorAll(value).length === 1;
      } catch {
        return false;
      }
    }

    function selectorFor(el) {
      const tag = el.tagName.toLowerCase();
      if (el.id) return [cssId(el.id), "id"];
      for (const attr of ["data-ann", "data-testid", "data-test", "data-cy"]) {
        const value = el.getAttribute(attr);
        if (value) return [`[${attr}="${cssString(value)}"]`, "data"];
      }
      const aria = el.getAttribute("aria-label");
      if (aria) return [`[aria-label="${cssString(aria)}"]`, "aria"];
      const name = el.getAttribute("name");
      if (name && ["input", "select", "textarea"].includes(tag)) return [`${tag}[name="${cssString(name)}"]`, "name"];
      const placeholder = el.getAttribute("placeholder");
      if (placeholder && ["input", "textarea"].includes(tag)) return [`${tag}[placeholder*="${cssString(placeholder.slice(0, 20))}"]`, "placeholder"];
      const href = el.getAttribute("href");
      if (href && tag === "a") {
        const hrefSelector = `a[href="${cssString(href)}"]`;
        if (isUniqueSelector(hrefSelector)) return [hrefSelector, "href"];
      }
      const role = el.getAttribute("role");
      if (role) {
        const roleSelector = `${tag}[role="${cssString(role)}"]`;
        if (isUniqueSelector(roleSelector)) return [roleSelector, "role"];
      }
      const ancestorSelector = stableAncestorSelector(el);
      if (ancestorSelector && ["table", "form", "nav", "header", "footer", "aside"].includes(tag)) {
        const descendantSelector = `${ancestorSelector} ${tag}`;
        if (isUniqueSelector(descendantSelector)) return [descendantSelector, "data-descendant"];
      }
      if (["h1", "main", "table", "form", "nav", "header", "footer", "aside"].includes(tag) && isUniqueSelector(tag)) {
        return [tag, "tag"];
      }
      return [structuralSelector(el), "path"];
    }

    function stableAncestorSelector(el) {
      let current = el.parentElement;
      while (current && current !== document.body) {
        for (const attr of ["data-ann", "data-testid", "data-test", "data-cy"]) {
          const value = current.getAttribute(attr);
          if (value) return `[${attr}="${cssString(value)}"]`;
        }
        if (current.id) return `#${cssString(current.id)}`;
        current = current.parentElement;
      }
      return null;
    }

    let roots = [document];
    if (rootSelector) {
      roots = Array.from(document.querySelectorAll(rootSelector));
      if (!roots.length) return [];
    }

    const nodes = [];
    for (const root of roots) {
      nodes.push(...Array.from(root.querySelectorAll(selector)));
    }

    const seen = new Set();
    const out = [];
    for (const el of nodes) {
      const isVis = visible(el);
      if (!includeHidden && !isVis) continue;
      const [sel, strategy] = selectorFor(el);
      const text = elementText(el);
      const key = `${sel}::${text}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const attrs = {};
      for (const attr of ["id", "data-ann", "data-testid", "data-test", "data-cy", "aria-label", "name", "type", "role", "href", "placeholder", "title"]) {
        const value = el.getAttribute(attr);
        if (value) attrs[attr] = value;
      }
      const entry = {
        elementId: `${pageKey}-E${String(out.length + 1).padStart(3, "0")}`,
        tag: el.tagName.toLowerCase(),
        type: typeOf(el),
        selector: sel,
        strategy,
        text: text.slice(0, 160),
        attrs,
        visible: isVis,
      };
      if (surfaceId) entry.surfaceId = surfaceId;
      out.push(entry);
    }
    return out;
  }, {
    selector: INTERESTING_SELECTOR,
    includeHidden: options.includeHidden,
    pageKey: options.pageKey,
    rootSelector: options.rootSelector || null,
    surfaceId: options.surfaceId || null,
  });
}

async function detectSurfaceRoot(page, interaction) {
  const waitSelector = interaction.waitForSelector || DEFAULT_SURFACE_OPEN_SELECTORS;
  return page.evaluate(({ waitSelector, scope, triggerSelector, contentSelector, strictExpectedTexts, titleExpectedTexts }) => {
    function visible(el) {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.width === 0 && rect.height === 0) return false;
      if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) return false;
      return true;
    }

    function cssString(value) {
      return String(value || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    }

    function selectorFor(el) {
      if (el.id) return `#${el.id}`;
      const dataAnn = el.getAttribute("data-ann");
      if (dataAnn) return `[data-ann="${cssString(dataAnn)}"]`;
      const testId = el.getAttribute("data-testid");
      if (testId) return `[data-testid="${cssString(testId)}"]`;
      return null;
    }

    function rootMatchesOrContains(el, selector) {
      if (!selector) return true;
      try {
        return el.matches(selector) || !!el.querySelector(selector);
      } catch {
        return false;
      }
    }

    function textMatchesExpected(text, expected) {
      expected = String(expected || "").trim();
      if (!expected) return true;
      if (text.includes(expected)) return true;
      const alternatives = expected.split(/[\\/／|｜]/).map((item) => item.trim()).filter((item) => item.length >= 2);
      return alternatives.some((item) => text.includes(item));
    }

    function matchesSignature(el) {
      if (!rootMatchesOrContains(el, contentSelector)) return false;
      const text = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
      if (!strictExpectedTexts.every((expected) => textMatchesExpected(text, expected))) return false;
      if (!titleExpectedTexts.length) return true;
      return titleExpectedTexts.some((expected) => textMatchesExpected(text, expected));
    }

    let searchRoot = document;
    if (scope === "trigger-parent") {
      const trigger = document.querySelector(triggerSelector);
      if (trigger?.parentElement) searchRoot = trigger.parentElement;
    }

    const selectors = waitSelector.split(",").map((item) => item.trim()).filter(Boolean);
    const matches = [];
    for (const sel of selectors) {
      try {
        searchRoot.querySelectorAll(sel).forEach((el) => {
          if (visible(el) && matchesSignature(el)) matches.push(el);
        });
      } catch {
        // Ignore invalid selector fragments.
      }
    }
    if (!matches.length) return null;

    matches.sort((a, b) => {
      const areaA = a.getBoundingClientRect();
      const areaB = b.getBoundingClientRect();
      const sizeA = areaA.width * areaA.height;
      const sizeB = areaB.width * areaB.height;
      if (sizeB !== sizeA) return sizeB - sizeA;
      const zA = Number(window.getComputedStyle(a).zIndex) || 0;
      const zB = Number(window.getComputedStyle(b).zIndex) || 0;
      return zB - zA;
    });

    const root = matches[0];
    return {
      openSelector: selectorFor(root) || waitSelector,
      name: root.getAttribute("aria-label") || root.getAttribute("data-ann") || "",
    };
  }, {
    waitSelector,
    scope: interaction.scope || "document",
    triggerSelector: interaction.triggerSelector,
    contentSelector: interaction.contentSelector || interaction.containerSelector || interaction.activeSelector || interaction.titleSelector || null,
    strictExpectedTexts: []
      .concat(interaction.textIncludes || [])
      .concat(interaction.matchText || [])
      .concat(interaction.stateText || [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
    titleExpectedTexts: []
      .concat(interaction.titleText || [])
      .concat(interaction.activeTitle || [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  });
}

function mergeElements(baseElements, extraElements) {
  const merged = [...baseElements];
  const indexBySelector = new Map(merged.map((item, index) => [item.selector, index]));
  for (const element of extraElements) {
    const existingIndex = indexBySelector.get(element.selector);
    if (existingIndex === undefined) {
      indexBySelector.set(element.selector, merged.length);
      merged.push(element);
      continue;
    }
    const existing = merged[existingIndex];
    if (element.surfaceId && !existing.surfaceId) {
      merged[existingIndex] = { ...existing, ...element };
    }
  }
  return merged.map((item, index) => ({
    ...item,
    elementId: item.elementId || `${item.pageKey || "P01"}-E${String(index + 1).padStart(3, "0")}`,
  }));
}

async function runInteraction(page, interaction, pageInfo, options) {
  const warnings = [];
  const waitMs = Number.isFinite(interaction.waitMs) ? interaction.waitMs : options.waitMs;

  if (interaction.preconditionSelector) {
    try {
      await page.waitForSelector(interaction.preconditionSelector, { timeout: options.timeoutMs });
    } catch {
      warnings.push(`${interaction.name}: precondition not found (${interaction.preconditionSelector})`);
      return { surface: null, elements: [], warnings };
    }
  }

  const trigger = await page.$(interaction.triggerSelector);
  if (!trigger) {
    warnings.push(`${interaction.name}: trigger not found (${interaction.triggerSelector})`);
    return { surface: null, elements: [], warnings };
  }

  const triggerAction = interaction.triggerAction || "click";
  if (triggerAction === "hover") await trigger.hover();
  else if (triggerAction === "focus") await trigger.focus();
  else await trigger.click();

  const waitSelector = interaction.waitForSelector || DEFAULT_SURFACE_OPEN_SELECTORS;
  const waitSelectors = waitSelector.split(",").map((item) => item.trim()).filter(Boolean);
  let opened = false;
  for (const selector of waitSelectors) {
    try {
      await page.waitForSelector(selector, { timeout: Math.max(2000, Math.floor(options.timeoutMs / Math.max(waitSelectors.length, 1))) });
      opened = true;
      break;
    } catch {
      // Try the next selector candidate.
    }
  }
  if (!opened) {
    warnings.push(`${interaction.name}: surface did not open (${waitSelector})`);
    return { surface: null, elements: [], warnings };
  }
  if (waitMs > 0) await page.waitForTimeout(waitMs);

  const detected = await detectSurfaceRoot(page, interaction);
  if (!detected) {
    warnings.push(`${interaction.name}: opened surface root could not be detected`);
    return { surface: null, elements: [], warnings };
  }

  const surface = {
    id: interaction.surfaceId,
    type: interaction.surfaceType,
    name: interaction.surfaceName || interaction.name,
    pageKey: pageInfo.pageKey,
    triggerSelector: interaction.triggerSelector,
    openSelector: detected.openSelector,
    closeSelector: interaction.closeSelector || null,
    contentSelector: interaction.contentSelector || interaction.activeSelector || null,
    activeSelector: interaction.activeSelector || null,
    titleSelector: interaction.titleSelector || null,
    titleText: interaction.titleText || interaction.activeTitle || null,
    textIncludes: interaction.textIncludes || interaction.matchText || interaction.stateText || [],
    visibility: "on-trigger",
    scanSource: "interaction-plan",
  };

  const elements = await collectElements(page, {
    includeHidden: true,
    pageKey: pageInfo.pageKey,
    rootSelector: detected.openSelector,
    surfaceId: interaction.surfaceId,
    waitMs,
    timeoutMs: options.timeoutMs,
  });

  if (interaction.closeSelector) {
    const closeButton = await page.$(interaction.closeSelector);
    if (closeButton) {
      await closeButton.click().catch(async () => {
        await page.keyboard.press("Escape");
      });
    } else {
      await page.keyboard.press("Escape");
      warnings.push(`${interaction.name}: close selector not found (${interaction.closeSelector})`);
    }
  } else {
    await page.keyboard.press("Escape");
  }
  if (waitMs > 0) await page.waitForTimeout(Math.min(waitMs, 500));

  return { surface, elements, warnings };
}

async function scanRoute(page, pageInfo, baseUrl, options, interactionsForPage) {
  const url = joinUrl(baseUrl, pageInfo.route || "/");
  await page.goto(url, { waitUntil: "networkidle", timeout: options.timeoutMs });
  if (options.waitMs > 0) await page.waitForTimeout(options.waitMs);

  const title = await page.title();
  let elements = await collectElements(page, {
    includeHidden: options.includeHidden,
    pageKey: pageInfo.pageKey,
    waitMs: options.waitMs,
    timeoutMs: options.timeoutMs,
  });

  const surfaces = [];
  const scanWarnings = [];

  for (const interaction of interactionsForPage) {
    const result = await runInteraction(page, interaction, pageInfo, options);
    scanWarnings.push(...result.warnings);
    if (result.surface) {
      surfaces.push(result.surface);
      elements = mergeElements(elements, result.elements);
    }
    if (options.waitMs > 0) await page.waitForTimeout(Math.min(options.waitMs, 300));
  }

  return {
    pageKey: pageInfo.pageKey,
    title: pageInfo.title || title || pageInfo.route || pageInfo.pageKey,
    path: pageInfo.path || "index.html",
    route: pageInfo.route || "/",
    elements,
    surfaces,
    scanWarnings,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const projectRoot = resolve(args.projectRoot);
  const out = resolve(args.out || resolve(projectRoot, "prototype-annotator/page-map.json"));
  const routePages = routesFromArgs(projectRoot, args.routes);
  const interactionPlan = loadInteractionPlan(projectRoot, args.interactionPlan);
  const playwright = await loadPlaywright(projectRoot);
  const browser = await playwright.chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const pages = [];
    const surfaces = [];
    const scanWarnings = [];

    for (const routePage of routePages) {
      const interactionsForPage = interactionPlan.interactions.filter((interaction) => routeMatches(routePage, interaction.pageRoute));
      const scanned = await scanRoute(page, routePage, args.baseUrl, args, interactionsForPage);
      const { surfaces: pageSurfaces = [], scanWarnings: pageWarnings = [], ...pagePayload } = scanned;
      pages.push(pagePayload);
      surfaces.push(...pageSurfaces);
      scanWarnings.push(...pageWarnings);
    }

    const payload = {
      version: 2,
      root: projectRoot,
      scanMode: "rendered-spa",
      scannedAt: new Date().toISOString(),
      baseUrl: args.baseUrl,
      pages,
      surfaces,
    };
    if (interactionPlan.path) payload.interactionPlan = interactionPlan.path;
    if (scanWarnings.length) payload.scanWarnings = scanWarnings;

    writeJsonAtomic(out, payload);
    const surfaceCount = surfaces.length;
    const warningSuffix = scanWarnings.length ? ` (${scanWarnings.length} warning(s))` : "";
    console.log(`Scanned ${pages.length} rendered route(s), ${surfaceCount} surface(s). Wrote ${out}${warningSuffix}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
