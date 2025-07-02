#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include "esp_camera.h"

#define CAMERA_MODEL_XIAO_ESP32S3
#include "camera_pins.h"

#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define IMAGE_UUID          "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define DATA_UUID           "80dcca86-d593-484b-8b13-72db9d98faea"
#define CONTROL_UUID        "a9da86e1-4456-4bea-b82d-b7a8e834bb0a"
#define SCREEN_ADDRESS      0x3C

// OLED Display settings
#define SCREEN_WIDTH 128 // OLED display width, in pixels
#define SCREEN_HEIGHT 64 // OLED display height, in pixels
#define OLED_RESET    -1 // Reset pin # (or -1 if sharing Arduino reset pin)

// Button definitions
#define CONFIRM_BTN 1
#define DOWN_BTN 2
#define UP_BTN 3
#define LED_PIN 4

// User data structure
struct UserData {
  String name;
  String surname;
  int age;
  float weight;
  float height;
  String diseases[3];
  String medications[3];
};

// Menu variables
int currentMenuIndex = 0;
const int maxMenuItems = 3; // Page 1: Personal info, Page 2: Diseases, Page 3: Medications
UserData userData;
bool hasUserData = false;

static BLECharacteristic *image_char;
static BLECharacteristic *data_char;
static BLECharacteristic *control_char;

// OLED display
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

void send_specific_chunk(int chunk_idx);
void send_metadata();
void cleanup_transfer();
void display_loading_screen();
void display_processing_screen();
void display_user_data();
void display_menu_item(int index);
void parse_user_data(String json);

// Global variables for image chunking
camera_fb_t *current_fb = NULL;
int total_chunks = 0;
int current_chunk_idx = 0;
bool transfer_in_progress = false;

class ControlCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) {
    std::string value = pCharacteristic->getValue().c_str();

    if (value.length() > 0) {
      // Parse the control message
      // Expected format: "GET:chunk_index" or "READY" or "CANCEL"
      String control = String(value.c_str());
      Serial.print("Control message: ");
      Serial.println(control);
      
      if (control.startsWith("GET:")) {
        int chunk_idx = control.substring(4).toInt();
        send_specific_chunk(chunk_idx);
      }
      else if (control.equals("READY")) {
        // Client is ready to receive the metadata
        send_metadata();
      }
      else if (control.equals("CANCEL")) {
        // Client wants to cancel the transfer
        cleanup_transfer();
      }
    }
  }
};

class DataCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) {
    std::string value = pCharacteristic->getValue().c_str();

    if (value.length() > 0) {
      Serial.println("*********");
      Serial.print("New value received: ");
      String jsonString = String(value.c_str());
      Serial.println(jsonString);
      
      // Check if this is JSON data (starts with {)
      if (jsonString.startsWith("{")) {
        parse_user_data(jsonString);
        display_user_data(); // Show the data on the screen
      }
      
      Serial.println("*********");
    }
  }
};

void setup_ble() {
  BLEDevice::init("EWatch");
  BLEServer *server = BLEDevice::createServer();

  BLEService *service = server->createService(SERVICE_UUID);

  image_char = service->createCharacteristic(IMAGE_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  data_char = service->createCharacteristic(DATA_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  control_char = service->createCharacteristic(CONTROL_UUID, BLECharacteristic::PROPERTY_WRITE);
  
  data_char->setCallbacks(new DataCallback());
  control_char->setCallbacks(new ControlCallback());

  service->start();

  BLEAdvertising *advertising = server->getAdvertising();
  advertising->start();
  
  Serial.println("BLE server initialized with batch notification support");
}

void send_metadata() {
  if (!current_fb || !transfer_in_progress) {
    Serial.println("No image ready to send");
    return;
  }
  
  const int chunk_size = 512; // BLE friendly size
  total_chunks = ceil(current_fb->len / (float)chunk_size);
  
  String metadata = String(current_fb->len) + "," + String(total_chunks);
  data_char->setValue(metadata.c_str());
  data_char->notify();
  
  Serial.print("Image metadata sent: ");
  Serial.println(metadata);
}

void send_specific_chunk(int chunk_idx) {
  if (!current_fb || !transfer_in_progress || chunk_idx >= total_chunks) {
    Serial.println("Invalid chunk request");
    return;
  }
  
  const int chunk_size = 512;
  int offset = chunk_idx * chunk_size;
    int remaining = current_fb->len - offset;
    int length = (chunk_size < remaining) ? chunk_size : remaining;
  
    if (length <= 0) {
      Serial.println("Invalid chunk length");
    return;
  }
    
  // Send chunk with header info (chunk index)
  String header = String(chunk_idx) + ":"; // format: chunk_idx:batch_position:batch_size
    image_char->setValue(header.c_str());
  
  // Now send the actual chunk data
  image_char->setValue(current_fb->buf + offset, length);
  image_char->notify();
    
  Serial.printf("Sent chunk %d/%d (size: %d)\n", chunk_idx + 1, total_chunks, length);
  
    // If this is the last chunk, clean up
  if (chunk_idx == total_chunks - 1) {
      Serial.println("Last chunk sent, transfer complete");
      cleanup_transfer();
  }
}

void cleanup_transfer() {
  if (current_fb) {
    esp_camera_fb_return(current_fb);
    current_fb = NULL;
  }
  transfer_in_progress = false;
  total_chunks = 0;
  current_chunk_idx = 0;
  
  // Notify client transfer is done
  data_char->setValue("DONE");
  data_char->notify();
  
  display_loading_screen();
}

void setup_camera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;  // for streaming
  //config.pixel_format = PIXFORMAT_RGB565; // for face detection/recognition
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 5;  // Lower number means higher quality (range is 0-63)
  config.fb_count = 1;

  // if PSRAM IC present, init with UXGA resolution and higher JPEG quality
  //    
  if (config.pixel_format == PIXFORMAT_JPEG) {
    if (psramFound()) {
      config.jpeg_quality = 4;  // Higher quality for PSRAM (0 is highest quality, 63 is lowest)
      config.fb_count = 2;
      config.grab_mode = CAMERA_GRAB_LATEST;
    } else {
      // Limit the frame size when PSRAM is not available
      config.frame_size = FRAMESIZE_SVGA;
      config.fb_location = CAMERA_FB_IN_DRAM;
    }
  } else {
    // Best option for face detection/recognition
    config.frame_size = FRAMESIZE_240X240;
    config.fb_count = 2;
  }

  // camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  // initial sensors are flipped vertically and colors are a bit saturated
  if (s->id.PID == OV3660_PID) {
    //s->set_vflip(s, 1);        // flip it vertically
    s->set_hmirror(s, 1);      // flip it horizontally
    s->set_brightness(s, 1);   // up the brightness just a bit
    //s->set_saturation(s, -2);  // lower the saturation
  }
  // drop down frame size for higher initial frame rate
  if (config.pixel_format == PIXFORMAT_JPEG) {
    s->set_framesize(s, FRAMESIZE_VGA);  // Increased from QVGA to VGA for better quality
    s->set_quality(s, 10);  // Set higher quality (0-63, lower is better)
    s->set_contrast(s, 2);  // Slightly increase contrast for better image detail
    s->set_saturation(s, 1);  // Slightly increased saturation for more vivid colors
  }
}

void send_chunks(uint8_t* image_data, size_t image_size) {
  const int chunk_size = 512; // BLE friendly size
  int chunks = ceil(image_size / (float)chunk_size);
  
  String metadata = String(image_size) + "," + String(chunks);
  data_char->setValue(metadata.c_str());
  
  for (int i = 0; i < chunks; i++) {
    int offset = i * chunk_size;
    int curr_size = image_size - offset;
    int length = chunk_size < curr_size ? chunk_size : curr_size;
    
    image_char->setValue(image_data + offset, length);
    //delay(100); // Give client time to process
  }
}

void take_picture() {
  // Clean up any previous transfer
  if (transfer_in_progress) {
    cleanup_transfer();
  }
  
  // Show processing screen
  display_processing_screen();
  
  // Turn on LED
  digitalWrite(LED_PIN, HIGH);
  
  // Flush the buffer by reading and discarding a frame
  camera_fb_t* flush_fb = esp_camera_fb_get();
  if (flush_fb) {
    esp_camera_fb_return(flush_fb);
  }
  
  // Short delay to ensure we get a fresh frame
  delay(100);
  
  // Now get the fresh frame
  camera_fb_t* fb = esp_camera_fb_get();  
  if(!fb) {
    Serial.println("Camera capture failed");
    digitalWrite(LED_PIN, LOW); // Turn off LED if capture failed
    display_loading_screen(); // Go back to loading screen
    return;
  }
  
  Serial.printf("Picture taken. Length: %d\n", fb->len);
  
  // Store the image for chunked transfer
  current_fb = fb;
  transfer_in_progress = true;
  
  // Notify client that image is ready - client should respond with READY to get metadata
  data_char->setValue("IMAGE_READY");
  data_char->notify();
  
  // Keep LED on for the remainder of the 2 seconds
  // delay(1900); // 1900 ms + the ~100ms already passed = ~2 seconds
  
  // Turn off LED
  digitalWrite(LED_PIN, LOW);
  
  // Keep showing the processing screen until we receive data
}

void setup() {
  Serial.begin(115200);
  
  // Initialize I2C for OLED
  Wire.begin();
  
  // Initialize OLED display first to show loading status
  setup_display();
  
  // Setup other components
  setup_ble();
  setup_camera();

  pinMode(CONFIRM_BTN, INPUT_PULLUP);
  pinMode(UP_BTN, INPUT_PULLUP);
  pinMode(DOWN_BTN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW); // Turn off LED initially
}

void loop() {
  // Check for button presses
  if (digitalRead(CONFIRM_BTN) == LOW) {
    Serial.println("Confirm button pressed");
    take_picture();
    delay(500); // Debounce
  }
  
  // Handle UP button for menu navigation
  if (digitalRead(UP_BTN) == LOW) {
    if (hasUserData) {
      currentMenuIndex = (currentMenuIndex - 1 + maxMenuItems) % maxMenuItems;
      Serial.print("Menu up: ");
      Serial.println(currentMenuIndex);
      display_menu_item(currentMenuIndex);
      delay(300); // Debounce
    }
  }
  
  // Handle DOWN button for menu navigation
  if (digitalRead(DOWN_BTN) == LOW) {
    if (hasUserData) {
      currentMenuIndex = (currentMenuIndex + 1) % maxMenuItems;
      Serial.print("Menu down: ");
      Serial.println(currentMenuIndex);
      display_menu_item(currentMenuIndex);
      delay(300); // Debounce
    }
  }

  delay(100);
}

void setup_display() {
  // Initialize the OLED display
  if(!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println(F("SSD1306 allocation failed"));
    return;
  }
  
  // Flip the display vertically as requested
  display.setRotation(2); // Rotate 180 degrees
  
  // Clear the buffer
  display.clearDisplay();
  
  // Show initial display - loading screen
  display_loading_screen();
}

void display_loading_screen() {
  display.clearDisplay();
  
  // Set text size and color
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  
  // Center "EWatch" text
  int16_t x1, y1;
  uint16_t w, h;
  display.getTextBounds("EWatch", 0, 0, &x1, &y1, &w, &h);
  display.setCursor((SCREEN_WIDTH - w) / 2, (SCREEN_HEIGHT - h) / 2);
  
  // Display EWatch text
  display.println("EWatch");
  
  // Update display
  display.display();
}

void display_user_data() {
  if (!hasUserData) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println("No user data");
    display.display();
    return;
  }
  
  display_menu_item(currentMenuIndex);
}

void display_menu_item(int index) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  // Variable declarations before the switch statement
  bool hasDiseases = false;
  bool hasMeds = false;
  int i;
  
  // Display the page number in top-right corner
  display.setTextSize(1);
  char pageIndicator[4];
  sprintf(pageIndicator, "%d/%d", index + 1, maxMenuItems);
  int16_t x1, y1;
  uint16_t w, h;
  display.getTextBounds(pageIndicator, 0, 0, &x1, &y1, &w, &h);
  display.setCursor(SCREEN_WIDTH - w - 2, 0); // Position at top-right with small margin
  display.print(pageIndicator);
  
  // Draw a line separator
  display.drawLine(0, 10, SCREEN_WIDTH, 10, SSD1306_WHITE);
  switch(index) {
    case 0: // Page 1: Personal Info (Name, Surname, Age, Weight, Height)
      // Header
      display.setTextSize(1);
      display.setCursor(0, 0);
      display.println("Personal Info");
      
      // Content
      display.setCursor(0, 13);
      display.print("Name: ");
      display.println(userData.name);
      
      display.setCursor(0, 23);
      display.print("Surname: ");
      display.println(userData.surname);
      
      display.setCursor(0, 33);
      display.print("Age: ");
      display.print(userData.age);
      display.println(" years");
      
      display.setCursor(0, 43);
      display.print("Weight: ");
      display.print(userData.weight);
      display.println(" kg");
      
      display.setCursor(0, 53);
      display.print("Height: ");
      display.print(userData.height);
      display.println(" cm");
      break;
      
    case 1: // Page 2: Diseases
      // Header
      display.setTextSize(1);
      display.setCursor(0, 0);
      display.println("Diseases");
      
      // Content
      display.setCursor(0, 16);
      display.setTextSize(1);
      
      hasDiseases = false;
      for (i = 0; i < 3; i++) {
        if (userData.diseases[i].length() > 0) {
          hasDiseases = true;
          display.setCursor(0, 16 + (i * 15));
          display.print("- ");
          display.println(userData.diseases[i]);
        }
      }
      
      if (!hasDiseases) {
        display.setCursor(0, 30);
        display.println("No diseases listed");
      }
      break;
      
    case 2: // Page 3: Medications
      // Header
      display.setTextSize(1);
      display.setCursor(0, 0);
      display.println("Medications");
      
      // Content
      display.setCursor(0, 16);
      display.setTextSize(1);
      
      hasMeds = false;
      for (i = 0; i < 3; i++) {
        if (userData.medications[i].length() > 0) {
          hasMeds = true;
          display.setCursor(0, 16 + (i * 15));
          display.print("- ");
          display.println(userData.medications[i]);
        }
      }
      
      if (!hasMeds) {
        display.setCursor(0, 30);
        display.println("No medications listed");
      }
      break;
  }
  
  display.display();
}

void display_processing_screen() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  
  // Center "Processing" text
  int16_t x1, y1;
  uint16_t w, h;
  display.getTextBounds("Processing", 0, 0, &x1, &y1, &w, &h);
  display.setCursor((SCREEN_WIDTH - w) / 2, SCREEN_HEIGHT / 2 - h);
  display.println("Processing");
  
  // Center "image" text
  display.getTextBounds("image", 0, 0, &x1, &y1, &w, &h);
  display.setCursor((SCREEN_WIDTH - w) / 2, SCREEN_HEIGHT / 2 + 5);
  display.println("image");
  
  // Update display
  display.display();
}

void parse_user_data(String json) {
  // Allow for a pretty large JSON document (6KB) since we need to handle arrays
  DynamicJsonDocument doc(6144);
  DeserializationError error = deserializeJson(doc, json);
  
  if (error) {
    Serial.print("deserializeJson() failed: ");
    Serial.println(error.c_str());
    return;
  }
  
  // Parse the JSON data
  userData.name = doc["name"].as<String>();
  userData.surname = doc["surname"].as<String>();
  userData.age = doc["age"];
  userData.weight = doc["weight"];
  userData.height = doc["height"];
  
  // Parse disease array
  JsonArray diseases = doc["diseases"];
  int i = 0;
  for (JsonVariant disease : diseases) {
    if (i < 3) {
      userData.diseases[i] = disease.as<String>();
      i++;
    }
  }
  
  // Parse medications array
  JsonArray medications = doc["medications"];
  i = 0;
  for (JsonVariant medication : medications) {
    if (i < 3) {
      userData.medications[i] = medication.as<String>();
      i++;
    }
  }
  
  hasUserData = true;
  currentMenuIndex = 0; // Reset menu to the beginning
}
