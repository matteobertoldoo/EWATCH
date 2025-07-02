from kivy.config import Config

Config.set("kivy", "keyboard_mode", "system")
Config.set("kivy", "clipboard", "")  # Disabilita clipboard per Wayland

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import mainthread, Clock
from kivy.utils import platform
from kivy.logger import Logger
from settings_screen import SettingsScreen
from settings_screen import get_server_url
from camera_widget import CameraWidget
from ble_screen import BleScreen

# Configure Python logging to use Kivy's logger
import logging

logging.Logger.manager.root = Logger

import io
import threading
import requests
import os
import asyncio


class RecognizeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Titolo
        title = Label(
            text="Riconoscimento Paziente",
            size_hint_y=None,
            height="40dp",
            font_size="18sp",
        )
        layout.add_widget(title)

        # Camera widget
        self.camera_widget = CameraWidget(
            callback=self.on_photo_captured, size_hint_y=0.4
        )
        layout.add_widget(self.camera_widget)

        # Status e controlli
        self.status = Label(
            text="Scatta una foto per iniziare", size_hint_y=None, height="40dp"
        )
        layout.add_widget(self.status)

        btn_recognize = Button(
            text="Riconosci Paziente", size_hint_y=None, height="48dp"
        )
        btn_recognize.bind(on_press=self.recognize_patient)
        layout.add_widget(btn_recognize)

        self.dati = Label(text="", size_hint_y=None, height="120dp")
        layout.add_widget(self.dati)

        self.btn_data = Button(
            text="Richiedi Dati Paziente", size_hint_y=None, height="48dp"
        )
        self.btn_data.bind(on_press=self.request_data)
        self.btn_data.disabled = True
        layout.add_widget(self.btn_data)

        # Bottoni navigazione
        nav_layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height="48dp", spacing=10
        )

        btn_settings = Button(text="Impostazioni")
        btn_settings.bind(
            on_press=lambda x: setattr(self.manager, "current", "settings")
        )
        nav_layout.add_widget(btn_settings)

        # Add BLE button
        btn_ble = Button(text="Connessione BLE")
        btn_ble.bind(on_press=lambda x: setattr(self.manager, "current", "ble"))
        nav_layout.add_widget(btn_ble)

        layout.add_widget(nav_layout)

        self.add_widget(layout)
        self.photo_texture = None
        self.photo_bytes = None
        self.paziente_id = None

    def on_photo_captured(self, texture, photo_bytes):
        self.photo_texture = texture
        self.photo_bytes = photo_bytes
        self.status.text = "Foto catturata. Premere 'Riconosci Paziente'"

    def recognize_patient(self, instance):
        if not self.photo_bytes:
            self.status.text = "Scatta prima una foto!"
            return

        self.status.text = "Riconoscimento in corso..."
        threading.Thread(target=self.send_photo).start()

    @mainthread
    def update_status(self, text):
        self.status.text = text

    @mainthread
    def update_patient_data(self, data):
        self.dati.text = data
        self.btn_data.disabled = False
        self.paziente_id = data.split()[0] if data else None

    def send_photo(self):
        try:
            server_url = get_server_url()
            url = f"{server_url}/recognize"
            files = {"image": ("image.jpg", self.photo_bytes, "image/jpeg")}

            self.update_status("Invio foto al server...")
            response = requests.post(url, files=files, timeout=10)

            if response.status_code == 200:
                data = response.json()
                patient_id = data.get("patient_id")
                confidence = data.get("confidence", 0)

                if patient_id:
                    self.update_status(
                        f"Paziente riconosciuto (conf: {confidence:.2f})"
                    )
                    self.update_patient_data(f"{patient_id}")
                else:
                    self.update_status("Paziente non riconosciuto")
                    self.update_patient_data("")
            else:
                self.update_status(f"Errore: {response.status_code}")
                self.update_patient_data("")
        except Exception as e:
            self.update_status(f"Errore: {str(e)}")
            self.update_patient_data("")

    def request_data(self, instance):
        if not self.paziente_id:
            self.status.text = "Nessun paziente selezionato"
            return

        self.status.text = "Richiesta dati paziente..."
        threading.Thread(target=self.fetch_patient_data).start()

    def fetch_patient_data(self):
        try:
            server_url = get_server_url()
            url = f"{server_url}/patient/{self.paziente_id}"

            self.update_status("Richiesta dati paziente...")
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                name = data.get("name", "")
                surname = data.get("surname", "")
                birthdate = data.get("birthdate", "")
                gender = data.get("gender", "")
                diseases = ", ".join(data.get("diseases", []))
                medications = ", ".join(data.get("medications", []))

                patient_info = (
                    f"ID: {self.paziente_id}\n"
                    f"Nome: {name} {surname}\n"
                    f"Data di nascita: {birthdate}\n"
                    f"Genere: {gender}\n"
                    f"Patologie: {diseases}\n"
                    f"Farmaci: {medications}"
                )

                self.update_status("Dati paziente ricevuti")
                self.update_patient_data(patient_info)
            else:
                self.update_status(f"Errore: {response.status_code}")
        except Exception as e:
            self.update_status(f"Errore: {str(e)}")


class MyApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._async_tasks = []
        self.running = True

    def build(self):
        self.sm = ScreenManager()
        self.sm.add_widget(RecognizeScreen(name="recognize"))
        self.sm.add_widget(SettingsScreen(name="settings", back_target="recognize"))
        self.sm.add_widget(BleScreen(name="ble", back_target="recognize"))
        return self.sm

    def on_pause(self):
        """
        Chiamata quando l'app va in background (Android)
        Ritorna True per consentire la ripresa senza riavvio
        """
        Logger.info("App: on_pause called - app in background")
        return True

    def on_stop(self):
        """Cleanup async tasks when the app stops"""
        self.running = False
        for task in self._async_tasks:
            if not task.done():
                task.cancel()

    def create_async_task(self, coro):
        """Create and track an async task"""
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(coro)
            self._async_tasks.append(task)
            return task
        except Exception as e:
            Logger.error(f"Error creating async task: {e}")
            return None

    # This method allows Kivy to use asyncio event loop
    async def async_run(self, async_lib="asyncio"):
        """Run the application with asyncio support"""
        # Configure Kivy to use asyncio
        if hasattr(Clock, "_async_lib"):
            Clock._async_lib = async_lib
        else:
            # Fallback for older Kivy versions
            Clock.start_async_loop = lambda *args: None

        # Start the Kivy application
        self.run()

    # Method to handle background BLE tasks if needed
    async def ble_manager(self):
        """Background task to manage BLE operations"""
        # This runs in the background and can manage BLE operations
        while self.running:
            # Don't do anything for now, just keep the loop alive
            await asyncio.sleep(1)


# New main async function to coordinate Kivy and asyncio
async def main(app):
    """Main entry point coordinating Kivy and asyncio"""
    # Run both the Kivy app and our background manager
    await asyncio.gather(app.async_run(), app.ble_manager())


# Needed to improve Android permissions handling
if platform == "android":
    from android.permissions import request_permissions, Permission

    # Request necessary permissions for BLE on Android
    permissions = [
        Permission.BLUETOOTH,
        Permission.BLUETOOTH_ADMIN,
        Permission.BLUETOOTH_SCAN,
        Permission.BLUETOOTH_CONNECT,
        Permission.BLUETOOTH_ADVERTISE,
        Permission.ACCESS_FINE_LOCATION,
        Permission.ACCESS_COARSE_LOCATION,
    ]

    try:
        request_permissions(permissions)
    except Exception as e:
        Logger.error(f"Error requesting permissions: {e}")

if __name__ == "__main__":
    # Set logging level
    Logger.setLevel(logging.DEBUG)

    # Create and run app using the asyncio pattern
    app = MyApp()
    asyncio.run(main(app))
