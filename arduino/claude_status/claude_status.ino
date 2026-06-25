/**
 * Claude Code 状态显示器
 * ======================
 * 从串口接收 Claude Code 工作状态码并显示在 8x12 LED Matrix 上。
 *
 * 通信协议 (与 monitor.py 一致):
 *   串口 115200 baud, 格式: <状态码>,0\n
 *   例如: "5,0\n" 显示状态码 5
 *
 * 状态码含义 (显示时会添加前缀 S, 如 S5):
 *   0 = IDLE      空闲
 *   1 = LOADING   启动
 *   2 = THINKING  思考
 *   3 = READING   读文件
 *   4 = WRITING   写代码
 *   5 = SEARCHING 搜索
 *   6 = BUILDING  编译
 *   7 = COMMAND   命令
 *   8 = WAITING   等待
 *   9 = PROCESSING 处理中
 *   10 = DONE     完成
 *   11 = ERROR    错误
 */

#include "Arduino_LED_Matrix.h"

ArduinoLEDMatrix matrix;

#define MAX_Y 8
#define MAX_X 12
uint8_t displayGrid[MAX_Y][MAX_X] = {0};

int currentStatus = 0;
int lastStatus = -1;
unsigned long lastBlinkTime = 0;
bool blinkOn = true;
const long blinkInterval = 400;  // 闪烁间隔 (ms)

// 状态码前缀 "S" 的像素映射 (8x3)
const bool fontS[8][3] = {
  {1,1,1},
  {1,0,0},
  {1,0,0},
  {1,1,1},
  {0,0,1},
  {0,0,1},
  {0,0,1},
  {1,1,1}
};

// 数字 0-9 字模 (8x3)
const bool fontDigits[10][8][3] = {
  {{1,1,1},{1,0,1},{1,0,1},{1,0,1},{1,0,1},{1,0,1},{1,0,1},{1,1,1}}, // 0
  {{0,1,0},{1,1,0},{0,1,0},{0,1,0},{0,1,0},{0,1,0},{0,1,0},{1,1,1}}, // 1
  {{1,1,1},{0,0,1},{0,0,1},{1,1,1},{1,0,0},{1,0,0},{1,0,0},{1,1,1}}, // 2
  {{1,1,1},{0,0,1},{0,0,1},{1,1,1},{0,0,1},{0,0,1},{0,0,1},{1,1,1}}, // 3
  {{1,0,1},{1,0,1},{1,0,1},{1,1,1},{0,0,1},{0,0,1},{0,0,1},{0,0,1}}, // 4
  {{1,1,1},{1,0,0},{1,0,0},{1,1,1},{0,0,1},{0,0,1},{0,0,1},{1,1,1}}, // 5
  {{1,1,1},{1,0,0},{1,0,0},{1,1,1},{1,0,1},{1,0,1},{1,0,1},{1,1,1}}, // 6
  {{1,1,1},{0,0,1},{0,0,1},{0,0,1},{0,0,1},{0,0,1},{0,0,1},{0,0,1}}, // 7
  {{1,1,1},{1,0,1},{1,0,1},{1,1,1},{1,0,1},{1,0,1},{1,0,1},{1,1,1}}, // 8
  {{1,1,1},{1,0,1},{1,0,1},{1,1,1},{0,0,1},{0,0,1},{0,0,1},{1,1,1}}  // 9
};

// 显示帧缓存
uint8_t frameBuffer[MAX_Y][MAX_X] = {0};

void setup() {
  Serial.begin(115200);
  matrix.begin();
  clearGrid();
  matrix.renderBitmap(displayGrid, MAX_Y, MAX_X);
}

void loop() {
  static char buffer[16];
  static int index = 0;

  // 读取串口数据
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (index > 0) {
        buffer[index] = '\0';
        int status = parseStatus(buffer);
        if (status >= 0 && status <= 99) {
          currentStatus = status;
        }
        index = 0;
      }
    } else if (index < 14) {
      buffer[index++] = c;
    }
  }

  // 检测状态变化
  if (currentStatus != lastStatus) {
    lastStatus = currentStatus;
    // 状态变化时暂停闪烁、立即刷新
    blinkOn = true;
    lastBlinkTime = millis();
    renderStatus(currentStatus);
    matrix.renderBitmap(displayGrid, MAX_Y, MAX_X);
  }

  // 特殊状态动画：
  //   IDLE(0) - 常亮显示
  //   THINKING(2) - 闪烁
  //   BUILDING(6) - 闪烁
  //   ERROR(11) - 快速闪烁
  //   其他 - 常亮
  bool needBlink = (currentStatus == 2 || currentStatus == 6 || currentStatus == 11);
  if (needBlink) {
    unsigned long now = millis();
    int interval = (currentStatus == 11) ? 200 : blinkInterval;
    if (now - lastBlinkTime >= interval) {
      lastBlinkTime = now;
      blinkOn = !blinkOn;
      if (blinkOn) {
        renderStatus(currentStatus);
      } else {
        clearGrid();
      }
      matrix.renderBitmap(displayGrid, MAX_Y, MAX_X);
    }
  }
}

/**
 * 解析状态码
 * 支持格式: "数字" 或 "数字,0"
 * 例如: "5" 或 "5,0" 都返回 5
 */
int parseStatus(char* data) {
  char* comma = strchr(data, ',');
  if (comma) {
    *comma = '\0';
  }
  int val = atoi(data);
  if (val < 0) val = 0;
  if (val > 99) val = 99;
  return val;
}

void clearGrid() {
  for (int y = 0; y < MAX_Y; y++)
    for (int x = 0; x < MAX_X; x++)
      displayGrid[y][x] = 0;
}

/**
 * 在指定 x 偏移绘制数字
 */
void drawDigit(int num, int xOffset) {
  for (int y = 0; y < 8; y++)
    for (int x = 0; x < 3; x++) {
      int px = xOffset + x;
      if (px >= 0 && px < MAX_X)
        displayGrid[y][px] = fontDigits[num][y][x];
    }
}

/**
 * 绘制字母 S (3列宽)
 */
void drawS(int xOffset) {
  for (int y = 0; y < 8; y++)
    for (int x = 0; x < 3; x++) {
      int px = xOffset + x;
      if (px >= 0 && px < MAX_X)
        displayGrid[y][px] = fontS[y][x];
    }
}

/**
 * 渲染状态码到 LED Matrix
 * 布局: S + <数字> (居中显示)
 * 0-9:   "S  数字"  (占用 3+1+3=7列)
 * 10-99: "S 十位个位" (占用 3+1+3+3=10列)
 */
void renderStatus(int status) {
  clearGrid();

  if (status <= 9) {
    // 单位数: S + 数字, 居中
    drawS(0);
    drawDigit(status, 5);
  } else {
    // 双位数: S + 十位 + 个位, 居中
    drawS(0);
    int tens = status / 10;
    int ones = status % 10;
    drawDigit(tens, 4);
    drawDigit(ones, 8);
  }
}
