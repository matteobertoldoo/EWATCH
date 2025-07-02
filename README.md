# Medical ICT System - Complete Healthcare Solution

A comprehensive medical information system consisting of client applications, server backend, and IoT device for patient identification and medical data management.

## 🏥 Overview

This repository contains a complete medical ICT system designed for healthcare facilities. The system includes mobile applications for patient registration and recognition, a Flask server backend with facial recognition capabilities, and an IoT wearable device (e-watch) for storing and displaying patient medical information.

## 📱 System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Registration  │    │                  │    │   Recognition   │
│      App        │◄──►│   Flask Server   │◄──►│      App        │
│   (Android)     │    │   + Face API     │    │   (Android)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                │                        │ BLE
                                │                        ▼
                       ┌────────▼────────┐    ┌─────────────────┐
                       │   Database      │    │    E-Watch      │
                       │   (Patient      │    │   IoT Device    │
                       │    Records)     │    │   (ESP32-S3)    │
                       └─────────────────┘    └─────────────────┘
```

## 🛠️ Components

### 1. Server Backend (`server/`)
Flask-based server providing REST API endpoints for patient management and facial recognition.

**Features:**
- Patient registration and data storage
- Facial recognition using face_recognition library
- Image processing and comparison
- JSON-based patient data management
- CORS-enabled API endpoints
- Secure file handling

**Key Files:**
- `app.py` - Main Flask application
- `requirements.txt` - Python dependencies
- Patient data stored in JSON format

**API Endpoints:**
```
POST /register    - Register new patient with photo
POST /recognize   - Identify patient by photo
POST /dati       - Retrieve patient data by ID
```

### 2. Patient Registration App (`client/mykivyapp/`)
Mobile application built with Kivy for registering new patients into the medical system.

**Features:**
- Patient photo capture with camera rotation
- Comprehensive patient information form (name, blood type, allergies, etc.)
- Real-time server communication
- Cross-platform Android compatibility
- Settings configuration for server connection

**Key Files:**
- `main.py` - Main registration application
- `camera_widget.py` - Camera functionality with rotation
- `settings_screen.py` - Server configuration
- `buildozer.spec` - Android build configuration

### 3. Patient Recognition App (`client/recognize/`)
Mobile application for identifying patients through facial recognition and managing e-watch communication.

**Features:**
- Patient photo capture and recognition
- Integration with facial recognition server
- Bluetooth Low Energy (BLE) connectivity to e-watch device
- Patient data retrieval and display
- Real-time image processing and rotation

**Key Files:**
- `main.py` - Main recognition application
- `ble_screen.py` - BLE connection management
- `camera_widget.py` - Camera functionality
- `settings_screen.py` - Configuration settings

### 4. E-Watch IoT Device (`e-watch/`)
ESP32-based wearable device with camera, OLED display, and BLE connectivity.

**Features:**
- ESP32-S3 XIAO microcontroller with camera
- 128x64 OLED display for information display
- Bluetooth Low Energy server
- Patient data storage and display
- Menu system with navigation buttons
- Image capture and transmission capabilities

**Key Files:**
- `ewatch.ino` - Main Arduino firmware
- `camera_pins.h` - Camera pin definitions

### 5. Development/Testing (`prova/`)
Development scripts for BLE communication testing and system integration.

**Features:**
- BLE client implementation with chunked image transfer
- Mock data generation for testing
- Image processing and rotation utilities
- Communication protocol testing

## 🛠️ Technical Stack

### Server Backend
- **Framework:** Flask (Python)
- **Face Recognition:** face_recognition library
- **Image Processing:** OpenCV, PIL
- **Data Storage:** JSON files
- **Dependencies:** numpy, flask-cors

### Mobile Applications
- **Framework:** Kivy (Python)
- **Build System:** Buildozer
- **Platform:** Android (API 21-35)
- **Dependencies:** 
  - Python 3
  - Kivy
  - Requests (HTTP communication)
  - Bleak (BLE communication)

### IoT Device
- **Hardware:** ESP32-S3 XIAO
- **Framework:** Arduino IDE/PlatformIO
- **Libraries:**
  - BLEDevice (Bluetooth Low Energy)
  - Adafruit_SSD1306 (OLED display)
  - esp_camera (Camera functionality)
  - ArduinoJson (JSON data handling)

## 🔧 Setup and Installation

### Server Setup

1. **Install Dependencies:**
   ```bash
   cd server/
   pip install -r requirements.txt
   ```

2. **Install System Dependencies (Ubuntu/Debian):**
   ```bash
   sudo apt update
   sudo apt install cmake libopenblas-dev liblapack-dev libx11-dev libgtk-3-dev
   ```

3. **Run Server:**
   ```bash
   python app.py
   ```
   Server will start on `http://localhost:5000`

### Mobile Applications

1. **Prerequisites:**
   ```bash
   pip install kivy buildozer
   ```

2. **Configure Server Settings:**
   Edit server IP/port in the settings screen of each app

3. **Build Android APK:**
   ```bash
   cd client/mykivyapp/  # for registration app
   # or
   cd client/recognize/  # for recognition app
   
   buildozer android debug
   ```

4. **Install APK:**
   - Transfer generated APK from `bin/` folder to Android device
   - Enable "Unknown sources" in Android settings
   - Install the APK

### E-Watch Device

1. **Hardware Setup:**
   - ESP32-S3 XIAO development board
   - Compatible camera module (OV2640)
   - 128x64 OLED display (I2C, address 0x3C)
   - Navigation buttons (UP, DOWN, CONFIRM)
   - LED indicator

2. **Software Setup:**
   - Install Arduino IDE or PlatformIO
   - Install required libraries:
     - ESP32 board package
     - Adafruit SSD1306
     - ArduinoJson
     - ESP32 BLE Arduino
   - Upload `ewatch.ino` to the device

## 📡 Communication Protocols

### HTTP REST API (Client ↔ Server)
```json
Registration Request:
POST /register
Content-Type: multipart/form-data
{
  "nome": "string",
  "gruppo": "string", 
  "allergie": "string",
  "foto": "image_file"
}

Recognition Request:
POST /recognize  
Content-Type: multipart/form-data
{
  "foto": "image_file"
}

Data Request:
POST /dati
Content-Type: application/x-www-form-urlencoded
{
  "id": "patient_id"
}
```

### BLE Protocol (App ↔ E-Watch)
- **Service UUID:** `4fafc201-1fb5-459e-8fcc-c5c9c331914b`
- **Image Characteristic:** `beb5483e-36e1-4688-b7f5-ea07361b26a8` (Image data transfer)
- **Data Characteristic:** `80dcca86-d593-484b-8b13-72db9d98faea` (Patient data)
- **Control Characteristic:** `a9da86e1-4456-4bea-b82d-b7a8e834bb0a` (Control commands)

## 🚀 Usage Instructions

### Complete Workflow

1. **Start the Server:**
   ```bash
   cd server/
   python app.py
   ```

2. **Register a New Patient:**
   - Launch Medical Registration app
   - Configure server settings (IP/port)
   - Capture patient photo
   - Fill patient information form
   - Submit registration

3. **Patient Recognition:**
   - Launch Medical Recognition app
   - Connect to e-watch device via BLE
   - Capture photo of patient
   - System identifies patient via server
   - Patient data sent to e-watch
   - View information on e-watch display

4. **E-Watch Operation:**
   - Power on device
   - Navigate menu with UP/DOWN buttons
   - Confirm selections with CONFIRM button
   - View patient data on OLED display

## 🔒 Security and Privacy

- Patient images processed using industry-standard face recognition
- BLE communication with encrypted connections
- Server-side data validation and sanitization
- Local image processing when possible
- Secure file handling and storage

## 📋 Configuration

### Server Configuration
Default server runs on `localhost:5000`. Modify `app.py` for different settings.

### Client Configuration
Configure server connection in each app's settings screen:
```json
{
  "server": {
    "ip": "192.168.1.100",
    "port": "5000"
  }
}
```

### Android Permissions
Automatically configured permissions:
- `CAMERA` - Photo capture
- `BLUETOOTH` / `BLUETOOTH_ADMIN` - BLE communication
- `ACCESS_FINE_LOCATION` - BLE device discovery
- `INTERNET` - Server communication
- `WRITE_EXTERNAL_STORAGE` - Image processing

## 🧪 Development and Testing

### Testing BLE Communication
```bash
cd prova/
python ble_client.py
```

### Server Testing
```bash
cd server/
# Test registration endpoint
curl -X POST -F "nome=Test" -F "foto=@test_image.jpg" http://localhost:5000/register

# Test recognition endpoint  
curl -X POST -F "foto=@test_image.jpg" http://localhost:5000/recognize
```

### Camera Testing
Both mobile apps include camera rotation and image processing for optimal results.

## 📁 Project Structure

```
ICT/
├── server/                 # Flask backend server
│   ├── app.py             # Main server application
│   ├── requirements.txt   # Python dependencies
│   └── uploads/           # Patient photos storage
├── client/
│   ├── mykivyapp/         # Registration mobile app
│   └── recognize/         # Recognition mobile app
├── e-watch/               # ESP32 IoT device firmware
├── prova/                 # Development and testing scripts
└── README.md             # This file
```

## 🔧 Dependencies

### Server Requirements
```
Flask>=2.0.0
face-recognition>=1.3.0
opencv-python>=4.5.0
Pillow>=8.0.0
numpy>=1.21.0
flask-cors>=3.0.0
```

### Mobile App Requirements
```
kivy>=2.1.0
buildozer>=1.4.0
requests>=2.25.0
bleak>=0.19.0  # BLE support
```

## 📄 License

This project is developed as part of an academic ICT project at University of Trento.

## 🤝 Contributing

This is an academic project. For contributions or questions, please contact the development team.

---

**⚠️ Important Notice:** This system is designed for educational and research purposes. It should undergo proper medical device certification and security auditing before use in real healthcare environments.
