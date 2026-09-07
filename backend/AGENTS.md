# Repository Guidelines

## Project Structure & Module Organization

`backend/` is reserved for the service that will ingest recordings, run AI processing, store note metadata, and serve the website. Use `src/` for application code, `tests/` for automated checks, `migrations/` for database changes, and `jobs/` for background workers. Keep shared request/response shapes in `shared/`.

## Build, Test, and Development Commands

Define backend commands in this folder once the stack is chosen. Keep them scriptable and document them in a backend README, for example `npm test`, `npm run dev`, or `pytest`. Do not add backend tooling to `hardware/`.

## Coding Style & Naming Conventions

Follow the chosen backend framework defaults, but keep route names, job names, and database tables descriptive and lowercase. Put shared payloads and schemas in `shared/` so firmware and backend stay in sync. Prefer explicit names like `recordings`, `transcriptions`, and `note_jobs`.

## Testing Guidelines

Add unit tests for parsing, transcription orchestration, and note generation logic. Add integration tests for upload, list, and download flows once the HTTP API exists. Name tests after behavior, not implementation details.
