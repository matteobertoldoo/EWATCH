import asyncio
import struct
import os
import json
import requests
from datetime import datetime
from bleak import BleakClient, BleakScanner
import numpy as np
from PIL import Image
import io

# UUIDs matching those in the Arduino code
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
IMAGE_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
DATA_UUID = "80dcca86-d593-484b-8b13-72db9d98faea"
CONTROL_UUID = "a9da86e1-4456-4bea-b82d-b7a8e834bb0a"
SERVER_URL = (
    "https://svbv8fg7aa5i.share.zrok.io/"  # URL del server per il riconoscimento
)
# Global variables for image data
image_buffer = bytearray()
image_size = 0
total_chunks = 0
received_chunks = 0
transfer_active = False
image_metadata_received = False
chunks_received = set()
client_instance = None  # Store client reference globally


async def send_user_data(client, data):
    """Send mock user data to the device after image processing"""
    # Give some time to process the image
    # await asyncio.sleep(2)

    # Generate mock data()
    json_data = json.dumps(data)

    print(f"Sending user data: {json_data}")

    # Send the data to the device
    try:
        await client.write_gatt_char(DATA_UUID, json_data.encode("utf-8"))
        print("User data sent successfully")
    except Exception as e:
        print(f"Error sending user data: {e}")


async def notification_handler(sender, data):
    """Handle incoming notifications from the device"""
    global image_buffer, image_size, total_chunks, received_chunks
    global transfer_active, image_metadata_received, chunks_received, client_instance

    # Check if this is the data characteristic (metadata or status updates)
    if str(sender.uuid) == DATA_UUID:
        try:
            message = data.decode("utf-8")
            print(f"Received data: {message}")

            if message == "IMAGE_READY":
                print("Image is ready for transfer. Sending READY command...")
                # Reset all state for a new transfer
                reset_transfer_state()
                transfer_active = True

                # Request metadata using the global client
                if client_instance:
                    await client_instance.write_gatt_char(CONTROL_UUID, b"READY")
                else:
                    print("Error: Client reference not available")

            elif message == "DONE":
                print("Transfer completed")
                if received_chunks == total_chunks:
                    save_and_process_image()
                transfer_active = False

            elif "," in message:  # This is metadata
                try:
                    size_str, chunks_str = message.split(",")
                    image_size = int(size_str)
                    total_chunks = int(chunks_str)
                    image_metadata_received = True
                    print(
                        f"Image metadata: size={image_size} bytes, chunks={total_chunks}"
                    )

                    # Resize the buffer
                    image_buffer = bytearray(image_size)

                    # Start requesting chunks
                    if client_instance:
                        await request_next_chunk(client_instance)
                    else:
                        print("Error: Client reference not available")
                except Exception as e:
                    print(f"Error parsing metadata: {e}")
        except UnicodeDecodeError:
            print("Warning: Received binary data on DATA_UUID characteristic")

    # Check if this is the image characteristic (actual image data)
    elif str(sender.uuid) == IMAGE_UUID:
        if not transfer_active or not image_metadata_received:
            return

        try:
            # Search for the colon byte that separates header from data
            header_end = -1
            for i in range(min(10, len(data))):
                if data[i] == ord(":"):
                    header_end = i
                    break

            if header_end >= 0:
                # Extract chunk index - safely decode only the header portion
                try:
                    chunk_idx = int(data[:header_end].decode("utf-8"))
                    # Extract actual data
                    chunk_data = data[header_end + 1 :]
                except UnicodeDecodeError:
                    print(f"Warning: Invalid chunk header format, using fallback index")
                    chunk_data = data
                    chunk_idx = received_chunks
            else:
                # No header found, assume it's just data
                chunk_data = data
                # Use received_chunks as the index (fallback)
                chunk_idx = received_chunks

            # Calculate where this chunk goes in the buffer
            chunk_size = 512
            offset = chunk_idx * chunk_size

            # Copy the data to the right position in the buffer
            data_len = len(chunk_data)
            if offset + data_len <= len(image_buffer):
                image_buffer[offset : offset + data_len] = chunk_data
            else:
                print(
                    f"Warning: Chunk data exceeds buffer bounds: offset={offset}, data_len={data_len}, buffer_size={len(image_buffer)}"
                )

            # Mark this chunk as received
            chunks_received.add(chunk_idx)
            received_chunks = len(chunks_received)

            print(f"Received chunk {chunk_idx+1}/{total_chunks} ({data_len} bytes)")

            # Request next chunk
            if client_instance:
                await request_next_chunk(client_instance)
            else:
                print("Error: Client reference not available")
        except Exception as e:
            print(f"Error processing image chunk: {e}")
            # Even if we have an error, try to continue with next chunk
            if client_instance and transfer_active:
                await request_next_chunk(client_instance)


def reset_transfer_state():
    """Reset all state variables for a new transfer"""
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
    """Save the current image buffer, send to server, and display"""
    global image_buffer, client_instance

    try:
        # Create an image from the buffer
        img = Image.open(io.BytesIO(image_buffer))

        # Rotate the image by -90 degrees (counterclockwise)
        rotated_img = img.rotate(-90, expand=True)
        flipped_img = rotated_img.transpose(Image.FLIP_TOP_BOTTOM)

        # Save the rotated image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"image_{timestamp}.jpg"
        flipped_img.save(filename)
        print(f"Image saved as {filename}")

        # Converti l'immagine in bytes per inviarla al server
        img_byte_arr = io.BytesIO()
        flipped_img.save(img_byte_arr, format="JPEG")
        img_byte_arr = img_byte_arr.getvalue()

        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            # Salva la texture ruotata come PNG
            flipped_img.save(temp_path)

            # Leggi i bytes dal file
            with open(temp_path, "rb") as f:
                photo_bytes = f.read()

            # Callback con la texture e i bytes
            asyncio.create_task(send_image_to_server(photo_bytes))

        finally:
            # Pulisci il file temporaneo
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as e:
        print(f"Failed to process or display image: {e}")

        # Fallback: save the original image
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"image_original_{timestamp}.jpg"
            with open(filename, "wb") as f:
                f.write(image_buffer)
            print(f"Original image saved as {filename}")
        except Exception as fallback_error:
            print(f"Failed to save original image: {fallback_error}")


async def send_image_to_server(image_bytes):
    """Invia l'immagine al server per il riconoscimento"""
    try:
        url = f"{SERVER_URL}/recognize"
        files = {"foto": ("image.jpg", image_bytes, "image/jpeg")}

        # print(files)
        print("Invio foto al server...")
        response = requests.post(url, files=files, timeout=10)

        if response.status_code == 200:
            # {'access_valid_until': '2025-06-22T13:00:01.907240', 'confidence': 0.539, 'id': '1943b8d8-5d72-47eb-8b57-e410961eb155', 'match': True, 'message': 'Paziente riconosciuto con confidenza 53.9%. Accesso ai dati autorizzato per 60 secondi.'}
            data = response.json()
            if data.get("match", True):
                print(f"Data: {data}")
                patient_id = data.get("id", "")
                asyncio.create_task(fetch_patient_data(patient_id))

            else:
                print("Paziente non riconosciuto")
        else:
            print(f"Errore: {response.status_code}, response: {response.text}")
    except Exception as e:
        print(f"Errore nell'invio dell'immagine: {str(e)}")


async def fetch_patient_data(patient_id):
    """Recupera i dati del paziente dal server
    same as: curl -X POST http://localhost:5000/dati -F "id=1943b8d8-5d72-47eb-8b57-e410961eb155"tB\xe3\xc8\xeb\xfd\x907\xf2
    """
    try:
        url = f"{SERVER_URL}/dati"
        data = {"id": patient_id}

        print(f"Fetching data for patient ID: {patient_id}")
        response = requests.post(url, data=data, timeout=10)

        if response.status_code == 200:
            # {'access_valid_until': '2025-06-22T13:00:01.907240', 'confidence': 0.539, 'id': '1943b8d8-5d72-47eb-8b57-e410961eb155', 'match': True, 'message': 'Paziente riconosciuto con confidenza 53.9%. Accesso ai dati autorizzato per 60 secondi.'}
            data = response.json()

            # Send mock user data back to device
            if client_instance:
                asyncio.create_task(send_user_data(client_instance, data))
                print("Started task to send user data")
            else:
                print("Unable to send user data - client not available")

        else:
            print(f"Errore: {response.status_code}, response: {response.text}")
    except Exception as e:
        print(f"Errore nell'invio dell'immagine: {str(e)}")


async def request_next_chunk(client):
    """Request the next chunk of the image"""
    global received_chunks, total_chunks

    if not transfer_active or received_chunks >= total_chunks:
        return

    # Find the first missing chunk
    for i in range(total_chunks):
        if i not in chunks_received:
            print(f"Requesting chunk {i+1}/{total_chunks}")
            await client.write_gatt_char(CONTROL_UUID, f"GET:{i}".encode("utf-8"))
            return


async def main():
    global client_instance

    # Scan for devices
    print("Scanning for EWatch device...")
    device = None

    # Try to find the device by name
    scanner = BleakScanner()
    devices = await scanner.discover()
    for d in devices:
        if d.name and "EWatch" in d.name:
            device = d
            break

    if not device:
        print("EWatch device not found. Available devices:")
        for d in devices:
            print(f"  {d.name or 'Unknown'} ({d.address})")

        # Ask user to select a device
        device_address = input("Enter the device address to connect to: ")
        for d in devices:
            if d.address == device_address:
                device = d
                break

        if not device:
            print("Invalid device address")
            return

    print(f"Connecting to {device.name or device.address}...")

    async with BleakClient(device) as client:
        client_instance = client  # Store client reference globally
        print(f"Connected: {client.is_connected}")

        # Subscribe to notifications
        await client.start_notify(IMAGE_UUID, notification_handler)
        await client.start_notify(DATA_UUID, notification_handler)

        print("Press the button on your EWatch to take a picture, or type 'q' to quit")

        # Wait for user input
        while True:
            cmd = await asyncio.to_thread(input, "> ")
            if cmd.lower() == "q":
                break

            # If user types 'cancel', send a cancel command
            if cmd.lower() == "cancel":
                await client.write_gatt_char(CONTROL_UUID, b"CANCEL")
                print("Cancellation request sent")

            # If user types 'send', manually send mock user data
            if cmd.lower() == "send":
                await send_user_data(client)
                print("Manually sending user data")

        # Clean up
        await client.stop_notify(IMAGE_UUID)
        await client.stop_notify(DATA_UUID)
        client_instance = None
        print("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
