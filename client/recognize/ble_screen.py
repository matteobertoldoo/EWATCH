import asyncio
import json
from datetime import datetime
import io
import os
import threading

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.clock import Clock, mainthread
from kivy.utils import platform
from kivy.logger import Logger
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image
from kivy.app import App  # Add this import

from bleak import BleakClient, BleakScanner

# UUIDs matching those in the Arduino code
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
IMAGE_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
DATA_UUID = "80dcca86-d593-484b-8b13-72db9d98faea"
CONTROL_UUID = "a9da86e1-4456-4bea-b82d-b7a8e834bb0a"


class BleScreen(Screen):
    def __init__(self, back_target, **kwargs):
        super().__init__(**kwargs)
        self.back_target = back_target
        self.ble_task = None
        self.client = None
        self.running = True

        # Image transfer state
        self.image_buffer = bytearray()
        self.image_size = 0
        self.total_chunks = 0
        self.received_chunks = 0
        self.transfer_active = False
        self.image_metadata_received = False
        self.chunks_received = set()

        # UI layout
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Title
        title = Label(
            text="Connessione BLE",
            size_hint_y=None,
            height="40dp",
            font_size="18sp",
        )
        layout.add_widget(title)

        # Log area
        self.scroll_view = ScrollView(do_scroll_x=False, size_hint_y=0.7)
        self.log_label = Label(
            text="Ready to scan...\n", size_hint_y=None, text_size=(None, None)
        )
        self.log_label.bind(
            width=lambda *x: setattr(
                self.log_label, "text_size", (self.log_label.width, None)
            )
        )
        self.log_label.bind(
            texture_size=lambda *x: setattr(
                self.log_label, "height", self.log_label.texture_size[1]
            )
        )
        self.scroll_view.add_widget(self.log_label)
        layout.add_widget(self.scroll_view)

        # Controls
        btn_layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height="48dp", spacing=10
        )

        self.scan_btn = Button(text="Scan for devices")
        self.scan_btn.bind(on_press=self.start_ble_scan)
        btn_layout.add_widget(self.scan_btn)

        self.cancel_btn = Button(text="Cancel/Disconnect")
        self.cancel_btn.bind(on_press=self.cancel_operation)
        btn_layout.add_widget(self.cancel_btn)

        layout.add_widget(btn_layout)

        # Back button
        back_btn = Button(
            text=f"Go back to {back_target}", size_hint_y=None, height="48dp"
        )
        back_btn.bind(on_press=lambda x: setattr(self.manager, "current", back_target))
        layout.add_widget(back_btn)

        self.add_widget(layout)

    def log(self, text):
        """Add text to the log area"""
        Logger.info(f"BLE: {text}")
        self.log_label.text += f"{text}\n"
        # Scroll to the bottom
        Clock.schedule_once(lambda dt: setattr(self.scroll_view, "scroll_y", 0), 0.1)

    @mainthread
    def update_log(self, text):
        """Thread-safe way to update the log"""
        self.log(text)

    def on_enter(self):
        """Called when entering the screen"""
        self.running = True

    def on_leave(self):
        """Called when leaving the screen"""
        self.cancel_operation()

    def start_ble_scan(self, instance):
        """Start the BLE scanning process"""
        self.log("Starting BLE scan...")
        self.scan_btn.disabled = True

        if platform == "android":
            # Request permissions on Android
            from android.permissions import (
                request_permissions,
                Permission,
                check_permission,
            )

            # Check and request all needed permissions
            permissions_to_check = [
                Permission.BLUETOOTH_SCAN,
                Permission.BLUETOOTH_CONNECT,
                Permission.BLUETOOTH_ADVERTISE,
                Permission.ACCESS_FINE_LOCATION,
            ]

            missing_permissions = []
            for permission in permissions_to_check:
                if not check_permission(permission):
                    missing_permissions.append(permission)

            if missing_permissions:
                self.log(f"Requesting permissions: {missing_permissions}")
                request_permissions(missing_permissions)
                # Add a small delay to ensure permissions are processed
                Clock.schedule_once(lambda dt: self._start_ble_scan_task(), 1)
                return

        # If not on Android or all permissions granted, proceed directly
        self._start_ble_scan_task()

    def _start_ble_scan_task(self):
        """Helper method to start the actual BLE scan after permissions check"""
        self.log("Initiating BLE scan...")

        # Use a simpler approach with Clock.schedule_once to ensure we're on the main thread
        def start_scan_wrapper(dt):
            try:
                # Create the task directly with proper error handling
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    self.log("Event loop is not running - this is a problem")
                    self.scan_btn.disabled = False
                    return

                # Add a direct call to show we're about to start
                self.log("Creating asyncio task now...")

                # Run a simple test coroutine first to check if asyncio is working
                async def test_coro():
                    self.log("Test coroutine running")
                    await asyncio.sleep(0.1)
                    self.log("Test coroutine completed")

                    # Now start the actual scan task
                    self.ble_task = asyncio.create_task(self.ble_scan())
                    self.log("BLE scan task scheduled")

                # Create and schedule the test task
                asyncio.create_task(test_coro())

            except Exception as e:
                self.log(f"Error in scan task wrapper: {e}")
                self.scan_btn.disabled = False

        # Use Clock to ensure we're on the main thread when starting the task
        Clock.schedule_once(start_scan_wrapper, 0)

    async def ble_scan(self):
        """Main BLE scanning and connection function"""
        try:
            # Add multiple logging statements to see how far it gets
            self.update_log("BLE scan coroutine started")
            self.update_log("Current thread: " + threading.current_thread().name)

            # Testing simple asyncio operations first
            self.update_log("Testing asyncio.sleep...")
            await asyncio.sleep(0.1)
            self.update_log("asyncio.sleep completed")

            # Now proceed with actual BLE scanning
            self.update_log("Starting BleakScanner...")

            self.update_log("Scanning for BLE devices...")

            # Scan for devices with detailed exception handling
            try:
                scanner = BleakScanner()
                self.update_log("Scanner created")
                devices = await scanner.discover(
                    timeout=5.0
                )  # Shorter timeout for testing
                self.update_log(f"Scan complete, found {len(devices)} devices")
            except Exception as scan_error:
                self.update_log(f"Scan error: {str(scan_error)}")
                if platform == "android":
                    self.update_log(
                        "Android scan errors may indicate permission issues"
                    )
                self.scan_btn.disabled = False
                return

            # Filter for EWatch devices
            ewatch_devices = []
            for device in devices:
                device_name = device.name or "Unknown"
                self.update_log(f"Found: {device_name} ({device.address})")
                if device_name and "EWatch" in device_name:
                    ewatch_devices.append(device)

            if not ewatch_devices:
                self.update_log("No EWatch devices found. Please try again.")
                self.scan_btn.disabled = False
                return

            # Connect to the first EWatch device
            device = ewatch_devices[0]
            self.update_log(f"Connecting to {device.name}...")

            async with BleakClient(device) as client:
                self.client = client
                self.update_log(f"Connected to {device.name}")

                # Subscribe to notifications
                await client.start_notify(IMAGE_UUID, self.notification_handler)
                await client.start_notify(DATA_UUID, self.notification_handler)

                self.update_log("Press the button on your EWatch to take a picture")

                # Stay connected until user navigates away or cancels
                while self.running:
                    await asyncio.sleep(0.1)

                # Clean up on exit
                await client.stop_notify(IMAGE_UUID)
                await client.stop_notify(DATA_UUID)
                self.client = None

        except Exception as e:
            self.update_log(f"Error: {str(e)}")
        finally:
            self.scan_btn.disabled = False

    def cancel_operation(self, instance=None):
        """Cancel the current operation and disconnect"""
        self.running = False
        if self.client and self.client.is_connected:
            self.update_log("Disconnecting...")
            # Send cancel command if transfer is active
            if self.transfer_active:
                asyncio.create_task(self.send_cancel_command())
        if self.ble_task:
            self.ble_task.cancel()
            self.ble_task = None
        self.scan_btn.disabled = False

    async def send_cancel_command(self):
        """Send cancel command to device"""
        if self.client and self.client.is_connected:
            try:
                await self.client.write_gatt_char(CONTROL_UUID, b"CANCEL")
            except Exception as e:
                self.update_log(f"Error sending cancel: {str(e)}")

    async def notification_handler(self, sender, data):
        """Handle incoming notifications from the device"""
        # Check if this is the data characteristic
        if str(sender.uuid) == DATA_UUID:
            try:
                message = data.decode("utf-8")
                self.update_log(f"Received: {message}")

                if message == "IMAGE_READY":
                    self.update_log("Image ready for transfer, sending READY...")
                    self.reset_transfer_state()
                    self.transfer_active = True
                    await self.client.write_gatt_char(CONTROL_UUID, b"READY")

                elif message == "DONE":
                    self.update_log("Transfer completed!")
                    if self.received_chunks == self.total_chunks:
                        self.save_and_process_image()
                    self.transfer_active = False

                elif "," in message:  # Metadata
                    try:
                        size_str, chunks_str = message.split(",")
                        self.image_size = int(size_str)
                        self.total_chunks = int(chunks_str)
                        self.image_metadata_received = True
                        self.update_log(
                            f"Image metadata: {self.image_size} bytes, {self.total_chunks} chunks"
                        )

                        # Resize buffer
                        self.image_buffer = bytearray(self.image_size)

                        # Start requesting chunks
                        await self.request_next_chunk()
                    except Exception as e:
                        self.update_log(f"Error parsing metadata: {str(e)}")
            except UnicodeDecodeError:
                self.update_log("Received binary data on DATA characteristic")

        # Check if this is the image characteristic
        elif str(sender.uuid) == IMAGE_UUID:
            if not self.transfer_active or not self.image_metadata_received:
                return

            try:
                # Parse chunk header and data
                header_end = -1
                for i in range(min(10, len(data))):
                    if data[i] == ord(":"):
                        header_end = i
                        break

                if header_end >= 0:
                    chunk_idx = int(data[:header_end].decode("utf-8"))
                    chunk_data = data[header_end + 1 :]
                else:
                    chunk_data = data
                    chunk_idx = self.received_chunks

                # Calculate position in buffer
                chunk_size = 512
                offset = chunk_idx * chunk_size

                # Copy data to buffer
                data_len = len(chunk_data)
                if offset + data_len <= len(self.image_buffer):
                    self.image_buffer[offset : offset + data_len] = chunk_data
                else:
                    self.update_log(
                        f"Chunk exceeds buffer: offset={offset}, len={data_len}"
                    )

                # Mark chunk as received
                self.chunks_received.add(chunk_idx)
                self.received_chunks = len(self.chunks_received)

                self.update_log(
                    f"Chunk {chunk_idx+1}/{self.total_chunks} ({data_len} bytes)"
                )

                # Request next chunk
                await self.request_next_chunk()
            except Exception as e:
                self.update_log(f"Error processing chunk: {str(e)}")
                await self.request_next_chunk()

    def reset_transfer_state(self):
        """Reset all state variables for a new transfer"""
        self.image_buffer = bytearray()
        self.image_size = 0
        self.total_chunks = 0
        self.received_chunks = 0
        self.transfer_active = False
        self.image_metadata_received = False
        self.chunks_received = set()

    async def request_next_chunk(self):
        """Request the next chunk of the image"""
        if not self.transfer_active or self.received_chunks >= self.total_chunks:
            return

        # Find first missing chunk
        for i in range(self.total_chunks):
            if i not in self.chunks_received:
                await self.client.write_gatt_char(
                    CONTROL_UUID, f"GET:{i}".encode("utf-8")
                )
                return

    def save_and_process_image(self):
        """Save and process the received image using Kivy's Image module"""
        try:
            # Create a stream from the image buffer
            data = io.BytesIO(self.image_buffer)

            # Generate a timestamp for the filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"image_{timestamp}.jpg"

            # Save the raw bytes directly to a file first
            # (Kivy doesn't handle image rotation well for in-memory buffers)
            with open(filename, "wb") as f:
                f.write(self.image_buffer)
            self.update_log(f"Raw image saved as {filename}")

            # Inform user about image availability
            self.update_log("Image processing completed")

            # Send mock user data back to device
            asyncio.create_task(self.send_user_data())

        except Exception as e:
            self.update_log(f"Error processing image: {str(e)}")

            # Fallback: save original data if there was an error
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"image_original_{timestamp}.jpg"
                with open(filename, "wb") as f:
                    f.write(self.image_buffer)
                self.update_log(f"Original image saved as {filename}")
            except Exception as fallback_error:
                self.update_log(f"Error saving original image: {str(fallback_error)}")

    async def send_user_data(self):
        """Send mock user data to the device"""
        if not self.client:
            return

        try:
            # Generate mock data
            mock_data = {
                "name": "John",
                "surname": "Doe",
                "age": 45,
                "weight": 75.5,
                "height": 180.0,
                "diseases": ["Hypertension", "Type 2 Diabetes"],
                "medications": ["Metformin", "Lisinopril", "Aspirin"],
            }

            json_data = json.dumps(mock_data)
            self.update_log(f"Sending user data...")

            await self.client.write_gatt_char(DATA_UUID, json_data.encode("utf-8"))
            self.update_log("User data sent successfully")
        except Exception as e:
            self.update_log(f"Error sending user data: {str(e)}")
