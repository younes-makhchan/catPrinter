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
constexpr int16_t STATUS_CARD_WIDTH = 230;
constexpr int16_t STATUS_CARD_HEIGHT = 74;
constexpr int16_t STATUS_PATTERN_X_STEP = 62;
constexpr int16_t STATUS_PATTERN_Y_STEP = 72;

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
String printStatusText;
uint16_t printStatusColor = TFT_BLACK;

void drawBlackBorder(int16_t x, int16_t y, int16_t width, int16_t height) {
  display.drawRect(x, y, width, height, TFT_BLACK);
  display.drawRect(x + 1, y + 1, width - 2, height - 2, TFT_BLACK);
}

void drawStatusPattern(const String &symbol, uint16_t color) {
  display.setTextDatum(MC_DATUM);
  display.setTextColor(color);
  display.setTextSize(1);
  for (int16_t y = 28; y < display.height(); y += STATUS_PATTERN_Y_STEP) {
    for (int16_t x = 38; x < display.width(); x += STATUS_PATTERN_X_STEP) {
      display.drawString(symbol, x, y, 4);
    }
  }
}

void showStatusCard(const String &title, uint16_t background, const String &symbol,
                    uint16_t symbolColor) {
  display.fillScreen(background);
  drawStatusPattern(symbol, symbolColor);

  const int16_t width = min<int16_t>(STATUS_CARD_WIDTH, display.width() - 34);
  const int16_t height = min<int16_t>(STATUS_CARD_HEIGHT, display.height() - 34);
  const int16_t x = (display.width() - width) / 2;
  const int16_t y = (display.height() - height) / 2;

  display.fillRect(x, y, width, height, display.color565(235, 252, 255));
  drawBlackBorder(x, y, width, height);
  display.setTextDatum(MC_DATUM);
  display.setTextColor(TFT_BLACK, display.color565(235, 252, 255));
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

void setPrintStatus(const String &text, uint16_t color = TFT_BLACK) {
  printStatusText = text;
  printStatusColor = color;
  if (state == DemoState::Image) {
    showPrintOverlay(printStatusText, printStatusColor);
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
      showStatusCard(
          "Press to talk",
          display.color565(226, 216, 246),
          "?",
          display.color565(112, 84, 158));
      break;
    case DemoState::Listening:
      printStatusText = "";
      showStatusCard(
          "Listening...",
          display.color565(244, 214, 218),
          "!",
          display.color565(145, 78, 86));
      Serial.println("START_LISTENING");
      break;
    case DemoState::Thinking:
      showStatusCard(
          "Thinking...",
          display.color565(255, 243, 178),
          "!",
          display.color565(158, 126, 35));
      Serial.println("STOP_LISTENING");
      Serial.println("PRINT_DEMO");
      break;
    case DemoState::Transcript:
      showTranscript();
      break;
    case DemoState::Image:
      showDemoImage();
      Serial.println("SHOW_IMAGE");
      if (!printStatusText.isEmpty()) {
        showPrintOverlay(printStatusText, printStatusColor);
      }
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
    setPrintStatus("Printing...");
    Serial.println("ACK:PRINTING");
  } else if (message == "PRINT_OK") {
    setPrintStatus("Printed");
    Serial.println("ACK:PRINT_OK");
  } else if (message.startsWith("PRINT_ERROR")) {
    setPrintStatus("Print failed", TFT_RED);
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
