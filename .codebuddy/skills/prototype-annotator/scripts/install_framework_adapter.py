#!/usr/bin/env python3
"""Install React or Vue adapter assets into a frontend project."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = SKILL_DIR / "templates" / "runtime"
SNIPPETS_DIR = SKILL_DIR / "templates" / "snippets"
RUNTIME_FILES = [
    "prototype-annotator.css",
    "markdown-renderer.js",
    "mermaid-loader.js",
    "prototype-annotator.js",
]


def detect_framework(project_root: Path) -> str | None:
    package_json = project_root / "package.json"
    if not package_json.exists():
        return None
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    deps = {}
    deps.update(data.get("dependencies") or {})
    deps.update(data.get("devDependencies") or {})
    if "vue" in deps:
        return "vue"
    if "react" in deps:
        return "react"
    return None


def uses_vite(project_root: Path) -> bool:
    package_json = project_root / "package.json"
    if not package_json.exists():
        return False
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    deps = {}
    deps.update(data.get("dependencies") or {})
    deps.update(data.get("devDependencies") or {})
    scripts = data.get("scripts") or {}
    return "vite" in deps or any("vite" in str(command) for command in scripts.values())


def copy_runtime(project_root: Path, public_subdir: str) -> Path:
    dest = project_root / public_subdir
    dest.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES:
        shutil.copy2(RUNTIME_DIR / name, dest / name)
    return dest


def copy_adapter(project_root: Path, framework: str, adapter_dir: str) -> Path:
    dest = project_root / adapter_dir
    dest.mkdir(parents=True, exist_ok=True)
    if framework == "react":
        target = dest / "PrototypeAnnotatorProvider.tsx"
        shutil.copy2(SNIPPETS_DIR / "react-provider.tsx", target)
        return target
    if framework == "vue":
        target = dest / "prototypeAnnotatorPlugin.ts"
        shutil.copy2(SNIPPETS_DIR / "vue-plugin.ts", target)
        return target
    raise ValueError(f"Unsupported framework: {framework}")


def copy_vite_plugin(project_root: Path, adapter_dir: str) -> Path:
    dest = project_root / adapter_dir
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "prototypeAnnotatorVitePlugin.ts"
    shutil.copy2(SNIPPETS_DIR / "vite-plugin.ts", target)
    return target


def copy_deploy_sync_script(project_root: Path) -> Path:
    dest = project_root / "scripts"
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "sync_deploy_assets.py"
    shutil.copy2(SKILL_DIR / "scripts" / "sync_deploy_assets.py", target)
    return target


def add_deploy_sync_package_scripts(project_root: Path) -> list[str]:
    package_json = project_root / "package.json"
    if not package_json.exists():
        return []
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    scripts = data.setdefault("scripts", {})
    added: list[str] = []
    wanted = {
        "prototype-annotator:sync-deploy": "python3 scripts/sync_deploy_assets.py .",
        "prototype-annotator:deploy-check": "python3 scripts/sync_deploy_assets.py . --check",
    }
    for name, command in wanted.items():
        if name in scripts:
            continue
        scripts[name] = command
        added.append(name)
    if added:
        package_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def rewrite_asset_urls(text: str) -> str:
    return (
        text
        .replace("/.prototype-annotations/assets/", "/prototype-annotator/assets/")
        .replace("./.prototype-annotations/assets/", "./prototype-annotator/assets/")
        .replace(".prototype-annotations/assets/", "prototype-annotator/assets/")
    )


def copy_annotations(project_root: Path, public_dest: Path, annotations: Path | None) -> Path | None:
    source = annotations or project_root / "prototype-annotator" / "annotations.json"
    canonical = project_root / "prototype-annotator" / "annotations.json"
    if not source.exists():
        legacy = project_root / ".prototype-annotations" / "annotations.json"
        if legacy.exists():
            source = legacy
    if not source.exists():
        return None
    text = rewrite_asset_urls(source.read_text(encoding="utf-8"))
    if source != canonical:
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(text, encoding="utf-8")
    target = public_dest / "annotations.json"
    target.write_text(text, encoding="utf-8")
    return target


def runtime_base_from_public_subdir(public_subdir: str) -> str:
    path = Path(public_subdir)
    parts = path.parts
    if parts and parts[0] == "public":
        path = Path(*parts[1:]) if len(parts) > 1 else Path("")
    value = "/" + str(path).strip("/") + "/"
    return value.replace("//", "/")


def iter_source_files(project_root: Path):
    source_root = project_root / "src"
    if not source_root.exists():
        return
    suffixes = {".ts", ".tsx", ".js", ".jsx", ".vue"}
    for path in source_root.rglob("*"):
        if path.is_file() and path.suffix in suffixes and "node_modules" not in path.parts:
            yield path


def adapter_is_wired(project_root: Path, framework: str, adapter_dir: str) -> bool:
    adapter_root = (project_root / adapter_dir).resolve()
    needles = ["PrototypeAnnotatorProvider"] if framework == "react" else ["prototypeAnnotatorPlugin", "PrototypeAnnotator"]
    for path in iter_source_files(project_root) or []:
        try:
            resolved = path.resolve()
            if adapter_root in resolved.parents:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(needle in text for needle in needles):
            return True
    return False


def vite_plugin_is_wired(project_root: Path) -> bool:
    config_paths = [
        project_root / "vite.config.ts",
        project_root / "vite.config.js",
        project_root / "vite.config.mts",
        project_root / "vite.config.mjs",
    ]
    for path in config_paths:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "prototypeAnnotatorWritePlugin" in text:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Prototype Annotator React/Vue adapter assets.")
    parser.add_argument("project_root", help="Frontend project root")
    parser.add_argument("--framework", choices=["react", "vue"], help="Framework. Defaults to package.json detection.")
    parser.add_argument("--public-subdir", default="public/prototype-annotator", help="Runtime asset destination")
    parser.add_argument("--adapter-dir", default="src/prototype-annotator", help="Adapter source destination")
    parser.add_argument("--annotations", help="Optional annotations.json to copy into public runtime assets")
    parser.add_argument("--no-vite-plugin", action="store_true", help="Do not copy the Vite dev-server write plugin.")
    parser.add_argument("--add-deploy-sync-script", action="store_true", help="Copy the deploy asset sync helper into the project and add npm scripts.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.exists():
        parser.error(f"Project root does not exist: {project_root}")

    framework = args.framework or detect_framework(project_root)
    if not framework:
        parser.error("Could not detect framework from package.json. Pass --framework react or --framework vue.")

    annotations = Path(args.annotations).resolve() if args.annotations else None
    public_dest = copy_runtime(project_root, args.public_subdir)
    adapter_path = copy_adapter(project_root, framework, args.adapter_dir)
    annotations_dest = copy_annotations(project_root, public_dest, annotations)
    vite_plugin_path = None
    if not args.no_vite_plugin and uses_vite(project_root):
        vite_plugin_path = copy_vite_plugin(project_root, args.adapter_dir)
    deploy_sync_script = None
    deploy_scripts = []
    if args.add_deploy_sync_script:
        deploy_sync_script = copy_deploy_sync_script(project_root)
        deploy_scripts = add_deploy_sync_package_scripts(project_root)

    runtime_base = runtime_base_from_public_subdir(args.public_subdir)
    print(f"Framework: {framework}")
    print(f"Runtime assets: {public_dest}")
    print(f"Adapter: {adapter_path}")
    print(f"runtimeBase: {runtime_base}")
    if annotations_dest:
        print(f"Copied annotations: {annotations_dest}")
    else:
        print("No annotations.json copied.")
    if vite_plugin_path:
        rel_plugin = vite_plugin_path.relative_to(project_root)
        print(f"Vite write plugin: {vite_plugin_path}")
        if vite_plugin_is_wired(project_root):
            print("Vite write plugin is already wired in vite.config.*.")
        else:
            print("Vite write plugin is not wired yet. Add this to vite.config.ts plugins:")
            print(f"  import prototypeAnnotatorWritePlugin from './{rel_plugin.with_suffix('').as_posix()}';")
            print("  prototypeAnnotatorWritePlugin(),")
        print("Before building for static hosting, sync deploy assets:")
        print(f"  python3 {SKILL_DIR / 'scripts' / 'sync_deploy_assets.py'} {project_root}")
        print(f"  python3 {SKILL_DIR / 'scripts' / 'sync_deploy_assets.py'} {project_root} --check")
    if deploy_sync_script:
        print(f"Deploy sync script: {deploy_sync_script}")
        if deploy_scripts:
            print("Added package scripts: " + ", ".join(deploy_scripts))
        else:
            print("Package deploy sync scripts already exist or package.json could not be updated.")
    if adapter_is_wired(project_root, framework, args.adapter_dir):
        print("App adapter appears to be wired into the application shell.")
    else:
        print("App adapter is not wired yet. Wrap the app shell with PrototypeAnnotatorProvider or install the Vue plugin before browser review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
