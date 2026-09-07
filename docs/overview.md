# Overview

Moment is a small ESP32-S3 note recorder. The hardware captures audio from an INMP441 microphone to SD card, then the backend will later upload, transcribe, and turn those recordings into notes.

## Device Behavior

- Press the button to start recording.
- Hold the button for 3 seconds to stop.
- Use the WS2812 on GPIO 21 for state feedback such as recording, standby, saving, and uploading.
