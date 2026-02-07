"""
v8_alerts.py

Baseado na v7_reconnect_stable

Adiciona:
- Alertas de bradicardia
- Alertas de taquicardia
- Detecção de ausência REAL de dados
- Cooldown de alertas

Sem:
- banco
- ntfy
- estados complexos

Objetivo:
Alertas confiáveis sem falso positivo.
"""

import asyncio
from datetime import datetime, timedelta

from bleak import BleakClient
from Crypto.Cipher import AES

# ==================================================
# CONFIG
# ==================================================

MAC = "E1:2C:9F:0B:F1:44"
AUTH_KEY = bytes.fromhex("9ef7899bbef1b557158e7c8c27e1b062")

RECONNECT_DELAY = 10
WATCHDOG_TIMEOUT = timedelta(minutes=2)
CONNECTION_GRACE_PERIOD = timedelta(seconds=40)

# Alertas
BRADY_LIMIT = 50
TACHY_LIMIT = 110
NO_DATA_TIMEOUT = timedelta(minutes=5)
ALERT_COOLDOWN = timedelta(minutes=10)

# ==================================================
# UUIDs Mi Band 4
# ==================================================

UUID_AUTH = "00000009-0000-3512-2118-0009af100700"
UUID_HR_CTRL = "00002a39-0000-1000-8000-00805f9b34fb"
UUID_HR_MEAS = "00002a37-0000-1000-8000-00805f9b34fb"

# ==================================================
# ESTADO RUNTIME
# ==================================================

challenge = None
last_hr_time = None
last_alert_time = None

# ==================================================
# AUTH
# ==================================================

def encrypt(key, msg):
    return AES.new(key, AES.MODE_ECB).encrypt(msg)

def auth_notification(_, data):
    global challenge
    if data[:3] == b'\x10\x02\x01':
        challenge = data[3:]

# ==================================================
# ALERTAS
# ==================================================

def send_alert(message):
    global last_alert_time
    now = datetime.now()

    if last_alert_time and now - last_alert_time < ALERT_COOLDOWN:
        return

    last_alert_time = now
    print(f"🚨 ALERTA: {message}")

# ==================================================
# HR
# ==================================================

def hr_notification(_, data):
    global last_hr_time

    if len(data) < 2:
        return

    bpm = data[1]
    now = datetime.now()
    last_hr_time = now

    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] ❤️ BPM: {bpm}")

    # Alertas de BPM
    if bpm <= BRADY_LIMIT:
        send_alert(f"Bradicardia detectada (BPM={bpm})")
    elif bpm >= TACHY_LIMIT:
        send_alert(f"Taquicardia detectada (BPM={bpm})")

# ==================================================
# MONITOR
# ==================================================

async def monitor(client):
    global challenge, last_hr_time

    challenge = None
    last_hr_time = None
    connected_at = datetime.now()

    # Auth
    await client.start_notify(UUID_AUTH, auth_notification)
    await client.write_gatt_char(UUID_AUTH, b"\x02\x00", response=False)

    for _ in range(20):
        if challenge:
            break
        await asyncio.sleep(0.2)

    if not challenge:
        raise Exception("Auth challenge não recebido")

    resp = encrypt(AUTH_KEY, challenge)
    await client.write_gatt_char(UUID_AUTH, b"\x03\x00" + resp, response=False)

    # HR
    await client.start_notify(UUID_HR_MEAS, hr_notification)
    await client.write_gatt_char(UUID_HR_CTRL, b"\x15\x01\x01", response=True)

    print("❤️ Monitoramento ativo")

    # Loop principal
    while True:
        now = datetime.now()

        # Grace period após conexão
        if now - connected_at < CONNECTION_GRACE_PERIOD:
            await asyncio.sleep(5)
            continue

        # Watchdog de ausência REAL de dados
        if last_hr_time and now - last_hr_time > NO_DATA_TIMEOUT:
            raise Exception("No HR data timeout")

        await asyncio.sleep(10)

# ==================================================
# SUPERVISOR
# ==================================================

async def supervisor():
    while True:
        try:
            print("🔄 Conectando à Mi Band...")
            async with BleakClient(MAC) as client:
                print("✅ Conectado")
                await monitor(client)

        except Exception as e:
            print(f"⚠️ Desconectado: {e}")
            print("🔁 Reconectando em alguns segundos...")
            await asyncio.sleep(RECONNECT_DELAY)

# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":
    asyncio.run(supervisor())
