"""
miband4_test_suite.py

Bateria de testes completa para Mi Band 4
Descobre e testa tudo que for possível via BLE

⚠️ Script de diagnóstico — NÃO usar em produção
"""

import asyncio
from datetime import datetime

from bleak import BleakClient
from Crypto.Cipher import AES

# ==================================================
# CONFIG
# ==================================================

MAC = "E1:2C:9F:0B:F1:44"
AUTH_KEY = bytes.fromhex("9ef7899bbef1b557158e7c8c27e1b062")

# UUIDs conhecidos
UUID_AUTH = "00000009-0000-3512-2118-0009af100700"
UUID_HR_CTRL = "00002a39-0000-1000-8000-00805f9b34fb"
UUID_HR_MEAS = "00002a37-0000-1000-8000-00805f9b34fb"
UUID_BATTERY_STD = "00002a19-0000-1000-8000-00805f9b34fb"
UUID_BATTERY_XIAOMI = "00000006-0000-3512-2118-0009af100700"

# ==================================================
# HELPERS
# ==================================================

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def encrypt(key, msg):
    return AES.new(key, AES.MODE_ECB).encrypt(msg)

# ==================================================
# AUTH
# ==================================================

challenge = None

def auth_notification(_, data):
    global challenge
    if data[:3] == b'\x10\x02\x01':
        challenge = data[3:]

# ==================================================
# NOTIFY CALLBACK
# ==================================================

def generic_notify(uuid):
    def handler(_, data):
        log(f"🔔 Notify {uuid}: {data.hex()}")
    return handler

# ==================================================
# TEST SUITE
# ==================================================

async def run_tests():
    global challenge

    log("🔄 Conectando à Mi Band 4...")
    async with BleakClient(MAC) as client:
        log("✅ Conectado")

        # -------------------------------
        # AUTENTICAÇÃO
        # -------------------------------
        log("🔐 Autenticando...")
        await client.start_notify(UUID_AUTH, auth_notification)
        await client.write_gatt_char(UUID_AUTH, b"\x02\x00", response=False)

        for _ in range(20):
            if challenge:
                break
            await asyncio.sleep(0.2)

        if not challenge:
            log("❌ Challenge não recebido")
            return

        resp = encrypt(AUTH_KEY, challenge)
        await client.write_gatt_char(UUID_AUTH, b"\x03\x00" + resp, response=False)
        log("🔓 Autenticado")

        # -------------------------------
        # DESCOBERTA DE SERVIÇOS
        # -------------------------------
        log("🔍 Descobrindo serviços e characteristics...")
        for service in client.services:
            log(f"🧩 Serviço: {service.uuid}")
            for char in service.characteristics:
                props = ",".join(char.properties)
                log(f"   └─ 📌 Char: {char.uuid} [{props}]")

        # -------------------------------
        # LEITURA DE CARACTERÍSTICAS
        # -------------------------------
        log("📖 Tentando leitura de characteristics...")
        for service in client.services:
            for char in service.characteristics:
                if "read" in char.properties:
                    try:
                        data = await client.read_gatt_char(char.uuid)
                        log(f"📖 Read {char.uuid}: {data.hex()}")
                    except Exception as e:
                        log(f"⚠️ Read falhou {char.uuid}: {e}")

        # -------------------------------
        # NOTIFICAÇÕES
        # -------------------------------
        log("🔔 Tentando ativar notificações...")
        for service in client.services:
            for char in service.characteristics:
                if "notify" in char.properties:
                    try:
                        await client.start_notify(char.uuid, generic_notify(char.uuid))
                        log(f"🔔 Notify ativado: {char.uuid}")
                    except Exception as e:
                        log(f"⚠️ Notify falhou {char.uuid}: {e}")

        # -------------------------------
        # TESTE HR
        # -------------------------------
        log("❤️ Testando batimento cardíaco...")
        try:
            await client.start_notify(UUID_HR_MEAS, generic_notify("HR"))
            await client.write_gatt_char(UUID_HR_CTRL, b"\x15\x01\x01", response=True)
            log("❤️ HR iniciado")
        except Exception as e:
            log(f"⚠️ HR falhou: {e}")

        # -------------------------------
        # TESTE BATERIA
        # -------------------------------
        log("🔋 Testando bateria...")
        for uuid in [UUID_BATTERY_STD, UUID_BATTERY_XIAOMI]:
            try:
                data = await client.read_gatt_char(uuid)
                log(f"🔋 Bateria {uuid}: {data.hex()}")
            except Exception as e:
                log(f"⚠️ Bateria {uuid} falhou: {e}")

        # -------------------------------
        # MANTER VIVO
        # -------------------------------
        log("⏳ Coletando dados por 2 minutos...")
        await asyncio.sleep(120)

        log("🛑 Encerrando teste")

# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":
    asyncio.run(run_tests())
