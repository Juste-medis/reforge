# Development environment

Verified on the project VPS on **2026-10-23**. No system packages were changed; everything below is installed in user space.

## Toolchain

| Tool | Version | Location | How it was installed |
|---|---|---|---|
| uv | 0.13.5 | `~/.local/bin/uv` | Official GitHub release tarball, SHA-256 verified |
| Python | 3.12.15 (uv-managed) | `~/.local/share/uv/python/` | `uv python install 3.12`. The system Python 3.13.7 is untouched |
| Node.js | **24.22.1 LTS** | `~/.local/opt/node-v24.22.1-linux-x64` | Official nodejs.org tarball, SHA-256 verified against `SHASUMS256.txt` |
| npm | 11.19.1 | bundled with Node 24 | — |
| Docker | 29.7.2 | system | The user is in the `docker` group (no sudo needed) |
| git | 2.51.0 | system | Repo initialised on 2026-10-23; no commits yet |

**Why Node 24:** the system Node 20.19.4 is end-of-life (its last release was v20.20.2, March 2026), and Vitest 5 requires Node ≥ 22.12. The system Node is left in place so other projects on this VPS aren't affected.

**Shell setup.** Run this per shell. It isn't added to `~/.bashrc`, so other projects keep the system Node:

```bash
export PATH="$HOME/.local/opt/node-v24.22.1-linux-x64/bin:$HOME/.local/bin:$PATH"
```

## Python stack (smoke-tested 2026-10-23)

Tested in a throwaway environment. The project's pinned `pyproject.toml` and `uv.lock` are created at kickoff.

| Package | Version | What was verified |
|---|---|---|
| opencv-contrib-python-headless | 4.14.0 (pinned `<5`) | `cv2.aruco.ArucoDetector` finds DICT_4X4_50 markers after a perspective warp |
| manifold3d | 3.5.4 | Extruding a 2-hole plate gives a watertight solid, the exact expected volume and genus 2. Build time 6.3 ms |
| trimesh | 5.1.1 | Watertightness, volume and Euler-number checks |
| shapely | 2.2.0 | 2D booleans and buffers |
| scikit-image | 0.26.0 | Sub-pixel `find_contours` |
| numpy / scipy | 2.5.4 / 1.18.1 | — |
| openai | 3.37.0 | The Responses and Images APIs are present; works with `base_url=https://api.meta.ai/v1` |
| meta-sam-parser | 0.1.0 (Meta "SAM License") | `parse_responses_stream`, `image_segmentation_format`, `decode_mask_to_raster`, `build_object_prompt`. Masks are **box-local** (`SegmentationMaskBounds`). Mask round-trip verified offline |
| fastapi / uvicorn | 0.161.1 / 0.54.0 | — |
| pydantic / pydantic-settings | 2.14.1 / 2.16.1 | — |
| python-multipart, pillow, httpx | 0.0.32, 13.0.0, 0.28.1 | — |
| fpdf2 | 2.8.9 (LGPL-3.0) | Generates the mat PDF. Fine to use as a library; reportlab is the fallback if the rules restrict licences |
| pytest | 9.1.1 | — |

The full stack installs in about 12 s from the uv cache.

## Frontend versions (npm registry, 2026-10-23; installed at kickoff)

| Package | Version | Note |
|---|---|---|
| vite / @vitejs/plugin-react | 8.3.5 / 6.1.2 | Need Node ^20.19 or ≥ 22.12 |
| react / react-dom | 19.3.x | `@react-three/fiber` requires `>=19 <19.4` |
| three / @react-three/fiber / @react-three/drei | 0.186.1 / 9.8.2 / 10.7.9 | — |
| tailwindcss + @tailwindcss/vite | 4.3.3 | The plugin supports Vite 8 |
| typescript | **5.9.3 (pinned)** | `openapi-typescript` 7.13 requires `typescript ^5.x`, so 7.0.2 is excluded |
| vitest | 5.0.5 | Needs Node ≥ 22.12, which is why we use Node 24 |
| openapi-typescript | 7.13.0 | Generates TypeScript types from FastAPI's OpenAPI spec |
| @meta-sam/parser | 0.1.0 | Optional: decodes masks in the browser |

## Docker images

These were checked to exist via `docker manifest inspect`. They're pulled when first needed.

| Image | Purpose |
|---|---|
| `python:3.12-slim` | Runtime base |
| `node:24-slim` | Frontend build stage |
| `openscad/openscad:latest` | CI-only check that the emitted `.scad` matches the manifold3d solid |
| `caddy:2` | HTTPS reverse proxy for the public demo |

## Secrets

1. Copy `.env.example` to `.env`, then set `META_MODEL_API_KEY` (create a key at https://dev.meta.ai/api-keys/).
2. `.env` and `.env.*` are git-ignored; this was checked with `git check-ignore`. Only `.env.example` is tracked.
3. Never paste the key into chat, logs or issues.

## API verification (pre-kickoff, throwaway)

```bash
~/.local/bin/uv run prep/verify_meta_api.py            # about $0.01, standard-tier models
~/.local/bin/uv run prep/verify_meta_api.py --muse-image   # adds a $0.01 Muse Image edit test
```

- **Inputs:** a synthetic test image only.
- **What it checks:** key and model access; Spark structured output, and vision with enum/minimum keywords; SAM 3.1 with text and point prompts, including mask placement, hole preservation and IoU against the exact ground truth; and image token cost.
- **Output:** writes `prep/out/verify_report_*.json`.
- **Status:** `prep/` is git-ignored and isn't part of the submission. The offline parts were self-tested on 2026-10-23; the live run needs the key.

## Reproducibility plan (created at kickoff)

- `backend/pyproject.toml` + `uv.lock`, pinned to the versions above.
- `frontend/package.json` + `package-lock.json`, plus `.node-version` set to `24.22.1`.
- A multi-stage Dockerfile using the same Python and Node versions.

## Browser verification (dev tool, not a project dependency)

- **Installed:** Playwright's Chromium and headless shell (v1248), in `~/.cache/ms-playwright` (about 681 MB), on 2026-10-26.
- **Used for:** headless UI checks and screenshots (scripts in the session scratchpad).
- **How it's run:** `uv run --no-project --with playwright …`. It isn't in `pyproject.toml` or `package.json`.

## Running the app

```bash
export PATH="$HOME/.local/opt/node-v24.22.1-linux-x64/bin:$HOME/.local/bin:$PATH"
cd frontend && npm install && npm run build      # outputs to frontend/dist
cd ../backend && uv sync && uv run reforge-api    # http://127.0.0.1:8000 (serves the UI and the API)
# Dev mode with hot reload: run `uv run reforge-api`, then `cd frontend && npm run dev` (http://localhost:5173, proxies /api)
```

In VS Code Remote, forward port 8000 (or 5173) to open the UI in your local browser.
