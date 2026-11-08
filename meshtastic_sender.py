
import time
from meshtastic.serial_interface import SerialInterface

radio = SerialInterface("COM7")

messages = {
    "1": "[TEST SOS] Immediate rescue assistance required.",
    "2": "[TEST MEDICAL] Urgent medical assistance needed.",
    "3": "[TEST SUPPLIES] Requesting food, water, and supplies."
}

def get_gps():
    node = radio.getMyNodeInfo()
    position = node.get("position", {})

    lat = position.get("latitude")
    lon = position.get("longitude")

    if lat is None and "latitudeI" in position:
        lat = position["latitudeI"] / 10000000

    if lon is None and "longitudeI" in position:
        lon = position["longitudeI"] / 10000000

    if lat is None or lon is None:
        return None

    if lat == 0 and lon == 0:
        return None

    timestamp = position.get("time")
    if timestamp and time.time() - timestamp > 600:
        return None

    return f"{lat:.6f}, {lon:.6f}"

try:
    while True:
        print("\n=== DISASTERMESH ===")
        print("1. SOS / Rescue")
        print("2. Medical Emergency")
        print("3. Supply Request")
        print("4. Exit")

        choice = input("\nSelect alert type: ")

        if choice == "4":
            break

        if choice in messages:
            gps = get_gps()
            message = messages[choice]

            if gps:
                print("GPS:", gps)
                confirm = input(
                    "Broadcast precise GPS on Primary channel? (y/N): "
                )
                if confirm.lower() == "y":
                    message += f" | GPS: {gps}"
                else:
                    message += " | GPS withheld"
            else:
                message += " | GPS unavailable"

            radio.sendText(message, channelIndex=1)
            print("Alert submitted:", message)
            time.sleep(2)
        else:
            print("Invalid selection.")

finally:
    radio.close()
