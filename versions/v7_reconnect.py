"""
v7_reconnect.py

- Monitoramento contínuo 24/7
- Reconexão automática BLE
- Tolerante a perda prolongada de conexão
- Inclui:
  - HR
  - Alertas
  - Estado do wearable
  - Carregamento
  - SQLite
  - ntfy
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
NO_DATA_LIMIT = timedelta(minutes=5)
ALERT_COOLDOWN = timedelta(minutes=10)

BATTERY_RISE_TIME = timedelta(minutes=3)
STARTUP_SAMPLES = 3
WATCHDOG_TIMEOUT = timedelta(minutes=2)

RECONNECT_DELAY = 10  # segundos

# ==================================================
# UUIDs BLE
# ==================================================

UUID_AUTH = "00000009-0000-3512-2118-0009af100700"
UUID_HR_CTRL = "00002a39-0000-1000-8000-00805f9b34fb"
UUID_HR_MEAS = "00002a37-0000-1000-8000-00805f9b34fb"
UUID_BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"

# ==================================================
# VARIÁVEIS GLOBAIS
# ==================================================

challenge = None
last_hr_time = None
last_alert_time = None

wearable_state = "IN_USE"
last_battery = None
battery_rising_since = None
startup_battery_samples = []

# ==================================================
# BANCO DE DADOS
# ==================================================

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wearable_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

def save_bpm(ts, bpm):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO heart_rate (timestamp, bpm) VALUES (?, ?)",
            (ts, bpm)
        )

def save_event(event):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO wearable_events (timestamp, event) VALUES (?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), event)
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
            headers={"Title": "ALERTA DE SAUDE", "Priority": "urgent"},
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
# ESTADO DO WEARABLE
# ==================================================

def set_state(new_state, message):
    global wearable_state
    if wearable_state != new_state:
        wearable_state = new_state
        print(message)
        save_event(message)

def update_wearable_state(battery, hr_recent):
    global last_battery, battery_rising_since, startup_battery_samples

    now = datetime.now()

    if len(startup_battery_samples) < STARTUP_SAMPLES and battery is not None:
        startup_battery_samples.append(battery)
        if startup_battery_samples[-1] > startup_battery_samples[0]:
            set_state("CHARGING", f"[{now}] 🔌 Pulseira já estava no carregador ao iniciar")
            return

    if battery is not None and last_battery is not None:
        if battery > last_battery:
            battery_rising_since = battery_rising_since or now
        else:
            battery_rising_since = None

    last_battery = battery

    if battery_rising_since and now - battery_rising_since >= BATTERY_RISE_TIME:
        set_state("CHARGING", f"[{now}] 🔌 Pulseira colocada para carregar")
        return

    if wearable_state == "CHARGING" and hr_recent:
        battery_rising_since = None
        set_state("IN_USE", f"[{now}] ⌚ Pulseira retirada do carregador")

# ==================================================
# HR
# ==================================================

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
# BATERIA
# ==================================================

async def battery_monitor(client):
    while True:
        battery = await client.read_gatt_char(UUID_BATTERY_LEVEL)
        hr_recent = last_hr_time and (datetime.now() - last_hr_time) < timedelta(seconds=30)
        update_wearable_state(battery[0], hr_recent)
        await asyncio.sleep(60)

# ==================================================
# MONITORAMENTO
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

    asyncio.create_task(battery_monitor(client))

    print("❤️ Monitoramento ativo")

    while True:
        if last_hr_time and datetime.now() - last_hr_time > WATCHDOG_TIMEOUT:
            raise Exception("Watchdog: conexão inativa")
        await asyncio.sleep(10)

# ==================================================
# SUPERVISOR
# ==================================================

async def supervisor():
    init_db()

    while True:
        try:
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
