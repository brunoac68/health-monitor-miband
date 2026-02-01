import asyncio
from bleak import BleakClient
from Crypto.Cipher import AES

MAC = "E1:2C:9F:0B:F1:44"
AUTH_KEY = bytes.fromhex("9ef7899bbef1b557158e7c8c27e1b062")

UUID_AUTH = "00000009-0000-3512-2118-0009af100700"
#UUID_AUTH_CCCD = "00002902-0000-1000-8000-00805f9b34fb"

UUID_HR_CTRL = "00002a39-0000-1000-8000-00805f9b34fb"
UUID_HR_MEAS = "00002a37-0000-1000-8000-00805f9b34fb"

challenge = None

def encrypt(key, msg):
    return AES.new(key, AES.MODE_ECB).encrypt(msg)

def auth_notification(_, data):
    global challenge
    if data[:3] == b'\x10\x02\x01':
        challenge = data[3:]

def hr_notification(_, data):
    if len(data) >= 2:
        bpm = data[1]
        print(f"❤️ BPM: {bpm}")

async def main():
    global challenge

    async with BleakClient(MAC) as client:
        print("[✓] Conectado")

        # Auth notifications
        await client.start_notify(UUID_AUTH, auth_notification)
#        await client.write_gatt_char(UUID_AUTH_CCCD, b'\x01\x00', response=True)

        print("[*] Solicitando challenge...")
        await client.write_gatt_char(UUID_AUTH, b'\x02\x00', response=False)

        for _ in range(20):
            if challenge:
                break
            await asyncio.sleep(0.2)

        if not challenge:
            raise Exception("Challenge não recebido")

        print("[*] Respondendo challenge...")
        resp = encrypt(AUTH_KEY, challenge)
        await client.write_gatt_char(UUID_AUTH, b'\x03\x00' + resp, response=False)

        print("[✓] Autenticado")

        # Heart rate notifications
        await client.start_notify(UUID_HR_MEAS, hr_notification)

        # Start heart rate measurement
        await client.write_gatt_char(UUID_HR_CTRL, b'\x15\x01\x01', response=True)

        print("[*] Medindo batimento...")
        while True:
            await asyncio.sleep(5)

asyncio.run(main())
