# Repository Guidelines

## Project Structure & Module Organization

This repo is split into four areas:

- `hardware/` contains the ESP32-S3 firmware, PlatformIO config, and device pin definitions.
- `backend/` is reserved for the API, workers, database, and website that will process recordings.
- `shared/` is for schemas or message contracts used by both sides.
- `docs/` stores wiring notes and project overview material.

Keep pin definitions in `hardware/include/pinout.h` and the wiring reference in `docs/pinout.md`.
Use this root file for repo-wide conventions; `hardware/AGENTS.md` and `backend/AGENTS.md` add folder-specific instructions.

## Build, Test, and Development Commands

Run firmware commands from `hardware/`:

```sh
platformio run
platformio run --target upload
platformio device monitor
platformio run --target clean
```

Backend commands will be added under `backend/` when that service is scaffolded. For now, there is no build or test command at the repo root.

## Coding Style & Naming Conventions

Use four-space indentation and Allman-style braces, matching the existing sketch. Prefer `PascalCase` for types, `camelCase` for functions and variables, and upper-case `constexpr` names for pins and audio settings. Keep hardware constants centralized instead of duplicating GPIO values across files.

## Testing Guidelines

`platformio run` is the baseline firmware check. For device validation, confirm recordings create valid `.wav` files on the SD card and that button, LED, and serial behavior still match the documented flow. When backend code arrives, add unit tests under `backend/tests/`.

## Commit & Pull Request Guidelines

Use short, imperative commit messages such as `Move firmware into hardware folder` or `Document backend layout`. Pull requests should explain the user-visible change, note which part of the repo it affects, and describe validation performed. Include photos, logs, or screenshots when hardware or UI behavior changes.
