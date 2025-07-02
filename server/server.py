#!/usr/bin/env python3

import os
import uuid
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import face_recognition
import numpy as np

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
ENCODING_FOLDER = "encodings"
DB = "pazienti.db"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ENCODING_FOLDER, exist_ok=True)

# --- Funzioni di supporto ---


def salva_db(id_paziente, nome, gruppo, allergie, path_foto):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS pazienti (
                    id TEXT PRIMARY KEY,
                    nome TEXT,
                    gruppo TEXT,
                    allergie TEXT,
                    path_foto TEXT
                )"""
    )
    c.execute(
        "INSERT INTO pazienti (id, nome, gruppo, allergie, path_foto) VALUES (?, ?, ?, ?, ?)",
        (id_paziente, nome, gruppo, allergie, path_foto),
    )
    conn.commit()
    conn.close()


def log_accesso(id_paziente, file_img):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS log_accessi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    id_paziente TEXT,
                    file_img TEXT
                )"""
    )
    timestamp = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO log_accessi (timestamp, id_paziente, file_img) VALUES (?, ?, ?)",
        (timestamp, id_paziente, file_img),
    )
    conn.commit()
    conn.close()


def trova_match(nuova_encoding, soglia=0.6):
    for filename in os.listdir(ENCODING_FOLDER):
        known_encoding = np.load(os.path.join(ENCODING_FOLDER, filename))
        distance = face_recognition.face_distance([known_encoding], nuova_encoding)[0]
        if distance < soglia:
            return filename.replace(".npy", "")  # ritorna id paziente
    return None


def ultimo_accesso_valido(id_paziente, window_seconds=60):
    """Verifica se il paziente ha un log recente entro la finestra temporale"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "SELECT timestamp FROM log_accessi WHERE id_paziente = ? ORDER BY timestamp DESC LIMIT 1",
        (id_paziente,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return False
    ultimo_timestamp = datetime.fromisoformat(row[0])
    return datetime.utcnow() - ultimo_timestamp < timedelta(seconds=window_seconds)


# --- API ---


@app.route("/register", methods=["POST"])
def register():
    if (
        not all(k in request.form for k in ("nome", "gruppo", "allergie"))
        or "foto" not in request.files
    ):
        return jsonify({"error": "Dati mancanti"}), 400

    nome = request.form["nome"]
    gruppo = request.form["gruppo"]
    allergie = request.form["allergie"]
    foto = request.files["foto"]

    id_paziente = uuid.uuid4().hex  # id univoco

    unique_filename = f"{uuid.uuid4().hex}.jpg"
    path_foto = os.path.join(UPLOAD_FOLDER, unique_filename)
    foto.save(path_foto)

    image = face_recognition.load_image_file(path_foto)
    encodings = face_recognition.face_encodings(image)

    # Validazione encoding
    if len(encodings) != 1:
        return jsonify({"error": "Deve essere presente esattamente un volto"}), 400

    encoding = encodings[0]
    np.save(os.path.join(ENCODING_FOLDER, f"{id_paziente}.npy"), encoding)
    salva_db(id_paziente, nome, gruppo, allergie, path_foto)

    return jsonify({"success": f"Paziente registrato", "id": id_paziente}), 200


@app.route("/recognize", methods=["POST"])
def recognize():
    if "foto" not in request.files:
        return jsonify({"error": "Nessun file ricevuto"}), 400

    foto = request.files["foto"]
    unique_filename = f"{uuid.uuid4().hex}.jpg"
    path_foto = os.path.join(UPLOAD_FOLDER, unique_filename)
    foto.save(path_foto)

    image = face_recognition.load_image_file(path_foto)
    encodings = face_recognition.face_encodings(image)

    os.remove(path_foto)

    if not encodings:
        log_accesso("nessun_volto", unique_filename)
        return jsonify({"error": "Nessun volto rilevato"}), 400

    encoding = encodings[0]
    id_paziente = trova_match(encoding)

    if id_paziente:
        log_accesso(id_paziente, unique_filename)
        return jsonify({"match": True, "id": id_paziente}), 200
    else:
        log_accesso("sconosciuto", unique_filename)
        return (
            jsonify(
                {"match": False, "message": "Volto non riconosciuto con soglia >90%"}
            ),
            200,
        )


@app.route("/dati", methods=["POST"])
def dati_utente():
    id_paziente = request.form.get("id")
    if not id_paziente:
        return jsonify({"error": "ID mancante"}), 400

    # Verifica se l'utente è stato riconosciuto entro 1 minuto
    if not ultimo_accesso_valido(id_paziente, window_seconds=60):
        return (
            jsonify({"error": "Accesso negato: riconoscimento volto non recente"}),
            403,
        )

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "SELECT nome, gruppo, allergie FROM pazienti WHERE id = ?", (id_paziente,)
    )
    row = c.fetchone()
    conn.close()

    if row:
        return (
            jsonify(
                {
                    "id": id_paziente,
                    "nome": row[0],
                    "gruppo": row[1],
                    "allergie": row[2],
                }
            ),
            200,
        )
    else:
        return jsonify({"error": "Utente non trovato"}), 404


@app.route("/log", methods=["GET"])
def visualizza_log():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, id_paziente, file_img FROM log_accessi ORDER BY timestamp DESC"
    )
    righe = c.fetchall()
    conn.close()

    log = [{"timestamp": r[0], "id": r[1], "file": r[2]} for r in righe]
    return jsonify(log), 200


# --- Avvio server ---

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
