import asyncio
import json
import requests
from datetime import datetime
from bleak import BleakClient, BleakScanner
from PIL import Image
import io

# UUIDs dei servizi e caratteristiche
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
IMAGE_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
DATA_UUID = "80dcca86-d593-484b-8b13-72db9d98faea"
CONTROL_UUID = "a9da86e1-4456-4bea-b82d-b7a8e834bb0a"

# Variabili globali per i dati dell'immagine
image_buffer = bytearray()
image_size = 0
total_chunks = 0
received_chunks = 0
transfer_active = False
image_metadata_received = False
chunks_received = set()
client_instance = None


def get_server_url():
    """Restituisce l'URL del server (potrebbe essere configurabile)"""
    return "http://localhost:5000"  # Modifica con l'URL del tuo server


def generate_mock_user_data():
    """Genera dati utente di esempio"""
    return {
        "name": "John",
        "surname": "Doe",
        "age": 45,
        "weight": 75.5,
        "height": 180.0,
        "diseases": ["Hypertension", "Type 2 Diabetes"],
        "medications": ["Metformin", "Lisinopril", "Aspirin"],
    }


async def send_user_data(client):
    """Invia dati utente al dispositivo"""
    user_data = generate_mock_user_data()
    json_data = json.dumps(user_data)
    print(f"Invio dati utente: {json_data}")
    await client.write_gatt_char(DATA_UUID, json_data.encode("utf-8"))
    print("Dati inviati con successo")


async def notification_handler(sender, data):
    """Gestisce le notifiche dal dispositivo"""
    global image_buffer, image_size, total_chunks, received_chunks
    global transfer_active, image_metadata_received, chunks_received, client_instance

    # Gestione dati di controllo
    if str(sender.uuid) == DATA_UUID:
        try:
            message = data.decode("utf-8")
            print(f"Ricevuto: {message}")

            if message == "IMAGE_READY":
                print("Immagine pronta per il trasferimento. Invio comando READY...")
                reset_transfer_state()
                transfer_active = True
                await client_instance.write_gatt_char(CONTROL_UUID, b"READY")

            elif message == "DONE":
                if received_chunks == total_chunks:
                    save_and_process_image()
                transfer_active = False

            elif "," in message:  # Metadati immagine
                size_str, chunks_str = message.split(",")
                image_size = int(size_str)
                total_chunks = int(chunks_str)
                image_metadata_received = True
                print(f"Metadati: dimensione={image_size} bytes, chunks={total_chunks}")

                image_buffer = bytearray(image_size)
                await request_next_chunk(client_instance)
        except:
            pass

    # Gestione dati immagine
    elif str(sender.uuid) == IMAGE_UUID and transfer_active and image_metadata_received:
        try:
            # Elabora header del chunk
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
                chunk_idx = received_chunks

            # Salva il chunk nel buffer
            chunk_size = 512
            offset = chunk_idx * chunk_size
            data_len = len(chunk_data)

            if offset + data_len <= len(image_buffer):
                image_buffer[offset : offset + data_len] = chunk_data

            chunks_received.add(chunk_idx)
            received_chunks = len(chunks_received)

            print(f"Chunk {chunk_idx+1}/{total_chunks}")
            await request_next_chunk(client_instance)
        except Exception as e:
            print(f"Errore nel processare chunk: {e}")
            await request_next_chunk(client_instance)


def reset_transfer_state():
    """Resetta le variabili per un nuovo trasferimento"""
    global image_buffer, image_size, total_chunks, received_chunks
    global transfer_active, image_metadata_received, chunks_received

    image_buffer = bytearray()
    image_size = 0
    total_chunks = 0
    received_chunks = 0
    image_metadata_received = False
    chunks_received = set()
    transfer_active = False


def save_and_process_image():
    """Salva l'immagine ricevuta e la invia al server"""
    global image_buffer, client_instance

    try:
        img = Image.open(io.BytesIO(image_buffer))
        rotated_img = img.rotate(-90, expand=True)
        flipped_img = rotated_img.transpose(Image.FLIP_TOP_BOTTOM)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"image_{timestamp}.jpg"
        flipped_img.save(filename)
        print(f"Immagine salvata come {filename}")

        # Converti l'immagine in bytes per inviarla al server
        img_byte_arr = io.BytesIO()
        flipped_img.save(img_byte_arr, format="JPEG")
        img_byte_arr = img_byte_arr.getvalue()

        # Invia immagine al server
        asyncio.create_task(send_image_to_server(img_byte_arr))

        # Mostra l'immagine localmente
        flipped_img.show()

        # Invia dati utente al dispositivo come prima
        asyncio.create_task(send_user_data(client_instance))
    except Exception as e:
        print(f"Errore nel processare l'immagine: {e}")


async def send_image_to_server(image_bytes):
    """Invia l'immagine al server per il riconoscimento"""
    try:
        server_url = get_server_url()
        url = f"{server_url}/recognize"
        files = {"image": ("image.jpg", image_bytes, "image/jpeg")}

        print("Invio foto al server...")
        response = requests.post(url, files=files, timeout=10)

        if response.status_code == 200:
            data = response.json()
            patient_id = data.get("patient_id")
            confidence = data.get("confidence", 0)

            if patient_id:
                print(
                    f"Paziente riconosciuto (ID: {patient_id}, conf: {confidence:.2f})"
                )
                await fetch_patient_data(patient_id)
            else:
                print("Paziente non riconosciuto")
        else:
            print(f"Errore: {response.status_code}")
    except Exception as e:
        print(f"Errore nell'invio dell'immagine: {str(e)}")


async def fetch_patient_data(patient_id):
    """Recupera i dati del paziente dal server"""
    try:
        server_url = get_server_url()
        url = f"{server_url}/patient/{patient_id}"

        print("Richiesta dati paziente...")
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            name = data.get("name", "")
            surname = data.get("surname", "")
            age = data.get("age", "")
            weight = data.get("weight", "")
            height = data.get("height", "")
            diseases = data.get("diseases", [])
            medications = data.get("medications", [])

            patient_data = {
                "name": name,
                "surname": surname,
                "age": age,
                "weight": weight,
                "height": height,
                "diseases": diseases,
                "medications": medications,
            }

            print(f"Dati paziente ricevuti: {patient_data}")
        else:
            print(f"Errore nel recupero dei dati del paziente: {response.status_code}")
    except Exception as e:
        print(f"Errore nel recupero dei dati del paziente: {str(e)}")


async def request_next_chunk(client):
    """Richiede il prossimo chunk dell'immagine"""
    global received_chunks, total_chunks

    if not transfer_active or received_chunks >= total_chunks:
        return

    for i in range(total_chunks):
        if i not in chunks_received:
            await client.write_gatt_char(CONTROL_UUID, f"GET:{i}".encode("utf-8"))
            return


async def main():
    global client_instance

    print("Ricerca del dispositivo EWatch...")

    # Scansione solo per EWatch
    scanner = BleakScanner()
    devices = await scanner.discover()
    device = None

    for d in devices:
        if d.name and "EWatch" in d.name:
            device = d
            break

    if not device:
        print("EWatch non trovato. Programma terminato.")
        return

    print(f"Connessione a {device.name}...")

    async with BleakClient(device) as client:
        client_instance = client
        print(f"Connesso: {client.is_connected}")

        await client.start_notify(IMAGE_UUID, notification_handler)
        await client.start_notify(DATA_UUID, notification_handler)

        print("Premi il pulsante su EWatch per scattare una foto, o 'q' per uscire")

        while True:
            cmd = await asyncio.to_thread(input, "> ")
            if cmd.lower() == "q":
                break

        await client.stop_notify(IMAGE_UUID)
        await client.stop_notify(DATA_UUID)
        print("Disconnesso")


if __name__ == "__main__":
    asyncio.run(main())
