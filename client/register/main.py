from kivy.config import Config

Config.set("kivy", "keyboard_mode", "system")

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.clock import mainthread, Clock
from kivy.utils import platform
from settings_screen import SettingsScreen
from settings_screen import get_server_url
from camera_widget import CameraWidget
from kivy.core.window import Window

import io, threading, requests

# Window.softinput_mode = "pan"  # Options: '', 'pan', 'scale', 'resize'


class RegisterScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Main layout
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Titolo
        title = Label(
            text="Patient Registration",
            size_hint_y=None,
            height="40dp",
            font_size="18sp",
        )
        main_layout.add_widget(title)

        # Camera widget
        self.camera_widget = CameraWidget(
            callback=self.on_photo_captured, size_hint_y=0.4
        )
        main_layout.add_widget(self.camera_widget)

        # Scroll view for input fields
        # scroll_view = ScrollView(size_hint=(1, 0.4))
        form_layout = BoxLayout(orientation="vertical", spacing=5, size_hint_y=None)
        form_layout.bind(minimum_height=form_layout.setter("height"))

        # Create row layouts for side-by-side fields
        row1 = BoxLayout(size_hint_y=None, height="40dp", spacing=5)
        row2 = BoxLayout(size_hint_y=None, height="40dp", spacing=5)
        row3 = BoxLayout(size_hint_y=None, height="40dp", spacing=5)
        # row4 = BoxLayout(size_hint_y=None, height="40dp", spacing=5)
        # row5 = BoxLayout(size_hint_y=None, height="40dp", spacing=5)

        # Input fields
        self.nome = TextInput(hint_text="Name*", multiline=False, size_hint_x=0.5)
        self.surname = TextInput(hint_text="Surname", multiline=False, size_hint_x=0.5)

        self.age = TextInput(
            hint_text="Age", multiline=False, input_filter="int", size_hint_x=0.25
        )
        self.weight = TextInput(
            hint_text="Weight (kg)",
            multiline=False,
            input_filter="float",
            size_hint_x=0.25,
        )
        self.height_input = TextInput(
            hint_text="Height (cm)",
            multiline=False,
            input_filter="float",
            size_hint_x=0.25,
        )

        self.gruppo = TextInput(
            hint_text="Blood Type", multiline=False, size_hint_x=0.25
        )

        self.allergie = TextInput(
            hint_text="Allergies", multiline=False, size_hint_x=1.0
        )

        self.diseases = TextInput(
            hint_text="Diseases (separated by comma)", multiline=False, size_hint_x=0.5
        )
        self.medications = TextInput(
            hint_text="Medications (separated by comma)",
            multiline=False,
            size_hint_x=0.5,
        )

        # Add fields to row layouts
        row1.add_widget(self.nome)
        row1.add_widget(self.surname)

        row2.add_widget(self.age)
        row2.add_widget(self.weight)
        row2.add_widget(self.height_input)

        row2.add_widget(self.gruppo)

        # row4.add_widget(self.allergie)

        row3.add_widget(self.diseases)
        row3.add_widget(self.medications)

        # Add rows to form layout
        form_layout.add_widget(row1)
        form_layout.add_widget(row2)
        form_layout.add_widget(row3)
        # form_layout.add_widget(row4)
        # form_layout.add_widget(row5)

        # Add form to scroll view
        # scroll_view.add_widget(form_layout)
        main_layout.add_widget(form_layout)

        # Status e bottoni
        self.status = Label(
            text="Take a photo to begin", size_hint_y=None, height="40dp"
        )
        main_layout.add_widget(self.status)

        # Bottoni principali
        btn_layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height="48dp", spacing=10
        )

        btn_send = Button(text="Register Patient")
        btn_send.bind(on_press=self.send_data)
        btn_layout.add_widget(btn_send)

        btn_clear = Button(text="Clear Fields")
        btn_clear.bind(on_press=self.clear_fields)
        btn_layout.add_widget(btn_clear)

        # Add the button layout to main layout (this was missing)
        main_layout.add_widget(btn_layout)

        # Bottone navigazione
        btn_settings = Button(text="Server Settings", size_hint_y=None, height="48dp")
        btn_settings.bind(
            on_press=lambda x: setattr(self.manager, "current", "settings")
        )
        main_layout.add_widget(btn_settings)

        self.add_widget(main_layout)
        self.photo_texture = None
        self.photo_bytes = None  # Cache per i bytes della foto

    def on_photo_captured(self, texture, photo_bytes):
        """Callback chiamato quando una foto è catturata"""
        self.photo_texture = texture
        self.photo_bytes = photo_bytes
        self.status.text = "Photo captured! Enter data and register."

    def clear_fields(self, instance):
        """Pulisce tutti i campi di input"""
        self.nome.text = ""
        self.surname.text = ""
        self.age.text = ""
        self.weight.text = ""
        self.height_input.text = ""  # Updated to height_input
        self.gruppo.text = ""
        self.allergie.text = ""
        self.diseases.text = ""
        self.medications.text = ""
        self.status.text = "Fields cleared. Take a new photo if needed."

    def send_data(self, instance):
        if not self.photo_bytes:
            self.status.text = "Take a photo first"
            return

        if not self.nome.text.strip():
            self.status.text = "Enter at least the name"
            return

        # Parse diseases and medications into lists
        diseases_list = [d.strip() for d in self.diseases.text.split(",") if d.strip()]
        medications_list = [
            m.strip() for m in self.medications.text.split(",") if m.strip()
        ]

        # Build payload
        payload = {
            "nome": self.nome.text.strip(),
            "surname": self.surname.text.strip(),
            "age": self.age.text.strip() or "0",
            "weight": self.weight.text.strip() or "0",
            "height": self.height_input.text.strip() or "0",  # Updated
            "gruppo": self.gruppo.text.strip(),
            "allergie": self.allergie.text.strip(),
        }

        # Add diseases and medications as lists
        for disease in diseases_list:
            payload["diseases[]"] = diseases_list

        for medication in medications_list:
            payload["medications[]"] = medications_list

        self.status.text = "Sending data to server..."
        threading.Thread(target=self._post_register, args=(payload,)).start()

    def _post_register(self, payload):
        try:
            server_url = get_server_url()
            files = {"foto": ("foto.jpg", io.BytesIO(self.photo_bytes), "image/jpeg")}
            r = requests.post(
                f"{server_url}/register", data=payload, files=files, timeout=30
            )

            if r.status_code == 200:
                resp = r.json()
                self._show_result(f"✓ Successfully registered! ID: {resp.get('id')}")
                self._clear_form()
            else:
                self._show_result(f"✗ Server error: {r.text}")
        except requests.exceptions.ConnectTimeout:
            self._show_result("✗ Server connection timeout")
        except requests.exceptions.ConnectionError:
            self._show_result("✗ Unable to connect to server")
        except Exception as e:
            self._show_result(f"✗ Errore: {str(e)}")

    @mainthread
    def _show_result(self, msg):
        self.status.text = msg

    @mainthread
    def _clear_form(self):
        """Pulisce il form dopo una registrazione riuscita"""
        Clock.schedule_once(lambda dt: self.clear_fields(None), 2.0)
        # Reset anche la foto
        self.photo_texture = None
        self.photo_bytes = None

    def on_enter(self):
        """Riattiva la camera quando si entra nella schermata"""
        # Set soft input mode only for this screen
        Window.softinput_mode = "pan"

        if hasattr(self, "camera_widget") and self.camera_widget:
            self.camera_widget.restart_camera()

    def on_leave(self):
        """Ferma la camera quando si esce dalla schermata"""
        # Reset soft input mode when leaving this screen
        Window.softinput_mode = ""

        if hasattr(self, "camera_widget") and self.camera_widget:
            self.camera_widget.stop_camera()


class MyApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(RegisterScreen(name="register"))
        sm.add_widget(SettingsScreen(name="settings", back_target="register"))
        return sm


if __name__ == "__main__":
    MyApp().run()
