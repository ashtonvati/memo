# Repository Guidelines

## Project Structure & Module Organization

`hardware/` is the firmware project root. `platformio.ini` configures the ESP32-S3 build, `src/complete_fixed_arduino.ino` contains the recorder logic, `include/pinout.h` is the pin source of truth, and `no_ota.csv` is the firmware partition layout. Treat `docs/pinout.md` as the wiring reference for humans.

## Build, Test, and Development Commands

Run PlatformIO from `hardware/`:

```sh
platformio run
platformio run --target upload
platformio device monitor
```

Use `platformio run` before changing pins, SD behavior, I2S capture, or button logic.

## Coding Style & Naming Conventions

Keep the current sketch style: four-space indentation, braces on their own lines, and short section headers. Use `constexpr` for hardware values and keep pin assignments in `include/pinout.h` instead of scattering literals through the sketch. Prefer `camelCase` for functions and `PascalCase` only for types.

## Testing Guidelines

Compile first, then verify recording start and stop, WAV finalization, SD writes, and LED state changes on hardware. If wiring or audio timing changes, update `docs/pinout.md` and `docs/overview.md` together. Keep hardware notes out of `backend/`.
