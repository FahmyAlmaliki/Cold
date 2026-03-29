from pymodbus.client import ModbusTcpClient
import struct
import time

# ===============================
# KONFIGURASI
# ===============================
IP = "10.39.123.61"
PORT = 502
SLAVE = 1

INTERVAL = 2


# ===============================
# KONVERSI REGISTER → FLOAT
# ===============================
def to_float(regs):
    raw = struct.pack(">HH", regs[0], regs[1])
    return struct.unpack(">f", raw)[0]


# ===============================
# REGISTER MAP PM2200
# ===============================
REGISTERS = {

    # Voltage Line-Neutral
    "Voltage_L1": 3027,
    "Voltage_L2": 3029,
    "Voltage_L3": 3031,

    # Current
    "Current_L1": 3001,
    "Current_L2": 3003,
    "Current_L3": 3005,

    # Power
    "Power_Total": 3059,

    # Power Factor
    "PF_Total": 3083,

    # Frequency
    "Frequency": 3109
}


# ===============================
# READ REGISTER
# ===============================
def read_value(client, addr):

    r = client.read_holding_registers(addr,2,slave=SLAVE)

    time.sleep(0.05)   # delay 50 ms

    if r.isError():
        return None

    return to_float(r.registers)


# ===============================
# MAIN
# ===============================
def main():

    client = ModbusTcpClient(IP, port=PORT)

    print("Connecting to meter...")

    if not client.connect():
        print("Gagal connect ke meter")
        return

    print("Connected\n")

    while True:

        print("===================================")

        for name, addr in REGISTERS.items():

            val = read_value(client, addr)

            if val is None:
                print(f"{name:15} : ERROR")
            else:
                print(f"{name:15} : {val:.3f}")

        print("===================================\n")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()