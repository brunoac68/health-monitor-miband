import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime

from bleak import BleakClient
from Crypto.Cipher import AES

# =========================
# CONFIGURAÇÃO
# =========================

MAC = "E1:2C:9F:0B:F1:44"
AUTH_KEY = bytes.fromhex("9ef7899bbef1b557158e7c8c27e1b062")

UUID_AUTH = "00000009-0000-3512-2118-0009af100700"
UUID_HR_CTRL = "00002a39-0000-1000-8000-00805f9b34fb"
UUID_HR_MEAS = "00002a37-0000-1000-8000-00805f9b34fb"

DB_PATH = Path("health.db")

challenge = None

# =========================
# CRIPTOGRAFIA
# =========================

def encrypt(key, msg):
    return AES.new(key, AES.MODE_ECB).encrypt(msg)

# =========================
# BANCO DE DADOS
# =========================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS heart_rate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            bpm INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_bpm(timestamp, bpm):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO heart_rate (timestamp, bpm) VALUES (?, ?)",
        (timestamp, bpm)
    )
    conn.commit()
    conn.close()

# =========================
# BLE CALLBACKS
# =========================

def auth_notification(_, data):
    global challenge
    if data[:3] == b'\x10\x02\x01':
        challenge = data[3:]

def hr_notification(_, data):
    if len(data) >= 2:
        bpm = data[1]
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] ❤️ BPM: {bpm}")
        save_bpm(ts, bpm)

# =========================
# LOOP PRINCIPAL (ROBUSTO)
# =========================

async def monitor_loop():
    global challenge
    init_db()

    while True:
        try:
            print("🔄 Tentando conectar à Mi Band...")
            async with BleakClient(MAC) as client:
                print("✅ Conectado")

                challenge = None

                # Autenticação
                await client.start_notify(UUID_AUTH, auth_notification)
                await client.write_gatt_char(UUID_AUTH, b'\x02\x00', response=False)

                for _ in range(20):
                    if challenge:
                        break
                    await asyncio.sleep(0.2)

                if not challenge:
                    raise Exception("Challenge não recebido")

                resp = encrypt(AUTH_KEY, challenge)
                await client.write_gatt_char(
                    UUID_AUTH,
                    b'\x03\x00' + resp,
                    response=False
                )

                print("🔓 Autenticado")

                # Batimento
                await client.start_notify(UUID_HR_MEAS, hr_notification)
                await client.write_gatt_char(
                    UUID_HR_CTRL,
                    b'\x15\x01\x01',
                    response=False
                )

                print("❤️ Monitoramento iniciado")

                while True:
                    await asyncio.sleep(5)

        except Exception as e:
            print(f"⚠️ Erro: {e}")
            print("⏳ Tentando reconectar em 10 segundos...")
            await asyncio.sleep(10)

# =========================
# ENTRY POINT
# =========================

asyncio.run(monitor_loop())
