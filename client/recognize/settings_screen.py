from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import mainthread
from kivy.storage.jsonstore import JsonStore

import threading, requests

# Configurazione di default
DEFAULT_SERVER_IP = "192.168.25.45"
DEFAULT_SERVER_PORT = "5000"

# Store per salvare le impostazioni
store = JsonStore("settings.json")


def get_server_url():
    """Ottiene l'URL del server dalle impostazioni salvate"""
    if store.exists("server"):
        ip = store.get("server")["ip"]
        port = store.get("server")["port"]
    else:
        ip = DEFAULT_SERVER_IP
        port = DEFAULT_SERVER_PORT
    return f"http://{ip}:{port}"


def get_app_storage_path():
    """Ottiene il percorso di storage interno dell'app"""
    if platform == "android":
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        context = PythonActivity.mActivity
        file_path = context.getExternalFilesDir(None).getAbsolutePath()
        return file_path
    else:
        return os.getcwd()


class SettingsScreen(Screen):
    def __init__(self, back_target, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical", padding=20, spacing=10)

        # Titolo
        title = Label(
            text="Impostazioni Server",
            size_hint_y=None,
            height="48dp",
            font_size="20sp",
        )
        layout.add_widget(title)

        # IP Server
        ip_label = Label(text="Indirizzo IP Server:", size_hint_y=None, height="40dp")
        layout.add_widget(ip_label)

        self.ip_input = TextInput(multiline=False, size_hint_y=None, height="40dp")
        layout.add_widget(self.ip_input)

        # Porta Server
        port_label = Label(text="Porta Server:", size_hint_y=None, height="40dp")
        layout.add_widget(port_label)

        self.port_input = TextInput(multiline=False, size_hint_y=None, height="40dp")
        layout.add_widget(self.port_input)

        # URL corrente
        self.current_url_label = Label(text="", size_hint_y=None, height="40dp")
        layout.add_widget(self.current_url_label)

        # Bottoni
        btn_layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height="48dp", spacing=10
        )

        btn_save = Button(text="Salva")
        btn_save.bind(on_press=self.save_settings)
        btn_layout.add_widget(btn_save)

        btn_test = Button(text="Test Connessione")
        btn_test.bind(on_press=self.test_connection)
        btn_layout.add_widget(btn_test)

        btn_reset = Button(text="Reset Default")
        btn_reset.bind(on_press=self.reset_to_default)
        btn_layout.add_widget(btn_reset)

        layout.add_widget(btn_layout)

        # Status
        self.status_label = Label(text="", size_hint_y=None, height="40dp")
        layout.add_widget(self.status_label)

        # Spacer
        layout.add_widget(Label())

        # Bottone navigazione
        btn_register = Button(
            text=f"Go back to {back_target}", size_hint_y=None, height="48dp"
        )
        btn_register.bind(
            on_press=lambda x: setattr(self.manager, "current", back_target)
        )
        layout.add_widget(btn_register)

        self.add_widget(layout)

    def on_enter(self):
        """Carica le impostazioni quando si entra nella schermata"""
        self.load_settings()

    def load_settings(self):
        """Carica le impostazioni salvate"""
        if store.exists("server"):
            settings = store.get("server")
            self.ip_input.text = settings["ip"]
            self.port_input.text = settings["port"]
        else:
            self.ip_input.text = DEFAULT_SERVER_IP
            self.port_input.text = DEFAULT_SERVER_PORT

        self.update_current_url()

    def save_settings(self, instance):
        """Salva le impostazioni"""
        ip = self.ip_input.text.strip()
        port = self.port_input.text.strip()

        if not ip:
            self.status_label.text = "Inserire un IP valido"
            return

        if not port:
            port = DEFAULT_SERVER_PORT

        try:
            int(port)
        except ValueError:
            self.status_label.text = "Porta non valida"
            return

        store.put("server", ip=ip, port=port)
        self.status_label.text = "Impostazioni salvate!"
        self.update_current_url()

    def test_connection(self, instance):
        """Testa la connessione al server"""
        ip = self.ip_input.text.strip()
        port = self.port_input.text.strip() or DEFAULT_SERVER_PORT

        if not ip:
            self.status_label.text = "Inserire un IP per testare"
            return

        test_url = f"http://{ip}:{port}"
        self.status_label.text = "Testing connessione..."

        threading.Thread(target=self._test_connection, args=(test_url,)).start()

    def _test_connection(self, url):
        """Testa la connessione in background"""
        try:
            response = requests.get(f"{url}/", timeout=5)
            if response.status_code == 200:
                self._update_status("✓ Connessione riuscita!")
            else:
                self._update_status(
                    f"✗ Server risponde ma errore: {response.status_code}"
                )
        except requests.exceptions.ConnectTimeout:
            self._update_status("✗ Timeout connessione")
        except requests.exceptions.ConnectionError:
            self._update_status("✗ Impossibile connettersi al server")
        except Exception as e:
            self._update_status(f"✗ Errore: {str(e)}")

    @mainthread
    def _update_status(self, message):
        self.status_label.text = message

    def reset_to_default(self, instance):
        """Reset alle impostazioni di default"""
        self.ip_input.text = DEFAULT_SERVER_IP
        self.port_input.text = DEFAULT_SERVER_PORT
        self.status_label.text = "Reset alle impostazioni di default"
        self.update_current_url()

    def update_current_url(self):
        """Aggiorna la visualizzazione dell'URL corrente"""
        current_url = get_server_url()
        self.current_url_label.text = f"URL corrente: {current_url}"
