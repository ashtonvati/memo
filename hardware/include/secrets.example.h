#pragma once

// Copy this file to secrets.h, fill in real values, and keep secrets.h private.
// API_HOST is the backend's stable home-LAN IPv4 address, not its Tailscale IP.
constexpr char HOME_WIFI_SSID[] = "Telstra6B0DC3";
constexpr char HOME_WIFI_PASSWORD[] = "szcs44mzmwscr6h9";

constexpr char API_HOST[] = "192.168.1.10";
constexpr uint16_t API_PORT = 8000;
constexpr char API_PATH[] = "/api/v1/recordings";
constexpr char DEVICE_ID[] = "moment-001";
// Use the same long random value for DEVICE_API_TOKEN in backend/.env.
constexpr char DEVICE_API_TOKEN[] = "010a964de84c7ff331ec037d03d312ab2921f4968842f2b3e73c5f41072d5a32";
