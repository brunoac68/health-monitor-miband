"""
v7_reconnect_battery_v2.py

Correções críticas:
- Reset completo de estado a cada reconexão
- Cancelamento correto de tasks assíncronas
- Watchdog estável (sem loop infinito)
- Leitura segura da bateria (Mi Band 4)
- Reconexão BLE robusta para uso 24/7
"""

import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

import requests
from bleak import BleakClient
from Crypto.Cipher import AES

# ==================================================
# CONFIGURAÇÃO
# ==================================================

MAC = "E1:2C:9F:0B:F1:44"
AUTH_KEY = bytes.fromhex("9ef7899bbef1b557158e7c8c27e1b062")

DB_PATH = Path("health.db")

NTFY_SERVER = "https://ntfy.sh"
NTFY_TOPIC = "vo-saude-bruno"

BRADY_LIMIT = 50
TACHY_LIMIT = 110
ALERT_COOLDOWN = timedelta(minutes=10)

WATCHDOG_TIMEOUT = timedelta(minutes=2)
RECONNECT_DELAY = 10

BATTERY_RISE_TIME = timedelta(minutes=3)

# ==================================================
# UUIDs BLE (Mi Band 4)
# ==================================================

UUID_AUTH = "00000009-0000-3512-2118-0009af100700"
UUID_BATTERY = "00000006-0000-3512-2118-0009af100700"
UUID_HR_CTRL = "00002a39-0000-1000-8000-00805f9b34fb"
UUID_HR_MEAS = "00002a37-0000-1000-8000-00805f9b34fb"

# ==================================================
# VARIÁVEIS GLOBAIS (resetadas a cada conexão)
# ==================================================

challenge = None
last_hr_time = None
last_alert_time = None

wearable_state = "IN_USE"
last_battery = None
battery_rising_since = None

# ==================================================
# RESET DE ESTADO (CRÍTICO)
# ==================================================

def reset_runtime_state():
    global challenge, last_hr_time, last_alert_time
    global wearable_state, last_battery, battery_rising_since

    challenge = None
    last_hr_time = None
    last_alert_time = None

    wearable_state = "IN_USE"
    last_battery = None
    battery_rising_since = None

# ==================================================
# BANCO DE DADOS
# ==================================================

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS heart_rate (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                bpm INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wearable_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS battery_level (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level INTEGER
            )
        """)

def save_bpm(ts, bpm):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO heart_rate VALUES (NULL, ?, ?)",
            (ts, bpm)
        )

def save_event(event):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO wearable_events VALUES (NULL, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), event)
        )

def save_battery(level):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO battery_level VALUES (NULL, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), level)
        )

# ==================================================
# NTFY
# ==================================================

def send_ntfy_alert(message):
    global last_alert_time
    now = datetime.now()

    if last_alert_time and now - last_alert_time < ALERT_COOLDOWN:
        return

    last_alert_time = now

    try:
        requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=message.encode("utf-8", errors="ignore"),
            headers={"Title": "ALERTA DE SAÚDE", "Priority": "urgent"},
            timeout=5
        )
    except Exception as e:
        print(f"Erro ntfy: {e}")

    print(f"🚨 ALERTA: {message}")

# ==================================================
# AUTENTICAÇÃO
# ==================================================

def encrypt(key, msg):
    return AES.new(key, AES.MODE_ECB).encrypt(msg)

def auth_notification(_, data):
    global challenge
    if data[:3] == b'\x10\x02\x01':
        challenge = data[3:]

# ==================================================
# ESTADO / HR
# ==================================================

def set_state(new_state, message):
    global wearable_state
    if wearable_state != new_state:
        wearable_state = new_state
        print(message)
        save_event(message)

def hr_notification(_, data):
    global last_hr_time

    bpm = data[1]
    now = datetime.now()
    last_hr_time = now

    if bpm == 0:
        set_state("CHARGING", f"[{now}] 🔌 Pulseira provavelmente no carregador (BPM=0)")
        return

    print(f"[{now}] ❤️ BPM: {bpm}")
    save_bpm(now.strftime("%Y-%m-%d %H:%M:%S"), bpm)

    if wearable_state == "IN_USE":
        if bpm <= BRADY_LIMIT:
            send_ntfy_alert(f"Bradicardia (BPM={bpm})")
        elif bpm >= TACHY_LIMIT:
            send_ntfy_alert(f"Taquicardia (BPM={bpm})")

# ==================================================
# BATERIA (SEGURA)
# ==================================================

async def read_battery_safe(client):
    try:
        data = await client.read_gatt_char(UUID_BATTERY)
        if data and len(data) >= 2:
            return int(data[1])
    except Exception:
        pass
    return None

async def battery_monitor(client):
    try:
        while True:
            battery = await read_battery_safe(client)
            if battery is not None:
                print(f"[{datetime.now()}] 🔋 Bateria: {battery}%")
                save_battery(battery)
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        return

# ==================================================
# MONITORAMENTO (COM WATCHDOG)
# ==================================================

async def monitor(client):
    global challenge

    await client.start_notify(UUID_AUTH, auth_notification)
    await client.write_gatt_char(UUID_AUTH, b"\x02\x00", response=False)

    for _ in range(20):
        if challenge:
            break
        await asyncio.sleep(0.2)

    resp = encrypt(AUTH_KEY, challenge)
    await client.write_gatt_char(UUID_AUTH, b"\x03\x00" + resp, response=False)

    await client.start_notify(UUID_HR_MEAS, hr_notification)
    await client.write_gatt_char(UUID_HR_CTRL, b"\x15\x01\x01", response=True)

    battery_task = asyncio.create_task(battery_monitor(client))

    print("❤️ Monitoramento ativo")

    try:
        while True:
            if last_hr_time and datetime.now() - last_hr_time > WATCHDOG_TIMEOUT:
                raise Exception("Watchdog: conexão inativa")
            await asyncio.sleep(10)
    finally:
        battery_task.cancel()

# ==================================================
# SUPERVISOR
# ==================================================

async def supervisor():
    init_db()

    while True:
        try:
            reset_runtime_state()
            print("🔄 Conectando à Mi Band...")

            async with BleakClient(MAC) as client:
                print("✅ Conectado")
                await monitor(client)

        except Exception as e:
            print(f"⚠️ {e}")
            print("🔁 Reconectando em alguns segundos...")
            await asyncio.sleep(RECONNECT_DELAY)

# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":
    asyncio.run(supervisor())
