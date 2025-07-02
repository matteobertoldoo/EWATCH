from kivy.config import Config

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.clock import Clock
from kivy.utils import platform
from kivy.logger import Logger


# Import camera per Android e Desktop
if platform == "android":
    try:
        from android.permissions import (
            request_permissions,
            Permission,
            check_permission,
        )
        from kivy.uix.camera import Camera

        CAMERA_AVAILABLE = True
    except ImportError:
        CAMERA_AVAILABLE = False
else:
    try:
        from kivy.uix.camera import Camera

        CAMERA_AVAILABLE = True
    except ImportError:
        CAMERA_AVAILABLE = False


class CameraWidget(BoxLayout):
    """Widget riutilizzabile per la camera"""

    def __init__(self, callback=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.callback = callback
        self.camera = None
        self.camera_active = False
        self.captured_image = None
        self.photo_bytes = None

        # Usa spacing=0 e padding=0 per massimizzare lo spazio
        self.spacing = 0
        self.padding = [0, 0, 0, 0]

        # Status label
        self.status_label = Label(
            text="Initializing camera...",
            size_hint_y=None,
            height="30dp",  # Ridotta da 40dp
            text_size=(None, None),
            halign="center",
            valign="middle",
        )
        self.status_label.bind(size=self.update_label_text_size)

        # Camera placeholder
        self.camera_placeholder = Image(size_hint=(1, 1))

        # Buttons layout
        btn_layout = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="40dp",  # Ridotta da 48dp
            spacing=5,  # Ridotto da 10
            padding=[2, 0, 2, 0],  # Padding minimo
        )

        self.btn_capture = Button(text="Scatta Foto", disabled=True)
        self.btn_capture.bind(on_press=self.capture_photo)

        self.btn_retake = Button(text="Nuova Foto", disabled=True)
        self.btn_retake.bind(on_press=self.retake_photo)

        self.add_widget(self.status_label)
        self.add_widget(self.camera_placeholder)
        btn_layout.add_widget(self.btn_capture)
        btn_layout.add_widget(self.btn_retake)
        self.add_widget(btn_layout)

        # Initialize camera
        Clock.schedule_once(self.init_camera, 0.5)

    def update_label_text_size(self, instance, size):
        """Aggiorna text_size per abilitare il text wrapping"""
        instance.text_size = (instance.width, None)

    def init_camera(self, dt):
        """Inizializza la camera"""
        if not CAMERA_AVAILABLE:
            self.status_label.text = "Camera non disponibile su questa piattaforma"
            return

        if platform == "android":
            self.check_permissions()
        else:
            self.add_camera()

    def check_permissions(self):
        """Controlla i permessi camera su Android"""
        try:
            if check_permission("android.permission.CAMERA"):
                self.add_camera()
            else:
                self.request_permissions()
        except Exception as e:
            Logger.error(f"Error checking permissions: {e}")
            self.status_label.text = "Errore controllo permessi"

    def request_permissions(self):
        """Richiede i permessi camera"""
        try:
            request_permissions([Permission.CAMERA], self.permission_callback)
            self.status_label.text = "Richiesta permessi camera..."
        except Exception as e:
            Logger.error(f"Error requesting permissions: {e}")
            self.status_label.text = "Errore richiesta permessi"

    def permission_callback(self, permissions, grant_results):
        """Callback permessi"""
        if all(grant_results):
            Clock.schedule_once(lambda dt: self.add_camera(), 0.1)
        else:
            self.status_label.text = "Permessi camera negati"

    def add_camera(self):
        """Aggiunge il widget camera"""
        try:
            # Se la camera è già attiva, non ricrearla
            if self.camera and self.camera_active:
                return

            # Rimuovi placeholder se presente
            if self.camera_placeholder in self.children:
                self.remove_widget(self.camera_placeholder)

            # Rimuovi immagine catturata se presente
            if self.captured_image and self.captured_image in self.children:
                self.remove_widget(self.captured_image)
                self.captured_image = None

            # Prova a trovare una camera disponibile
            camera_index = self.find_available_camera()
            if camera_index is None:
                self.status_label.text = "Nessuna camera disponibile"
                return

            # Crea o riattiva la camera
            if not self.camera:
                # Usa risoluzione più compatibile per Android
                if platform == "android":
                    resolution = (640, 480)
                else:
                    resolution = (640, 480)

                # Torna al layout originale ma mantieni allow_stretch=True
                self.camera = Camera(
                    play=True,
                    resolution=resolution,
                    size_hint=(1, 1),
                    allow_stretch=True,  # Manteniamo questa proprietà per la dimensione
                    index=camera_index,
                )

                # Aggiungi rotazione tramite canvas - 90 gradi
                from kivy.graphics import PushMatrix, PopMatrix, Rotate

                with self.camera.canvas.before:
                    PushMatrix()
                    self.camera_rotate = Rotate(angle=90, origin=self.camera.center)
                    # Aggiunge il binding per aggiornare l'origine della rotazione
                    self.camera.bind(
                        size=self._update_camera_rotate_origin,
                        pos=self._update_camera_rotate_origin,
                    )

                with self.camera.canvas.after:
                    PopMatrix()
            else:
                # Riattiva la camera esistente
                self.camera.play = True

            # Aggiungi camera al layout principale direttamente come prima
            self.add_widget(self.camera, index=1)

            self.camera_active = True
            self.btn_capture.disabled = False
            self.btn_retake.disabled = True
            self.status_label.text = f"Camera pronta! Premi 'Scatta Foto'"

        except Exception as e:
            Logger.error(f"Error adding camera: {e}")
            self.status_label.text = f"Errore inizializzazione camera: {str(e)}"

    def _update_camera_rotate_origin(self, instance, value):
        """Aggiorna l'origine della rotazione quando la dimensione/posizione della camera cambia"""
        if hasattr(self, "camera_rotate"):
            self.camera_rotate.origin = instance.center

    def find_available_camera(self):
        """Trova una camera disponibile testando diversi indici"""
        # Lista di indici da testare
        if platform == "android":
            test_indices = [1, 0]  # Su Android, prova prima posteriore poi frontale
        else:
            test_indices = [0, 1, 2, 3]

        for index in test_indices:
            try:
                Logger.info(f"Testing camera index {index}")

                # Test più semplice per Android
                if platform == "android":
                    # Su Android, assumiamo che index 0 e 1 esistano sempre
                    return index
                else:
                    # Su desktop, testa creando una camera temporanea
                    test_camera = Camera(play=False, index=index, resolution=(320, 240))
                    test_camera = None
                    Logger.info(f"Camera index {index} is available")
                    return index

            except Exception as e:
                Logger.warning(f"Camera index {index} failed: {e}")
                continue

        Logger.error("No available camera found")
        return 0 if platform == "android" else None  # Su Android, prova comunque con 0

    def capture_photo(self, instance):
        """Cattura foto dalla camera"""
        if not self.camera or not self.camera_active:
            self.status_label.text = "Camera non disponibile"
            return

        try:
            # Ottieni texture dalla camera
            texture = self.camera.texture
            if not texture:
                self.status_label.text = "Errore: texture non disponibile"
                return

            # Ferma la camera ma non rimuoverla
            self.camera.play = False
            self.camera_active = False

            # Rimuovi la camera dal layout
            if self.camera in self.children:
                self.remove_widget(self.camera)

            # Ruota la texture di 90 gradi in senso antiorario
            rotated_texture = self.rotate_texture_90_counterclockwise(texture)

            # Crea widget immagine con la texture ruotata
            self.captured_image = Image(
                size_hint=(1, 1),
                pos_hint={"center_x": 0.5, "center_y": 0.5},  # Centra l'immagine
                allow_stretch=True,  # Permette all'immagine di allungarsi
                keep_ratio=True,  # Mantiene le proporzioni
            )
            self.captured_image.texture = rotated_texture
            self.add_widget(self.captured_image, index=1)

            # Aggiorna UI
            self.btn_capture.disabled = True
            self.btn_retake.disabled = False
            self.status_label.text = "Foto catturata!"

            # Esporta la texture ruotata in un file temporaneo
            import tempfile, os

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name

            try:
                # Salva la texture ruotata come PNG
                rotated_texture.save(temp_path)

                # Leggi i bytes dal file
                with open(temp_path, "rb") as f:
                    photo_bytes = f.read()

                # Callback con la texture e i bytes
                if self.callback:
                    self.callback(rotated_texture, photo_bytes)

            finally:
                # Pulisci il file temporaneo
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except Exception as e:
            Logger.error(f"Error capturing photo: {e}")
            self.status_label.text = f"Errore cattura foto: {str(e)}"

            # Prova a riattivare la camera in caso di errore
            try:
                if self.camera:
                    self.camera.play = True
                    self.camera_active = True
            except:
                pass

    def rotate_texture_90_counterclockwise(self, texture):
        """Ruota una texture di 90 gradi in senso antiorario"""
        from kivy.graphics.texture import Texture

        # Crea una nuova texture con dimensioni scambiate (90 gradi)
        width, height = texture.size
        rotated_texture = Texture.create(
            size=(height, width), colorfmt=texture.colorfmt
        )

        # Ottieni i pixel dalla texture originale
        pixels = texture.pixels

        # Calcola il numero di bytes per pixel (solitamente 4 per RGBA)
        bytes_per_pixel = len(pixels) // (width * height)

        # Crea array per i pixel ruotati
        rotated_pixels = bytearray(len(pixels))

        # Ruota di 90 gradi in senso antiorario
        for y in range(height):
            for x in range(width):
                # Posizione originale
                orig_pos = (y * width + x) * bytes_per_pixel

                # Posizione ruotata (90 gradi antiorario: new_x = height-1-y, new_y = x)
                new_x = height - 1 - y
                new_y = x
                new_pos = (new_y * height + new_x) * bytes_per_pixel

                # Copia i pixel
                rotated_pixels[new_pos : new_pos + bytes_per_pixel] = pixels[
                    orig_pos : orig_pos + bytes_per_pixel
                ]

        # Applica i pixel ruotati alla nuova texture
        rotated_texture.blit_buffer(
            bytes(rotated_pixels), colorfmt=texture.colorfmt, bufferfmt="ubyte"
        )

        return rotated_texture

    def retake_photo(self, instance):
        """Riprendi foto"""
        try:
            # Rimuovi immagine catturata
            if self.captured_image and self.captured_image in self.children:
                self.remove_widget(self.captured_image)
                self.captured_image = None

            # Riattiva la camera
            if self.camera:
                # Aggiungi di nuovo la camera al layout
                self.add_widget(self.camera, index=1)

                # Riavvia la camera
                self.camera.play = True
                self.camera_active = True

                # Aggiorna UI
                self.btn_capture.disabled = False
                self.btn_retake.disabled = True
                self.status_label.text = "Camera riattivata! Premi 'Scatta Foto'"
            else:
                # Se per qualche motivo la camera non esiste più, ricreala
                self.add_camera()

        except Exception as e:
            Logger.error(f"Error retaking photo: {e}")
            self.status_label.text = f"Errore: {str(e)}"
            # In caso di errore, prova a ricreare la camera
            Clock.schedule_once(lambda dt: self.add_camera(), 0.5)

    def get_texture(self):
        """Ottieni la texture catturata"""
        if self.captured_image and self.captured_image.texture:
            return self.captured_image.texture
        return None

    def stop_camera(self):
        """Ferma la camera"""
        if self.camera:
            self.camera.play = False
            self.camera_active = False

    def restart_camera(self):
        """Riavvia la camera (utile quando si torna alla schermata)"""
        if self.camera and not self.camera_active and not self.captured_image:
            try:
                self.camera.play = True
                self.camera_active = True
                if self.camera not in self.children:
                    self.add_widget(self.camera, index=1)
                self.btn_capture.disabled = False
                self.status_label.text = "Camera riattivata! Premi 'Scatta Foto'"
            except Exception as e:
                Logger.error(f"Error restarting camera: {e}")
                # Se non riesce a riavviare, ricrea la camera
                Clock.schedule_once(lambda dt: self.add_camera(), 0.5)
