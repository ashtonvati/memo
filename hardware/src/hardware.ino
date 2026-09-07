#include <Arduino.h>
#include <SPI.h>
#include <SD.h>
#include <ESP_I2S.h>
#include <FastLED.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <mbedtls/sha256.h>

#include "../include/pinout.h"
#include "../include/secrets.h"

// ============================================================
// PINS
// ============================================================

constexpr int SD_CS   = PIN_SD_CS;
constexpr int SD_MOSI = PIN_SD_MOSI;
constexpr int SD_SCK  = PIN_SD_CLK;
constexpr int SD_MISO = PIN_SD_MISO;

constexpr int I2S_BCLK = PIN_MIC_SCK;
constexpr int I2S_WS   = PIN_MIC_WS;
constexpr int I2S_DIN  = PIN_MIC_DOUT;

constexpr int BUTTON_PIN = PIN_BUTTON;
constexpr int LED_PIN = PIN_LED_WS2812;


// ============================================================
// LED
// ============================================================

CRGB led[1];

void setLED(const CRGB& colour)
{
    led[0] = colour;
    FastLED.show();
}


// ============================================================
// AUDIO SETTINGS
// ============================================================

constexpr uint32_t SAMPLE_RATE = 16000;
constexpr uint16_t BITS_PER_SAMPLE = 16;
constexpr uint16_t CHANNELS = 1;

constexpr size_t BUFFER_SAMPLES = 512;

int32_t i2sBuffer[BUFFER_SAMPLES];
int16_t audioBuffer[BUFFER_SAMPLES];


// ============================================================
// GLOBALS
// ============================================================

I2SClass I2S;
File recordingFile;

bool isRecording = false;

uint32_t recordingNumber = 0;
uint32_t dataBytesWritten = 0;

constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 30000;
constexpr unsigned long WIFI_CONNECT_TIMEOUT_MS = 10000;
constexpr unsigned long UPLOAD_RESPONSE_TIMEOUT_MS = 15000;
constexpr size_t UPLOAD_BUFFER_BYTES = 1024;

unsigned long lastWifiAttemptMs = 0;


// ============================================================
// WAV HELPERS
// ============================================================

void writeLE16(File &file, uint16_t value)
{
    file.write((uint8_t)(value & 0xFF));
    file.write((uint8_t)((value >> 8) & 0xFF));
}


void writeLE32(File &file, uint32_t value)
{
    file.write((uint8_t)(value & 0xFF));
    file.write((uint8_t)((value >> 8) & 0xFF));
    file.write((uint8_t)((value >> 16) & 0xFF));
    file.write((uint8_t)((value >> 24) & 0xFF));
}


// ============================================================
// WAV HEADER
// ============================================================

void writeWavHeader(File &file)
{
    file.write((const uint8_t*)"RIFF", 4);

    // Placeholder for total file size
    writeLE32(file, 0);

    file.write((const uint8_t*)"WAVE", 4);

    // fmt chunk
    file.write((const uint8_t*)"fmt ", 4);
    writeLE32(file, 16);  // PCM fmt chunk size
    writeLE16(file, 1);   // PCM format
    writeLE16(file, CHANNELS);
    writeLE32(file, SAMPLE_RATE);

    uint32_t byteRate =
        SAMPLE_RATE *
        CHANNELS *
        (BITS_PER_SAMPLE / 8);

    uint16_t blockAlign =
        CHANNELS *
        (BITS_PER_SAMPLE / 8);

    writeLE32(file, byteRate);
    writeLE16(file, blockAlign);
    writeLE16(file, BITS_PER_SAMPLE);

    // data chunk
    file.write((const uint8_t*)"data", 4);

    // Placeholder for audio data size
    writeLE32(file, 0);
}


void updateWavHeader(File &file)
{
    uint32_t fileSize = 44 + dataBytesWritten;

    // RIFF chunk size
    file.seek(4);
    writeLE32(file, fileSize - 8);

    // Actual audio data size
    file.seek(40);
    writeLE32(file, dataBytesWritten);
}


// ============================================================
// WIFI AND UPLOAD
// ============================================================

bool connectToNetwork(const char *ssid, const char *password)
{
    WiFi.begin(ssid, password);

    unsigned long startedAt = millis();

    while (WiFi.status() != WL_CONNECTED)
    {
        if (millis() - startedAt >= WIFI_CONNECT_TIMEOUT_MS)
        {
            return false;
        }

        delay(100);
    }

    return true;
}


bool connectToKnownNetwork()
{
    if (WiFi.status() == WL_CONNECTED)
    {
        return true;
    }

    setLED(CRGB::Cyan);
    WiFi.disconnect();

    if (connectToNetwork(HOME_WIFI_SSID, HOME_WIFI_PASSWORD))
    {
        return true;
    }

    setLED(CRGB::Yellow);

    return false;
}


bool calculateSha256(File &file, char *digest, size_t digestSize)
{
    if (digestSize < 65)
    {
        return false;
    }

    uint8_t hash[32];
    uint8_t buffer[UPLOAD_BUFFER_BYTES];
    mbedtls_sha256_context context;
    mbedtls_sha256_init(&context);

    if (mbedtls_sha256_starts_ret(&context, 0) != 0)
    {
        mbedtls_sha256_free(&context);
        return false;
    }

    file.seek(0);

    while (file.available())
    {
        size_t bytesRead = file.read(buffer, sizeof(buffer));

        if (bytesRead == 0 || mbedtls_sha256_update_ret(&context, buffer, bytesRead) != 0)
        {
            mbedtls_sha256_free(&context);
            return false;
        }
    }

    if (mbedtls_sha256_finish_ret(&context, hash) != 0)
    {
        mbedtls_sha256_free(&context);
        return false;
    }

    mbedtls_sha256_free(&context);

    for (size_t i = 0; i < sizeof(hash); i++)
    {
        snprintf(digest + (i * 2), 3, "%02x", hash[i]);
    }

    digest[64] = '\0';
    file.seek(0);

    return true;
}


bool uploadFile(File &file, const char *filename)
{
    char checksum[65];

    if (!calculateSha256(file, checksum, sizeof(checksum)))
    {
        return false;
    }

    const char boundary[] = "----moment-esp32-boundary";
    String prefix =
        String("--") + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"device_id\"\r\n\r\n" + DEVICE_ID + "\r\n"
        "--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"filename\"\r\n\r\n" + filename + "\r\n"
        "--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"sha256\"\r\n\r\n" + checksum + "\r\n"
        "--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"audio\"; filename=\"" + filename + "\"\r\n"
        "Content-Type: audio/wav\r\n\r\n";
    String suffix = String("\r\n--") + boundary + "--\r\n";
    size_t contentLength = prefix.length() + file.size() + suffix.length();

    WiFiClient client;

    if (!client.connect(API_HOST, API_PORT))
    {
        return false;
    }

    client.printf("POST %s HTTP/1.1\r\n", API_PATH);
    client.printf("Host: %s\r\n", API_HOST);
    client.printf("Authorization: Bearer %s\r\n", DEVICE_API_TOKEN);
    client.printf("Content-Type: multipart/form-data; boundary=%s\r\n", boundary);
    client.printf("Content-Length: %u\r\n", (unsigned int)contentLength);
    client.print("Connection: close\r\n\r\n");
    client.print(prefix);

    uint8_t buffer[UPLOAD_BUFFER_BYTES];

    while (file.available())
    {
        size_t bytesRead = file.read(buffer, sizeof(buffer));

        if (bytesRead == 0 || client.write(buffer, bytesRead) != bytesRead)
        {
            client.stop();
            return false;
        }
    }

    client.print(suffix);

    unsigned long startedAt = millis();

    while (!client.available())
    {
        if (millis() - startedAt >= UPLOAD_RESPONSE_TIMEOUT_MS)
        {
            client.stop();
            return false;
        }

        delay(10);
    }

    String statusLine = client.readStringUntil('\n');
    client.stop();

    return statusLine.indexOf(" 200 ") >= 0 || statusLine.indexOf(" 201 ") >= 0;
}


void syncRecordings()
{
    if (!connectToKnownNetwork())
    {
        return;
    }

    File root = SD.open("/");

    if (!root)
    {
        return;
    }

    File file = root.openNextFile();

    while (file)
    {
        String path = file.name();
        bool isWav = !file.isDirectory() && path.endsWith(".wav");

        if (isWav)
        {
            setLED(CRGB::Green);
            bool uploaded = uploadFile(file, path.c_str());
            file.close();

            if (uploaded)
            {
                SD.remove(path.c_str());
            }
            else
            {
                root.close();
                setLED(CRGB::Yellow);
                return;
            }
        }
        else
        {
            file.close();
        }

        file = root.openNextFile();
    }

    root.close();
    setLED(CRGB::Yellow);
}


// ============================================================
// START RECORDING
// ============================================================

bool startRecording()
{
    char filename[32];

    // Find an unused filename
    while (true)
    {
        snprintf(
            filename,
            sizeof(filename),
            "/recording_%03lu.wav",
            (unsigned long)recordingNumber
        );

        recordingNumber++;

        if (!SD.exists(filename))
        {
            break;
        }
    }

    recordingFile = SD.open(filename, FILE_WRITE);

    if (!recordingFile)
    {
        setLED(CRGB::Orange);
        return false;
    }

    dataBytesWritten = 0;

    // Write placeholder WAV header
    writeWavHeader(recordingFile);

    isRecording = true;

    // Purple = Standby
    setLED(CRGB::Purple);

    return true;
}


// ============================================================
// STOP RECORDING
// ============================================================

void stopRecording()
{
    if (!isRecording)
    {
        return;
    }

    // Stop collecting samples
    isRecording = false;

    // Blue = saving/finalising
    setLED(CRGB::Blue);

    // Write final WAV sizes
    updateWavHeader(recordingFile);

    // Close file
    recordingFile.close();

    // Yellow = Recording
    setLED(CRGB::Yellow);
}


// ============================================================
// RECORD AUDIO
// ============================================================

void recordAudio()
{
    if (!recordingFile)
    {
        return;
    }

    size_t bytesAvailable = I2S.available();

    if (bytesAvailable < sizeof(int32_t))
    {
        return;
    }

    // Don't exceed our buffer
    size_t maxBytes =
        BUFFER_SAMPLES * sizeof(int32_t);

    if (bytesAvailable > maxBytes)
    {
        bytesAvailable = maxBytes;
    }

    // Only read complete 32-bit samples
    bytesAvailable -=
        bytesAvailable % sizeof(int32_t);

    if (bytesAvailable == 0)
    {
        return;
    }

    // Read raw microphone samples
    size_t bytesRead =
        I2S.readBytes(
            (char*)i2sBuffer,
            bytesAvailable
        );

    if (bytesRead == 0)
    {
        return;
    }

    size_t samplesRead =
        bytesRead / sizeof(int32_t);


    // ========================================================
    // CONVERT INMP441 SAMPLE → 16-BIT PCM
    // ========================================================

    for (size_t i = 0; i < samplesRead; i++)
    {
        // The raw I2S sample contains the microphone's
        // 24-bit audio in a 32-bit container.
        //
        // Shifting by 12 gives us a useful 16-bit
        // representation for the WAV file.

        int32_t sample =
            i2sBuffer[i] >> 13;


        // Clamp to signed 16-bit range
        if (sample > 32767)
        {
            sample = 32767;
        }
        else if (sample < -32768)
        {
            sample = -32768;
        }


        audioBuffer[i] =
            (int16_t)sample;
    }


    // ========================================================
    // WRITE PCM DATA TO SD
    // ========================================================

    size_t bytesToWrite =
        samplesRead * sizeof(int16_t);

    size_t bytesWritten =
        recordingFile.write(
            (const uint8_t*)audioBuffer,
            bytesToWrite
        );

    dataBytesWritten += bytesWritten;
}


// ============================================================
// SETUP
// ============================================================

void setup()
{
    // --------------------------------------------------------
    // LED
    // --------------------------------------------------------

    FastLED.addLeds<WS2812, LED_PIN, GRB>(led, 1);

    FastLED.setBrightness(40);

    setLED(CRGB::Orange);

    WiFi.mode(WIFI_STA);
    lastWifiAttemptMs = millis() - WIFI_RETRY_INTERVAL_MS;


    // --------------------------------------------------------
    // BUTTON
    // --------------------------------------------------------

    pinMode(
        BUTTON_PIN,
        INPUT_PULLUP
    );


    // --------------------------------------------------------
    // SD CARD
    // --------------------------------------------------------

    SPI.begin(
        SD_SCK,
        SD_MISO,
        SD_MOSI,
        SD_CS
    );

    if (!SD.begin(
        SD_CS,
        SPI,
        20000000
    ))
    {
        setLED(CRGB::Orange);

        return;
    }


    // --------------------------------------------------------
    // I2S
    // --------------------------------------------------------

    I2S.setPins(
        I2S_BCLK,
        I2S_WS,
        -1,
        I2S_DIN
    );


    bool i2sStarted =
        I2S.begin(
            I2S_MODE_STD,
            SAMPLE_RATE,
            I2S_DATA_BIT_WIDTH_32BIT,
            I2S_SLOT_MODE_MONO,
            I2S_STD_SLOT_LEFT
        );


    if (!i2sStarted)
    {
        setLED(CRGB::Orange);

        return;
    }
}


// ============================================================
// MAIN LOOP
// ============================================================

void loop()
{
    static bool previousButtonState = HIGH;

    bool currentButtonState =
        digitalRead(BUTTON_PIN);


    // --------------------------------------------------------
    // Detect button press
    // --------------------------------------------------------

    if (
        previousButtonState == HIGH &&
        currentButtonState == LOW
    )
    {
        // Debounce
        delay(30);

        if (digitalRead(BUTTON_PIN) == LOW)
        {
            if (isRecording)
            {
                stopRecording();
            }
            else
            {
                startRecording();
            }

            // Wait until the button is released
            while (digitalRead(BUTTON_PIN) == LOW)
            {
                delay(1);
            }
        }
    }


    previousButtonState = currentButtonState;


    // --------------------------------------------------------
    // Record
    // --------------------------------------------------------

    if (isRecording)
    {
        recordAudio();
    }
    else if (millis() - lastWifiAttemptMs >= WIFI_RETRY_INTERVAL_MS)
    {
        lastWifiAttemptMs = millis();
        syncRecordings();
    }
}
