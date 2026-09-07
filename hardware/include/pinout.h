#pragma once

// Pin assignments for "moment". Source of truth: docs/pinout.md
// ESP32-S3 raw GPIO numbers (Waveshare ESP32-S3 Mini).

// --- Power / ground ------------------------------------------------------
#define PIN_3V3    -1   // INMP441 VDD, SD reader 3V3, Display VCC
#define PIN_GND    -1   // common ground rail — everything

// --- SD card reader (SPI) ------------------------------------------------
#define PIN_SD_CS    13
#define PIN_SD_MOSI  12
#define PIN_SD_CLK   11
#define PIN_SD_MISO  10

// --- INMP441 I2S microphone ----------------------------------------------
#define PIN_MIC_SCK   2   // BCLK
#define PIN_MIC_WS    3   // LRCLK
#define PIN_MIC_DOUT  1   // SD (data out)

// --- Controls -------------------------------------------------------------
#define PIN_BUTTON    6

// --- Status LED (WS2812 on board) -----------------------------------------
#define PIN_LED_WS2812  21
