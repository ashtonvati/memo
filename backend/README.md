# Moment Backend

The backend receives WAV recordings from the ESP32, transcribes them with
faster-whisper, generates Markdown notes through OpenRouter, and serves a private
recording archive.

## Run on the homelab

1. Copy `.env.example` to `.env` and set `DEVICE_API_TOKEN`, `SECRET_KEY`, and
   `DASHBOARD_PASSWORD_HASH`.
2. Create an OpenRouter API key and set `OPENROUTER_API_KEY` in `.env`. The
   default model is `google/gemini-2.5-flash-lite`; change `OPENROUTER_MODEL`
   if you prefer a different provider or price point. A recording can be
   transcribed without a configured key, but note generation will be marked
   failed until it is set.
3. Start it with `docker compose up -d --build`.
4. Install Tailscale on the homelab host and open the dashboard from its
   Tailscale hostname at `http://<host>:8000`. Do not configure router port
   forwarding or a public reverse proxy.

The ESP32 is not a Tailscale node. It uploads only on the home Wi-Fi network,
using the host's stable LAN IPv4 address and port `8000`. Reserve that address
in DHCP. Keep the device upload token configured even on a trusted LAN.

The `moment-data` volume contains both `moment.db` and the `audio/` directory.
Back up that volume together; neither is useful on its own.

## Managed deployment

`ops/` contains a deliberately limited deployment controller for a dedicated
LXC. It polls GitHub `main` every five minutes, rebuilds the Compose stack only
when a new commit is available, verifies `/healthz`, and restores the previous
commit if that check fails. It has no AI access and does not edit source code.

Install the runtime configuration as `/etc/moment/backend.env` from
`ops/backend.env.example`. The controller's `moment` user needs a read-only
GitHub deploy key for this repository before running `ops/bootstrap-lxc.sh`.

## Device setup

Copy `hardware/include/secrets.example.h` to `hardware/include/secrets.h` and
set its home Wi-Fi credentials, backend LAN IPv4 address, and device token.
`secrets.h` is ignored by Git. The device deletes a local WAV only after the
server responds with HTTP 200 or 201.

## Processing

The web and worker services share SQLite and the persisted data volume. The
worker claims queued recordings, runs faster-whisper with the configured model,
then calls OpenRouter's OpenAI-compatible chat-completions endpoint. Defaults target `small` with CPU
int8 inference. Set `WHISPER_DEVICE` and `WHISPER_COMPUTE_TYPE` for GPU hosts.

## Development

Create a virtual environment and install `pip install -r requirements.txt`.
Run the web app with `PYTHONPATH=src python -m moment_backend.web`, the worker
with `PYTHONPATH=src python -m moment_backend.worker`, and tests with
`PYTHONPATH=src pytest`.
