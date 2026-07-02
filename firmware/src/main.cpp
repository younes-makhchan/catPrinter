#include <Arduino.h>
#include <LittleFS.h>
#include <TFT_eSPI.h>
#include <TJpg_Decoder.h>

namespace {

constexpr uint8_t BUTTON_PIN = 26;
constexpr uint32_t DEBOUNCE_MS = 30;
constexpr uint32_t MIN_STAGE_MS = 250;
constexpr uint32_t MAX_STAGE_MS = 10000;
constexpr char DEMO_IMAGE[] = "/demo.jpg";
constexpr char TRANSCRIPT_END_MARK[] = ".";
constexpr int16_t TRANSCRIPT_BORDER = 4;
constexpr int16_t TRANSCRIPT_X = 18;
constexpr int16_t TRANSCRIPT_Y = 16;
constexpr int16_t TRANSCRIPT_LINE_GAP = 78;
constexpr uint8_t TRANSCRIPT_TEXT_SIZE = 3;
constexpr uint8_t TRANSCRIPT_FONT = 4;

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
String demoTranscript = "six,seven";
uint32_t thinkingMs = 2000;
uint32_t transcriptMs = 1800;

void drawBlackBorder(int16_t x, int16_t y, int16_t width, int16_t height) {
  display.drawRect(x, y, width, height, TFT_BLACK);
  display.drawRect(x + 1, y + 1, width - 2, height - 2, TFT_BLACK);
}

void showStatusCard(const String &title, uint16_t background) {
  display.fillScreen(background);

  const int16_t size = min(display.width(), display.height()) - 44;
  const int16_t x = (display.width() - size) / 2;
  const int16_t y = (display.height() - size) / 2;

  display.fillRect(x, y, size, size, TFT_WHITE);
  drawBlackBorder(x, y, size, size);
  display.setTextDatum(MC_DATUM);
  display.setTextColor(TFT_BLACK, TFT_WHITE);
  display.setTextSize(1);
  display.drawString(title, display.width() / 2, display.height() / 2, 4);
}

void showMessage(const String &title, const String &subtitle = "") {
  display.fillScreen(TFT_WHITE);
  drawBlackBorder(4, 4, display.width() - 8, display.height() - 8);
  display.setTextDatum(MC_DATUM);
  display.setTextColor(TFT_BLACK, TFT_WHITE);
  display.setTextSize(1);
  display.drawString(title, display.width() / 2, display.height() / 2 - 12, 4);
  if (!subtitle.isEmpty()) {
    display.drawString(subtitle, display.width() / 2, display.height() / 2 + 25, 2);
  }
}

void showTranscript() {
  display.fillScreen(TFT_WHITE);
  drawBlackBorder(
      TRANSCRIPT_BORDER,
      TRANSCRIPT_BORDER,
      display.width() - TRANSCRIPT_BORDER * 2,
      display.height() - TRANSCRIPT_BORDER * 2);
  display.setTextDatum(TL_DATUM);
  display.setTextColor(TFT_BLACK, TFT_WHITE);
  display.setTextSize(TRANSCRIPT_TEXT_SIZE);

  String remaining = demoTranscript;
  remaining.replace(",", "\n");

  int16_t y = TRANSCRIPT_Y;
  while (remaining.length() && y < display.height() - TRANSCRIPT_LINE_GAP) {
    int16_t separator = remaining.indexOf('\n');
    String line = separator >= 0 ? remaining.substring(0, separator) : remaining;
    line.trim();
    if (!line.isEmpty()) {
      if (separator < 0 && !line.endsWith(TRANSCRIPT_END_MARK)) {
        line += TRANSCRIPT_END_MARK;
      }
      display.drawString(line, TRANSCRIPT_X, y, TRANSCRIPT_FONT);
      y += TRANSCRIPT_LINE_GAP;
    }
    if (separator < 0) {
      break;
    }
    remaining = remaining.substring(separator + 1);
  }

  display.setTextSize(1);
}

void showPrintOverlay(const String &text, uint16_t color = TFT_BLACK) {
  const int16_t height = 30;
  const int16_t y = display.height() - height - 6;
  display.fillRect(8, y, display.width() - 16, height, TFT_WHITE);
  drawBlackBorder(8, y, display.width() - 16, height);
  display.setTextDatum(MC_DATUM);
  display.setTextColor(color, TFT_WHITE);
  display.setTextSize(1);
  display.drawString(text, display.width() / 2, y + height / 2, 2);
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
      showStatusCard("Press to talk", display.color565(255, 218, 222));
      break;
    case DemoState::Listening:
      showStatusCard("Listening...", display.color565(230, 220, 255));
      Serial.println("START_LISTENING");
      break;
    case DemoState::Thinking:
      showStatusCard("Thinking...", display.color565(255, 245, 175));
      Serial.println("STOP_LISTENING");
      break;
    case DemoState::Transcript:
      showTranscript();
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
  if (state == DemoState::Thinking && elapsed >= thinkingMs) {
    enterState(DemoState::Transcript);
  } else if (state == DemoState::Transcript && elapsed >= transcriptMs) {
    enterState(DemoState::Image);
  }
}

uint32_t parseStageMs(const String &value, uint32_t fallback) {
  const uint32_t parsed = value.toInt();
  if (parsed < MIN_STAGE_MS || parsed > MAX_STAGE_MS) {
    return fallback;
  }
  return parsed;
}

void handleLaptopMessage(const String &message) {
  if (message.startsWith("CFG_TEXT=")) {
    const String value = message.substring(9);
    if (!value.isEmpty() && value.length() <= 48) {
      demoTranscript = value;
    }
    Serial.println("ACK:CFG_TEXT");
  } else if (message.startsWith("CFG_THINK_MS=")) {
    thinkingMs = parseStageMs(message.substring(13), thinkingMs);
    Serial.println("ACK:CFG_THINK_MS");
  } else if (message.startsWith("CFG_TRANSCRIPT_MS=")) {
    transcriptMs = parseStageMs(message.substring(18), transcriptMs);
    Serial.println("ACK:CFG_TRANSCRIPT_MS");
  } else if (message == "PRINTING") {
    showPrintOverlay("Printing...");
    Serial.println("ACK:PRINTING");
  } else if (message == "PRINT_OK") {
    showPrintOverlay("Printed");
    Serial.println("ACK:PRINT_OK");
  } else if (message.startsWith("PRINT_ERROR")) {
    showPrintOverlay("Print failed", TFT_RED);
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
