#!/usr/bin/env python3

import os
import uuid
import sqlite3
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import face_recognition
import numpy as np
from PIL import Image
import io

app = Flask(__name__)

# Configurazione
UPLOAD_FOLDER = "face_uploads"
ENCODINGS_FOLDER = "face_encodings"
DATABASE = "face_db.db"
SIMILARITY_THRESHOLD = 0.6  # Soglia per il riconoscimento (più basso = più strict)
ACCESS_WINDOW_SECONDS = 60  # Tempo in secondi per accedere ai dati dopo riconoscimento

# Crea cartelle necessarie
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ENCODINGS_FOLDER, exist_ok=True)


# --- Database Setup ---
def init_database():
    """Inizializza il database SQLite"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Tabella pazienti
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            surname TEXT,
            age INTEGER,
            weight REAL,
            height REAL, 
            blood_type TEXT,
            allergies TEXT,
            diseases TEXT,
            medications TEXT,
            photo_path TEXT,
            face_encoding_path TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """
    )

    # Tabella log riconoscimenti
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recognition_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            recognition_time TEXT,
            confidence REAL,
            image_path TEXT,
            success INTEGER
        )
    """
    )

    # Tabella sessioni di accesso (per controllo timer)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS access_sessions (
            patient_id TEXT PRIMARY KEY,
            last_recognition_time TEXT,
            session_valid_until TEXT
        )
    """
    )

    conn.commit()
    conn.close()


# --- Utilità per gestione immagini ---
def save_image(file, folder, filename):
    """Salva un'immagine nella cartella specificata"""
    filepath = os.path.join(folder, filename)
    file.save(filepath)
    return filepath


def load_and_process_image(image_path):
    """Carica e processa un'immagine per il riconoscimento facciale"""
    try:
        # Carica l'immagine
        image = face_recognition.load_image_file(image_path)

        # Trova i volti nell'immagine
        face_locations = face_recognition.face_locations(image)

        if not face_locations:
            return None, "Nessun volto rilevato nell'immagine"

        if len(face_locations) > 1:
            return (
                None,
                "Rilevati più volti. Assicurati che ci sia solo una persona nell'immagine",
            )

        # Genera encoding del volto
        face_encodings = face_recognition.face_encodings(image, face_locations)

        if not face_encodings:
            return None, "Impossibile generare encoding del volto"

        return face_encodings[0], None

    except Exception as e:
        return None, f"Errore nel processamento dell'immagine: {str(e)}"


def save_face_encoding(encoding, patient_id):
    """Salva l'encoding del volto su file"""
    encoding_path = os.path.join(ENCODINGS_FOLDER, f"{patient_id}.npy")
    np.save(encoding_path, encoding)
    return encoding_path


def load_face_encoding(patient_id):
    """Carica l'encoding del volto da file"""
    encoding_path = os.path.join(ENCODINGS_FOLDER, f"{patient_id}.npy")
    if os.path.exists(encoding_path):
        return np.load(encoding_path)
    return None


# --- Funzioni database ---
def save_patient(patient_data):
    """Salva un paziente nel database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO patients (id, name, surname, age, weight, height, blood_type, 
                            allergies, diseases, medications, photo_path, 
                            face_encoding_path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        patient_data,
    )

    conn.commit()
    conn.close()


def get_patient(patient_id):
    """Recupera i dati di un paziente"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        # Parse JSON stored as text for lists
        diseases = json.loads(result[8]) if result[8] else []
        medications = json.loads(result[9]) if result[9] else []

        return {
            "id": result[0],
            "name": result[1],
            "surname": result[2],
            "age": result[3],
            "weight": result[4],
            "height": result[5],
            "blood_type": result[6],
            "allergies": result[7],
            "diseases": diseases,
            "medications": medications,
            "photo_path": result[10],
            "face_encoding_path": result[11],
            "created_at": result[12],
            "updated_at": result[13],
        }
    return None


def log_recognition(patient_id, confidence, image_path, success):
    """Registra un tentativo di riconoscimento"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    now = datetime.now()

    cursor.execute(
        """
        INSERT INTO recognition_log (patient_id, recognition_time, confidence, 
                                   image_path, success)
        VALUES (?, ?, ?, ?, ?)
    """,
        (patient_id, now.isoformat(), confidence, image_path, success),
    )

    # Se il riconoscimento è riuscito, crea/aggiorna la sessione di accesso
    if success and patient_id:
        valid_until = now + timedelta(seconds=ACCESS_WINDOW_SECONDS)
        cursor.execute(
            """
            INSERT OR REPLACE INTO access_sessions 
            (patient_id, last_recognition_time, session_valid_until)
            VALUES (?, ?, ?)
        """,
            (patient_id, now.isoformat(), valid_until.isoformat()),
        )

    conn.commit()
    conn.close()


def check_access_permission(patient_id):
    """Verifica se è possibile accedere ai dati del paziente"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT session_valid_until FROM access_sessions 
        WHERE patient_id = ?
    """,
        (patient_id,),
    )

    result = cursor.fetchone()
    conn.close()

    if not result:
        return False, "Nessuna sessione di riconoscimento valida trovata"

    valid_until = datetime.fromisoformat(result[0])
    now = datetime.now()

    if now > valid_until:
        return (
            False,
            "Sessione di accesso scaduta. Eseguire nuovamente il riconoscimento",
        )

    remaining_seconds = int((valid_until - now).total_seconds())
    return (
        True,
        f"Accesso autorizzato. Sessione valida per altri {remaining_seconds} secondi",
    )


def cleanup_expired_sessions():
    """Rimuove le sessioni scadute dal database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    now = datetime.now().isoformat()
    cursor.execute(
        """
        DELETE FROM access_sessions 
        WHERE session_valid_until < ?
    """,
        (now,),
    )

    conn.commit()
    conn.close()


# --- Riconoscimento facciale ---
def find_matching_patient(target_encoding):
    """Trova il paziente corrispondente all'encoding fornito"""
    best_match = None
    best_confidence = float("inf")

    # Carica tutti i pazienti
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM patients")
    patient_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    # Confronta con ogni paziente registrato
    for patient_id in patient_ids:
        stored_encoding = load_face_encoding(patient_id)

        if stored_encoding is not None:
            # Calcola la distanza (più bassa = più simile)
            distance = face_recognition.face_distance(
                [stored_encoding], target_encoding
            )[0]

            if distance < best_confidence:
                best_confidence = distance
                best_match = patient_id

    # Verifica se il match è abbastanza buono
    if best_match and best_confidence < SIMILARITY_THRESHOLD:
        return best_match, 1.0 - best_confidence  # Converte distanza in confidenza

    return None, 0.0


# --- API Endpoints ---


@app.route("/help", methods=["GET"])
def help_info():
    """Mostra le informazioni di aiuto per l'API"""
    return (
        jsonify(
            {
                "message": "Benvenuto nel Secure Face Recognition Server",
                "version": "2.0.0",
                "endpoints": {
                    "/": "Controllo stato del server",
                    "/register": "Registra un nuovo paziente con foto",
                    "/recognize": "Riconosce un paziente dalla foto",
                    "/dati": "Recupera i dati di un paziente (solo dopo riconoscimento)",
                    "/patients": "Non più disponibile per sicurezza",
                    "/patient-count": "Ottieni il numero totale di pazienti registrati",
                    "/log": "Recupera il log dei riconoscimenti (statistiche anonime)",
                    "/stats": "Statistiche aggregate del sistema",
                    "/session-status/<patient_id>": "Verifica lo stato della sessione per un paziente specifico",
                },
            }
        ),
        200,
    )


@app.route("/", methods=["GET"])
def health_check():
    """Endpoint per verificare che il server sia attivo"""
    return (
        jsonify(
            {
                "status": "online",
                "service": "Secure Face Recognition Server",
                "version": "2.0.0",
                "access_window_seconds": ACCESS_WINDOW_SECONDS,
                "timestamp": datetime.now().isoformat(),
            }
        ),
        200,
    )


@app.route("/register", methods=["POST"])
def register_patient():
    """Registra un nuovo paziente con la sua foto"""
    try:
        # Valida i dati ricevuti
        if "foto" not in request.files:
            return jsonify({"error": "Nessuna foto ricevuta"}), 400

        name = request.form.get("nome", "").strip()
        surname = request.form.get("surname", "").strip()
        age = request.form.get("age", 0)
        try:
            age = int(age)
        except:
            age = 0

        weight = request.form.get("weight", 0)
        try:
            weight = float(weight)
        except:
            weight = 0.0

        height = request.form.get("height", 0)
        try:
            height = float(height)
        except:
            height = 0.0

        blood_type = request.form.get("gruppo", "").strip()
        allergies = request.form.get("allergie", "").strip()

        # Handle diseases and medications as arrays
        diseases = request.form.getlist("diseases[]") or []
        medications = request.form.getlist("medications[]") or []

        if not name:
            return jsonify({"error": "Nome è obbligatorio"}), 400

        # Genera ID univoco per il paziente
        patient_id = str(uuid.uuid4())

        # Salva l'immagine
        photo_file = request.files["foto"]
        photo_filename = f"{patient_id}.jpg"
        photo_path = save_image(photo_file, UPLOAD_FOLDER, photo_filename)

        # Processa l'immagine per estrarre l'encoding del volto
        face_encoding, error = load_and_process_image(photo_path)

        if error:
            return jsonify({"error": error}), 400

        # Salva l'encoding del volto
        encoding_path = save_face_encoding(face_encoding, patient_id)

        # Salva i dati nel database
        timestamp = datetime.now().isoformat()
        patient_data = (
            patient_id,
            name,
            surname,
            age,
            weight,
            height,
            blood_type,
            allergies,
            json.dumps(diseases),
            json.dumps(medications),
            photo_path,
            encoding_path,
            timestamp,
            timestamp,
        )
        save_patient(patient_data)

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Paziente registrato con successo",
                    "id": patient_id,
                    "name": name,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": f"Errore interno del server: {str(e)}"}), 500


@app.route("/recognize", methods=["POST"])
def recognize_patient():
    """Riconosce un paziente dalla sua foto"""
    try:
        # Pulisci sessioni scadute
        cleanup_expired_sessions()

        # Valida la richiesta
        if "foto" not in request.files:
            return jsonify({"error": "Nessuna foto ricevuta"}), 400

        # Salva l'immagine temporaneamente
        photo_file = request.files["foto"]
        temp_filename = f"temp_{uuid.uuid4().hex}.jpg"
        temp_path = save_image(photo_file, UPLOAD_FOLDER, temp_filename)

        try:
            # Processa l'immagine
            face_encoding, error = load_and_process_image(temp_path)

            if error:
                return jsonify({"error": error, "match": False}), 400

            # Cerca il paziente corrispondente
            patient_id, confidence = find_matching_patient(face_encoding)

            if patient_id:
                # Log del riconoscimento riuscito (crea anche la sessione di accesso)
                log_recognition(patient_id, confidence, temp_filename, 1)

                return (
                    jsonify(
                        {
                            "match": True,
                            "id": patient_id,
                            "confidence": round(confidence, 3),
                            "access_valid_until": (
                                datetime.now()
                                + timedelta(seconds=ACCESS_WINDOW_SECONDS)
                            ).isoformat(),
                            "message": f"Paziente riconosciuto con confidenza {round(confidence * 100, 1)}%. Accesso ai dati autorizzato per {ACCESS_WINDOW_SECONDS} secondi.",
                        }
                    ),
                    200,
                )
            else:
                # Log del riconoscimento fallito
                log_recognition(None, 0.0, temp_filename, 0)

                return (
                    jsonify(
                        {
                            "match": False,
                            "message": "Nessun paziente corrispondente trovato",
                        }
                    ),
                    200,
                )

        finally:
            # Rimuovi l'immagine temporanea
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        return jsonify({"error": f"Errore interno del server: {str(e)}"}), 500


@app.route("/dati", methods=["POST"])
def get_patient_data():
    """Recupera i dati di un paziente specifico - SOLO se riconosciuto di recente"""
    try:
        patient_id = request.form.get("id", "").strip()

        if not patient_id:
            return jsonify({"error": "ID paziente mancante"}), 400

        # Verifica permessi di accesso
        has_permission, message = check_access_permission(patient_id)

        if not has_permission:
            return (
                jsonify(
                    {
                        "error": "Accesso negato",
                        "message": message,
                        "required_action": "Eseguire nuovamente il riconoscimento facciale",
                    }
                ),
                403,
            )

        # Recupera i dati del paziente
        patient = get_patient(patient_id)

        if not patient:
            return jsonify({"error": "Paziente non trovato"}), 404

        return (
            jsonify(
                {
                    "id": patient_id,
                    "name": patient["name"],
                    "surname": patient["surname"],
                    "age": patient["age"],
                    "weight": patient["weight"],
                    "height": patient["height"],
                    "diseases": patient["diseases"],
                    "medications": patient["medications"],
                    "blood_type": patient["blood_type"],
                    "access_info": message,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": f"Errore interno del server: {str(e)}"}), 500


@app.route("/patients", methods=["GET"])
def list_patients():
    """ENDPOINT RIMOSSO PER SICUREZZA - Non è più possibile ottenere la lista di tutti i pazienti"""
    return (
        jsonify(
            {
                "error": "Endpoint non autorizzato",
                "message": "Per motivi di sicurezza, non è possibile ottenere la lista completa dei pazienti",
                "available_actions": [
                    "POST /register - Registra nuovo paziente",
                    "POST /recognize - Riconosci paziente esistente",
                    "POST /dati - Ottieni dati paziente (solo dopo riconoscimento)",
                ],
            }
        ),
        403,
    )


@app.route("/patient-count", methods=["GET"])
def get_patient_count():
    """Restituisce solo il numero totale di pazienti registrati (senza dati sensibili)"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM patients")
        count = cursor.fetchone()[0]
        conn.close()

        return (
            jsonify(
                {
                    "total_patients": count,
                    "message": "Conteggio pazienti disponibile. Per accedere ai dati specifici è necessario il riconoscimento facciale.",
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": f"Errore interno del server: {str(e)}"}), 500


@app.route("/log", methods=["GET"])
def get_recognition_log():
    """Recupera il log dei riconoscimenti (solo statistiche, senza dati sensibili)"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Solo statistiche aggregate, non dati specifici dei pazienti
        cursor.execute(
            """
            SELECT recognition_time, confidence, success 
            FROM recognition_log 
            ORDER BY recognition_time DESC 
            LIMIT 50
        """
        )

        results = cursor.fetchall()
        conn.close()

        log_entries = []
        for result in results:
            log_entries.append(
                {
                    "time": result[0],
                    "confidence": result[1] if result[1] else 0,
                    "success": bool(result[2]),
                }
            )

        return (
            jsonify(
                {
                    "log": log_entries,
                    "count": len(log_entries),
                    "note": "Log anonimizzato per sicurezza - IDs pazienti rimossi",
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": f"Errore interno del server: {str(e)}"}), 500


@app.route("/stats", methods=["GET"])
def get_statistics():
    """Recupera statistiche aggregate del sistema (senza dati sensibili)"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Conta pazienti totali
        cursor.execute("SELECT COUNT(*) FROM patients")
        total_patients = cursor.fetchone()[0]

        # Conta riconoscimenti totali
        cursor.execute("SELECT COUNT(*) FROM recognition_log")
        total_recognitions = cursor.fetchone()[0]

        # Conta riconoscimenti riusciti
        cursor.execute("SELECT COUNT(*) FROM recognition_log WHERE success = 1")
        successful_recognitions = cursor.fetchone()[0]

        # Conta sessioni attive
        cursor.execute(
            """
            SELECT COUNT(*) FROM access_sessions 
            WHERE session_valid_until > ?
        """,
            (datetime.now().isoformat(),),
        )
        active_sessions = cursor.fetchone()[0]

        conn.close()

        success_rate = 0
        if total_recognitions > 0:
            success_rate = (successful_recognitions / total_recognitions) * 100

        return (
            jsonify(
                {
                    "total_patients": total_patients,
                    "total_recognitions": total_recognitions,
                    "successful_recognitions": successful_recognitions,
                    "success_rate": round(success_rate, 2),
                    "active_sessions": active_sessions,
                    "access_window_seconds": ACCESS_WINDOW_SECONDS,
                    "threshold": SIMILARITY_THRESHOLD,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": f"Errore interno del server: {str(e)}"}), 500


@app.route("/session-status/<patient_id>", methods=["GET"])
def check_session_status(patient_id):
    """Verifica lo stato della sessione per un paziente specifico"""
    try:
        has_permission, message = check_access_permission(patient_id)

        return (
            jsonify(
                {
                    "patient_id": patient_id,
                    "has_access": has_permission,
                    "message": message,
                    "access_window_seconds": ACCESS_WINDOW_SECONDS,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": f"Errore interno del server: {str(e)}"}), 500


# --- Avvio del server ---
if __name__ == "__main__":
    print("Inizializzazione Secure Face Recognition Server...")
    init_database()
    print("Database inizializzato.")
    print(f"Server in ascolto su http://0.0.0.0:5000")
    print(f"Soglia di riconoscimento: {SIMILARITY_THRESHOLD}")
    print(f"Finestra di accesso: {ACCESS_WINDOW_SECONDS} secondi dopo riconoscimento")
    print(
        "⚠️  Sicurezza: Accesso ai dati pazienti solo dopo riconoscimento facciale recente"
    )
    app.run(host="0.0.0.0", port=5000, debug=True)
