import type { Connect, Plugin } from "vite";
import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { basename, dirname, extname, join, resolve, sep } from "node:path";

export type PrototypeAnnotatorVitePluginOptions = {
  endpoint?: string;
  assetsEndpoint?: string;
  annotationsPath?: string;
  publicCopyPath?: string | false;
  publicDeployCopyPath?: string | false;
  assetsDir?: string;
  syncAssetsToPublic?: boolean;
  publicDir?: string;
  publicAssetsDir?: string;
};

const DEFAULT_ENDPOINT = "/.prototype-annotator/api/annotations";
const DEFAULT_ASSETS_ENDPOINT = "/.prototype-annotator/api/assets";
const ASSET_URL_PREFIX = "/prototype-annotator/assets/";
const MAX_ASSET_BYTES = 10 * 1024 * 1024;
const ALLOWED_IMAGE_MIME_TYPES: Record<string, string> = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/gif": ".gif",
  "image/webp": ".webp",
};

function readRequestBody(req: Connect.IncomingMessage): Promise<string> {
  return new Promise((resolveBody, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
    req.on("end", () => resolveBody(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function writeJsonAtomic(path: string, data: unknown) {
  mkdirSync(dirname(path), { recursive: true });
  const temp = `${path}.tmp`;
  writeFileSync(temp, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  renameSync(temp, path);
}

function sendJson(res: Connect.ServerResponse, status: number, data: unknown) {
  const text = JSON.stringify(data);
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Content-Length", Buffer.byteLength(text));
  res.end(text);
}

function sanitizeAssetStem(value: string) {
  const withoutExt = value.replace(/\.[a-zA-Z0-9]+$/, "");
  const sanitized = withoutExt.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return sanitized.slice(0, 72) || "clipboard-image";
}

function assetExtension(mimeType: string, fileName = "") {
  const normalized = (mimeType || "").split(";", 1)[0].trim().toLowerCase();
  if (ALLOWED_IMAGE_MIME_TYPES[normalized]) return ALLOWED_IMAGE_MIME_TYPES[normalized];
  const lowerName = fileName.toLowerCase();
  if (lowerName.endsWith(".png")) return ".png";
  if (lowerName.endsWith(".jpg") || lowerName.endsWith(".jpeg")) return ".jpg";
  if (lowerName.endsWith(".gif")) return ".gif";
  if (lowerName.endsWith(".webp")) return ".webp";
  throw new Error(`Unsupported image type: ${mimeType || fileName || "unknown"}`);
}

function decodeAssetPayload(payload: any): { bytes: Buffer; mimeType: string } {
  let mimeType = String(payload?.mimeType ?? "");
  let base64Text = String(payload?.base64 ?? "");
  const dataUrl = String(payload?.dataUrl ?? "");
  if (dataUrl) {
    const match = /^data:([^;,]+);base64,(.+)$/s.exec(dataUrl);
    if (!match) throw new Error("dataUrl must be a base64 data URL");
    mimeType = match[1];
    base64Text = match[2];
  }
  if (!base64Text) throw new Error("Missing image data");
  const bytes = Buffer.from(base64Text, "base64");
  if (!bytes.length) throw new Error("Invalid image data");
  if (bytes.length > MAX_ASSET_BYTES) throw new Error(`Image exceeds ${MAX_ASSET_BYTES / 1024 / 1024}MB`);
  return { bytes, mimeType };
}

function writeAsset(assetsDir: string, payload: any, publicAssetsDir?: string | null) {
  const { bytes, mimeType } = decodeAssetPayload(payload);
  const fileName = String(payload?.fileName ?? "");
  const ext = assetExtension(mimeType, fileName);
  const annotationId = sanitizeAssetStem(String(payload?.annotationId ?? ""));
  const pageKey = sanitizeAssetStem(String(payload?.pageKey ?? ""));
  const sourceStem = sanitizeAssetStem(fileName);
  const prefix = [pageKey, annotationId, sourceStem].filter((part) => part && part !== "clipboard-image").join("-") || "clipboard-image";
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "").replace("T", "-");
  mkdirSync(assetsDir, { recursive: true });
  let outputPath = resolve(assetsDir, `${prefix}-${timestamp}${ext}`);
  let index = 1;
  while (existsSync(outputPath)) {
    outputPath = resolve(assetsDir, `${prefix}-${timestamp}-${index}${ext}`);
    index += 1;
  }
  writeFileSync(outputPath, bytes);
  if (publicAssetsDir) {
    mkdirSync(publicAssetsDir, { recursive: true });
    writeFileSync(resolve(publicAssetsDir, basename(outputPath)), bytes);
  }
  return {
    ok: true,
    src: ASSET_URL_PREFIX + basename(outputPath),
    fileName: basename(outputPath),
    mimeType: mimeType.split(";", 1)[0] || "application/octet-stream",
    bytes: bytes.length,
  };
}

function imageContentType(path: string) {
  const ext = extname(path).toLowerCase();
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".gif") return "image/gif";
  if (ext === ".webp") return "image/webp";
  return "application/octet-stream";
}

export function prototypeAnnotatorWritePlugin(options: PrototypeAnnotatorVitePluginOptions = {}): Plugin {
  const endpoint = options.endpoint ?? DEFAULT_ENDPOINT;
  const assetsEndpoint = options.assetsEndpoint ?? DEFAULT_ASSETS_ENDPOINT;

  return {
    name: "prototype-annotator-write-api",
    apply: "serve",
    configureServer(server) {
      const root = server.config.root;
      const annotationsPath = resolve(root, options.annotationsPath ?? "prototype-annotator/annotations.json");
      const publicCopyPath = options.publicCopyPath === false
        ? null
        : resolve(root, options.publicCopyPath ?? "public/prototype-annotator/annotations.json");
      const syncAssetsToPublic = options.syncAssetsToPublic ?? true;
      const publicDir = options.publicDir ?? "public";
      const publicDeployCopyPath = options.publicDeployCopyPath === false
        ? null
        : resolve(root, options.publicDeployCopyPath ?? join(publicDir, "prototype-annotator/annotations.json"));
      const historyPath = resolve(root, "prototype-annotator/history.jsonl");
      const assetsDir = resolve(root, options.assetsDir ?? "prototype-annotator/assets");
      const publicAssetsDir = syncAssetsToPublic
        ? resolve(root, options.publicAssetsDir ?? join(publicDir, "prototype-annotator/assets"))
        : null;
      const assetsRoot = resolve(assetsDir);

      server.middlewares.use(async (req, res, next) => {
        const pathname = new URL(req.url ?? "", "http://localhost").pathname;
        if (pathname.startsWith(ASSET_URL_PREFIX)) {
          const rel = pathname.slice(ASSET_URL_PREFIX.length);
          const assetPath = resolve(assetsRoot, rel);
          if ((!assetPath.startsWith(assetsRoot + sep) && assetPath !== assetsRoot) || !existsSync(assetPath)) {
            sendJson(res, 404, { ok: false, error: "Asset not found." });
            return;
          }
          res.statusCode = 200;
          res.setHeader("Content-Type", imageContentType(assetPath));
          res.setHeader("Cache-Control", "no-store, max-age=0");
          res.end(readFileSync(assetPath));
          return;
        }

        if (pathname === assetsEndpoint) {
          if (req.method !== "POST") {
            sendJson(res, 405, { ok: false, error: "Only POST is supported." });
            return;
          }
          try {
            const payload = JSON.parse(await readRequestBody(req));
            sendJson(res, 200, writeAsset(assetsDir, payload, publicAssetsDir));
          } catch (error) {
            sendJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) });
          }
          return;
        }

        if (pathname !== endpoint) {
          next();
          return;
        }

        if (req.method === "GET") {
          if (!existsSync(annotationsPath)) {
            sendJson(res, 404, { ok: false, error: `Missing annotations file: ${annotationsPath}` });
            return;
          }
          res.statusCode = 200;
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.end(readFileSync(annotationsPath, "utf8"));
          return;
        }

        if (req.method !== "PUT") {
          sendJson(res, 405, { ok: false, error: "Only GET and PUT are supported." });
          return;
        }

        try {
          const payload = JSON.parse(await readRequestBody(req));
          if (!payload || !payload.data || !Array.isArray(payload.data.annotations)) {
            sendJson(res, 400, { ok: false, error: "Payload must include data.annotations." });
            return;
          }

          writeJsonAtomic(annotationsPath, payload.data);
          if (publicCopyPath) writeJsonAtomic(publicCopyPath, payload.data);
          if (publicDeployCopyPath) writeJsonAtomic(publicDeployCopyPath, payload.data);

          mkdirSync(dirname(historyPath), { recursive: true });
          appendFileSync(historyPath, `${JSON.stringify({
            at: new Date().toISOString(),
            action: payload.action ?? "save",
            id: payload.annotation?.id ?? null,
            title: payload.annotation?.title ?? null,
          })}\n`, "utf8");

          sendJson(res, 200, {
            ok: true,
            annotationsPath,
            publicCopyPath,
            publicDeployCopyPath,
            reportRefreshRequired: true,
          });
        } catch (error) {
          sendJson(res, 500, { ok: false, error: error instanceof Error ? error.message : String(error) });
        }
      });
    },
  };
}

export default prototypeAnnotatorWritePlugin;
