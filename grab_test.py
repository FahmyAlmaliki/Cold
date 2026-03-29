from pymodbus.client import ModbusTcpClient
import time
import subprocess
from datetime import datetime

MODBUS_IP = "10.39.122.193"
PORT = 502

START_REGISTER = 20
TOTAL_REG = 64

READING_INTERVAL = 10

def ping_modbus_ip():

    try:

        result = subprocess.run(
            ["ping", "-c", "3", "-W", "1", MODBUS_IP],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print(f"Ping to {MODBUS_IP} successful")
        else:
            print(f"Ping to {MODBUS_IP} failed (rc={result.returncode})")

    except Exception as e:
        print(f"Error running ping to {MODBUS_IP}: {e}")


def read_modbus():

    client = ModbusTcpClient(MODBUS_IP, port=PORT, timeout=3)

    if not client.connect():
        return None

    try:
        result = client.read_holding_registers(address=START_REGISTER, count=TOTAL_REG)

        if result.isError():
            return None

        regs = result.registers

        data = {}
        skip_channels = {11, 12, 13, 14}
        new_channel = 1

        for ch in range(16):
            channel = ch + 1

            if channel in skip_channels:
                continue

            base = ch * 4

            temp_raw = regs[base]
            hum_raw = regs[base + 1]

            if temp_raw > 32767:
                temp_raw -= 65536

            if hum_raw > 32767:
                hum_raw -= 65536

            data[new_channel] = {
                "temp": temp_raw / 100,
                "hum": hum_raw / 100,
                "status": regs[base + 2],
                "info": regs[base + 3],
            }
            new_channel += 1

        return data

    finally:
        client.close()


while True:

    data = read_modbus()

    if data is None:

        print("Failed read Modbus")
        ping_modbus_ip()

        print("Retry read Modbus after ping...")
        data = read_modbus()

        if data is None:
            print("Still failed read Modbus after ping")
            time.sleep(2)
            continue

    print("\n", datetime.now())

    for ch, d in data.items():

        print(
            f"CH{ch:02d}  "
            f"T:{d['temp']:.2f}C  "
            f"H:{d['hum']:.2f}%  "
            f"S:{hex(d['status'])}  I:{hex(d['info'])}"
        )

    time.sleep(READING_INTERVAL)