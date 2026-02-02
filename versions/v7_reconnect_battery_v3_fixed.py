"""
v7_reconnect_battery_v3_fixed.py

VERSÃO ESTABILIZADA DA V7

Objetivo:
- Conectar na Mi Band 4
- Autenticar
- Ler batimento cardíaco
- Reconectar automaticamente se perder conexão

Sem:
- bateria
- alertas
- estados
- banco
- ntfy

Correções desta versão:
- Descoberta explícita de serviços após reconexão
- Limpeza explícita de notificações BLE
- Evita loop de reconexão instável
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

# ==================================================
# CLEANUP
# ==================================================

async def cleanup_client(client):
    try:
        await client.stop_notify(UUID_AUTH)
    except Exception:
        pass

    try:
        await client.stop_notify(UUID_HR_MEAS)
    except Exception:
        pass

# ==================================================
# MONITOR
# ==================================================

async def monitor(client):
    global challenge, last_hr_time

    challenge = None
    last_hr_time = None
    connected_at = datetime.now()

    try:
        # ------------------------------
        # AUTH
        # ------------------------------
        await client.start_notify(UUID_AUTH, auth_notification)
        await client.write_gatt_char(UUID_AUTH, b"\x02\x00", response=False)

        for _ in range(20):
            if challenge:
                break
            await asyncio.sleep(0.2)

        if not challenge:
            raise Exception("Auth challenge não recebido")

        resp = encrypt(AUTH_KEY, challenge)
        await client.write_gatt_char(
            UUID_AUTH,
            b"\x03\x00" + resp,
            response=False
        )

        # ------------------------------
        # HR
        # ------------------------------
        await client.start_notify(UUID_HR_MEAS, hr_notification)
        await client.write_gatt_char(
            UUID_HR_CTRL,
            b"\x15\x01\x01",
            response=True
        )

        print("❤️ Monitoramento ativo")

        # ------------------------------
        # LOOP PRINCIPAL
        # ------------------------------
        while True:
            now = datetime.now()

            # Grace period inicial
            if now - connected_at < CONNECTION_GRACE_PERIOD:
                await asyncio.sleep(5)
                continue

            # Watchdog real
            if last_hr_time and now - last_hr_time > WATCHDOG_TIMEOUT:
                raise Exception("Watchdog: sem HR por muito tempo")

            await asyncio.sleep(10)

    finally:
        await cleanup_client(client)

# ==================================================
# SUPERVISOR
# ==================================================

async def supervisor():
    while True:
        try:
            print("🔄 Conectando à Mi Band...")
            async with BleakClient(MAC) as client:
                print("✅ Conectado")

                # 🔑 GARANTIR SERVIÇOS GATT
                await client.get_services()
                await asyncio.sleep(2)

                await monitor(client)

        except Exception as e:
            print(f"⚠️ {repr(e)}")
            print("🔁 Reconectando em alguns segundos...")
            await asyncio.sleep(RECONNECT_DELAY)

# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":
    asyncio.run(supervisor())
