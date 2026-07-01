#include <Arduino.h>
#include <LittleFS.h>
#include <TFT_eSPI.h>
#include <TJpg_Decoder.h>

namespace {

constexpr uint8_t BUTTON_PIN = 15;
constexpr uint32_t DEBOUNCE_MS = 30;
constexpr uint32_t THINKING_MS = 2000;
constexpr uint32_t TRANSCRIPT_MS = 1800;
constexpr char DEMO_IMAGE[] = "/demo.jpg";
constexpr char DEMO_TRANSCRIPT[] = "six,seven";

TFT_eSPI display;

enum class DemoState {
  Idle,
  Listening,
  Thinking,
  Transcript,
  Image,
};

DemoState state = DemoState::Idle;
uint32_t stateStartedAt = 0;
bool stableButtonPressed = false;
bool lastRawButtonPressed = false;
uint32_t buttonChangedAt = 0;
String laptopMessage;

void centerText(const String &text, uint16_t color = TFT_BLACK) {
  display.setTextDatum(MC_DATUM);
  display.setTextColor(color, TFT_WHITE);
  display.drawString(text, display.width() / 2, display.height() / 2, 4);
}

void showMessage(const String &title, const String &subtitle = "") {
  display.fillScreen(TFT_WHITE);
  display.setTextDatum(MC_DATUM);
  display.setTextColor(TFT_BLACK, TFT_WHITE);
  display.drawString(title, display.width() / 2, display.height() / 2 - 12, 4);
  if (!subtitle.isEmpty()) {
    display.drawString(subtitle, display.width() / 2, display.height() / 2 + 25, 2);
  }
}

bool jpegBlock(int16_t x, int16_t y, uint16_t width, uint16_t height,
               uint16_t *pixels) {
  if (y >= display.height()) {
    return false;
  }
  display.pushImage(x, y, width, height, pixels);
  return true;
}

void showDemoImage() {
  display.fillScreen(TFT_WHITE);
  if (!LittleFS.exists(DEMO_IMAGE)) {
    showMessage("Image missing", "Upload LittleFS");
    return;
  }

  uint16_t width = 0;
  uint16_t height = 0;
  TJpgDec.getFsJpgSize(&width, &height, DEMO_IMAGE, LittleFS);

  uint8_t scale = 1;
  while (scale < 8 &&
         (width / scale > display.width() || height / scale > display.height())) {
    scale *= 2;
  }
  TJpgDec.setJpgScale(scale);

  const int16_t x = max(0, (display.width() - static_cast<int>(width / scale)) / 2);
  const int16_t y = max(0, (display.height() - static_cast<int>(height / scale)) / 2);
  TJpgDec.drawFsJpg(x, y, DEMO_IMAGE, LittleFS);
}

void enterState(DemoState next) {
  state = next;
  stateStartedAt = millis();

  switch (state) {
    case DemoState::Idle:
      showMessage("Press to talk", "Hold the button");
      break;
    case DemoState::Listening:
      showMessage("Listening...", "Release when done");
      Serial.println("START_LISTENING");
      break;
    case DemoState::Thinking:
      showMessage("Thinking...");
      Serial.println("STOP_LISTENING");
      break;
    case DemoState::Transcript:
      showMessage(DEMO_TRANSCRIPT, "Generating image...");
      break;
    case DemoState::Image:
      showDemoImage();
      Serial.println("PRINT_DEMO");
      break;
  }
}

void updateButton() {
  const bool rawPressed = digitalRead(BUTTON_PIN) == LOW;
  if (rawPressed != lastRawButtonPressed) {
    lastRawButtonPressed = rawPressed;
    buttonChangedAt = millis();
  }

  if (millis() - buttonChangedAt < DEBOUNCE_MS ||
      rawPressed == stableButtonPressed) {
    return;
  }

  stableButtonPressed = rawPressed;
  if (stableButtonPressed && state != DemoState::Listening) {
    enterState(DemoState::Listening);
  } else if (!stableButtonPressed && state == DemoState::Listening) {
    enterState(DemoState::Thinking);
  }
}

void updateDemo() {
  const uint32_t elapsed = millis() - stateStartedAt;
  if (state == DemoState::Thinking && elapsed >= THINKING_MS) {
    enterState(DemoState::Transcript);
  } else if (state == DemoState::Transcript && elapsed >= TRANSCRIPT_MS) {
    enterState(DemoState::Image);
  }
}

void handleLaptopMessage(const String &message) {
  if (message == "PRINTING") {
    display.fillRect(0, display.height() - 24, display.width(), 24, TFT_WHITE);
    display.setTextDatum(BC_DATUM);
    display.setTextColor(TFT_BLACK, TFT_WHITE);
    display.drawString("Printing...", display.width() / 2, display.height() - 3, 2);
    Serial.println("ACK:PRINTING");
  } else if (message == "PRINT_OK") {
    display.fillRect(0, display.height() - 24, display.width(), 24, TFT_WHITE);
    display.setTextDatum(BC_DATUM);
    display.setTextColor(TFT_BLACK, TFT_WHITE);
    display.drawString("Printed", display.width() / 2, display.height() - 3, 2);
    Serial.println("ACK:PRINT_OK");
  } else if (message.startsWith("PRINT_ERROR")) {
    display.fillRect(0, display.height() - 24, display.width(), 24, TFT_WHITE);
    display.setTextDatum(BC_DATUM);
    display.setTextColor(TFT_RED, TFT_WHITE);
    display.drawString("Print failed", display.width() / 2, display.height() - 3, 2);
    Serial.println("ACK:PRINT_ERROR");
  }
}

void readLaptopMessages() {
  while (Serial.available()) {
    const char value = static_cast<char>(Serial.read());
    if (value == '\n') {
      laptopMessage.trim();
      if (!laptopMessage.isEmpty()) {
        handleLaptopMessage(laptopMessage);
      }
      laptopMessage = "";
    } else if (value != '\r') {
      laptopMessage += value;
    }
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  display.init();
  display.setRotation(1);
  display.fillScreen(TFT_WHITE);

  TJpgDec.setSwapBytes(true);
  TJpgDec.setCallback(jpegBlock);

  if (!LittleFS.begin(false)) {
    showMessage("LittleFS error", "Run uploadfs");
  } else {
    enterState(DemoState::Idle);
  }
}

void loop() {
  updateButton();
  updateDemo();
  readLaptopMessages();
  delay(5);
}
