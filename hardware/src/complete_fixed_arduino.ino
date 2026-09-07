#include <Arduino.h>
#include <SPI.h>
#include <SD.h>
#include <ESP_I2S.h>
#include <FastLED.h>

// ============================================================
// PINS
// ============================================================

constexpr int SD_CS   = 13;
constexpr int SD_MOSI = 12;
constexpr int SD_SCK  = 11;
constexpr int SD_MISO = 10;

constexpr int I2S_BCLK = 2;
constexpr int I2S_WS   = 3;
constexpr int I2S_DIN  = 1;

constexpr int BUTTON_PIN = 6;
constexpr int LED_PIN = 21;


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

    Serial.print("Creating ");
    Serial.println(filename);

    recordingFile = SD.open(filename, FILE_WRITE);

    if (!recordingFile)
    {
        Serial.println("ERROR: Could not create file");
        setLED(CRGB::Orange);
        return false;
    }

    Serial.println("File created");

    dataBytesWritten = 0;

    // Write placeholder WAV header
    writeWavHeader(recordingFile);

    Serial.println("WAV header written");

    isRecording = true;

    // Purple = Standby
    setLED(CRGB::Purple);

    Serial.println("RECORDING");

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

    Serial.println("Stopping...");

    // Stop collecting samples
    isRecording = false;

    // Blue = saving/finalising
    setLED(CRGB::Blue);

    // Write final WAV sizes
    updateWavHeader(recordingFile);

    // Close file
    recordingFile.close();

    Serial.print("Saved ");
    Serial.print(dataBytesWritten);
    Serial.println(" bytes");

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
    Serial.begin(115200);

    delay(1000);

    Serial.println();
    Serial.println("==============================");
    Serial.println("ESP32 NOTE RECORDER");
    Serial.println("==============================");


    // --------------------------------------------------------
    // LED
    // --------------------------------------------------------

    FastLED.addLeds<WS2812, LED_PIN, GRB>(led, 1);

    FastLED.setBrightness(40);

    setLED(CRGB::Orange);


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

    Serial.println("Initialising SD...");

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
        Serial.println("ERROR: SD card failed");

        setLED(CRGB::Orange);

        return;
    }

    Serial.println("SD card OK.");


    // --------------------------------------------------------
    // I2S
    // --------------------------------------------------------

    Serial.println("Initialising I2S...");

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
        Serial.println("ERROR: I2S failed");

        setLED(CRGB::Orange);

        return;
    }

    Serial.println("I2S OK.");
    Serial.println("READY");
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
}