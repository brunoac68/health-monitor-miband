"""
v6_state_init.py

Extensão da v6_state:
- Corrige detecção de estado inicial no startup
- Identifica quando o script inicia com a pulseira já no carregador
- Mantém toda a lógica de estado, alertas e persistência

Estados:
- IN_USE
- CHARGING
- REMOVED
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

# Alertas
BRADY_LIMIT = 50
TACHY_LIMIT = 110
NO_DATA_LIMIT = timedelta(minutes=5)
ALERT_COOLDOWN = timedelta(minutes=10)

# Estado
BATTERY_RISE_TIME = timedelta(minutes=3)

# ==================================================
# UUIDs BLE (Mi Band 4)
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
initial_state_checked = False

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
    conn.commit()
    conn.close()

def save_bpm(ts, bpm):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO heart_rate (timestamp, bpm) VALUES (?, ?)",
        (ts, bpm)
    )
    conn.commit()
    conn.close()

# ==================================================
# NTFY
# ==================================================

def send_ntfy_alert(message):
    global last_alert_time

    now = datetime.now()
    if last_alert_time and now - last_alert_time < ALERT_COOLDOWN:
        return

    last_alert_time = now

    body = f"{message}\n{now.strftime('%Y-%m-%d %H:%M:%S')}"

    try:
        requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=body.encode("utf-8", errors="ignore"),
            headers={
                "Title": "ALERTA DE SAUDE",
                "Priority": "urgent",
                "Tags": "rotating_light,heart"
            },
            timeout=5
        )
    except Exception as e:
        print(f"Erro ntfy: {e}")

    print(f"🚨 ALERTA ENVIADO: {message}")

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

def update_wearable_state(battery, hr_recent):
    global wearable_state, last_battery, battery_rising_since, initial_state_checked

    now = datetime.now()

    # 🟡 Detectar estado inicial no startup
    if not initial_state_checked:
        initial_state_checked = True

        if not hr_recent and battery is not None:
            wearable_state = "CHARGING"
            last_battery = battery
            print(f"[{now}] 🔌 Pulseira já estava no carregador ao iniciar")
            return

    # 🔋 Monitorar subida da bateria
    if battery is not None and last_battery is not None:
        if battery > last_battery:
            if not battery_rising_since:
                battery_rising_since = now
        else:
            battery_rising_since = None

    last_battery = battery

    # 🔌 Detectar carregamento normal
    if battery_rising_since and now - battery_rising_since >= BATTERY_RISE_TIME:
        if wearable_state != "CHARGING":
            wearable_state = "CHARGING"
            print(f"[{now}] 🔌 Pulseira colocada para carregar")
        return

    # ⌚ Retirada do carregador
    if wearable_state == "CHARGING" and hr_recent:
        wearable_state = "IN_USE"
        battery_rising_since = None
        print(f"[{now}] ⌚ Pulseira retirada do carregador")
        return

    # ❌ Fora do pulso
    if wearable_state == "IN_USE" and not hr_recent:
        wearable_state = "REMOVED"

# ==================================================
# NOTIFICAÇÃO DE HR
# ==================================================

def hr_notification(_, data):
    global last_hr_time

    if len(data) >= 2:
        bpm = data[1]
        now = datetime.now()
        last_hr_time = now

        print(f"[{now}] ❤️ BPM: {bpm}")
        save_bpm(now.strftime("%Y-%m-%d %H:%M:%S"), bpm)

        if wearable_state == "IN_USE":
            check_alerts(bpm)

# ==================================================
# ALERTAS
# ==================================================

def check_alerts(bpm):
    if bpm <= BRADY_LIMIT:
        send_ntfy_alert(f"Bradicardia detectada (BPM={bpm})")
    elif bpm >= TACHY_LIMIT:
        send_ntfy_alert(f"Taquicardia detectada (BPM={bpm})")

def check_no_data():
    if wearable_state != "IN_USE":
        return

    if last_hr_time and datetime.now() - last_hr_time > NO_DATA_LIMIT:
        send_ntfy_alert("Sem dados de batimento por mais de 5 minutos")

# ==================================================
# BATERIA
# ==================================================

async def read_battery(client):
    try:
        data = await client.read_gatt_char(UUID_BATTERY_LEVEL)
        return int(data[0])
    except Exception:
        return None

async def battery_monitor(client):
    while True:
        battery = await read_battery(client)

        hr_recent = (
            last_hr_time
            and (datetime.now() - last_hr_time) < timedelta(seconds=30)
        )

        update_wearable_state(battery, hr_recent)
        await asyncio.sleep(60)

# ==================================================
# MAIN
# ==================================================

async def main():
    init_db()

    print("🔄 Conectando à Mi Band...")
    async with BleakClient(MAC) as client:
        print("✅ Conectado")

        await client.start_notify(UUID_AUTH, auth_notification)
        await client.write_gatt_char(UUID_AUTH, b"\x02\x00", response=False)

        for _ in range(20):
            if challenge:
                break
            await asyncio.sleep(0.2)

        resp = encrypt(AUTH_KEY, challenge)
        await client.write_gatt_char(UUID_AUTH, b"\x03\x00" + resp, response=False)

        print("🔓 Autenticado")

        await client.start_notify(UUID_HR_MEAS, hr_notification)
        await client.write_gatt_char(UUID_HR_CTRL, b"\x15\x01\x01", response=True)

        asyncio.create_task(battery_monitor(client))

        print("❤️ Monitoramento iniciado")

        while True:
            check_no_data()
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
