import time
from datetime import datetime, timezone
import meshtastic.serial_interface
from pubsub import pub

# Store the latest GPS coordinates for each node
latest_positions = {}


def save_position(sender, position):
    lat = position.get("latitude")
    lon = position.get("longitude")

    # Some Meshtastic packets use integer coordinates
    if lat is None and "latitudeI" in position:
        lat = position["latitudeI"] / 1e7

    if lon is None and "longitudeI" in position:
        lon = position["longitudeI"] / 1e7

    # Ignore missing or invalid GPS coordinates
    if lat is None or lon is None:
        return False

    if lat == 0 and lon == 0:
        return False

    timestamp = position.get("time")

    if timestamp:
        updated = datetime.fromtimestamp(
            timestamp, timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
    else:
        updated = "Unknown"

    latest_positions[sender] = {
        "latitude": lat,
        "longitude": lon,
        "updated": updated
    }

    return True


# Called when GPS position data arrives

def on_position(packet, interface):
    sender = packet.get("fromId", "Unknown")

    # Ignore GPS updates from other devices
    if sender != "!0436bda8":
        return

    position = packet.get("decoded", {}).get("position", {})

    if save_position(sender, position):
        gps = latest_positions[sender]

        print("\n[GPS UPDATE]")
        print("Device:", sender)
        print("Latitude:", gps["latitude"])
        print("Longitude:", gps["longitude"])
        print("Position time:", gps["updated"])

# Called when a text message arrives
def on_message(packet, interface):
    sender = packet.get("fromId", "Unknown")
    message = packet.get("decoded", {}).get("text", "")
    snr = packet.get("rxSnr", "N/A")

    print("\n========== DISASTERMESH ==========")
    print("Incoming Message!")
    print("Sender:", sender)
    print("Message:", message)
    print("Signal (SNR):", snr)

    if sender in latest_positions:
        gps = latest_positions[sender]

        print("Latitude:", gps["latitude"])
        print("Longitude:", gps["longitude"])
        print("Last GPS time:", gps["updated"])
    else:
        print("GPS: No position received yet")

    print("==================================")


# Subscribe to Meshtastic events
pub.subscribe(on_message, "meshtastic.receive.text")
pub.subscribe(on_position, "meshtastic.receive.position")

print("Connecting to DisasterMesh Gateway...")

radio = meshtastic.serial_interface.SerialInterface(
    devPath="COM9"
)

# Load positions already known by the gateway
for node_id, node in radio.nodes.items():
    position = node.get("position", {})
    save_position(node_id, position)

print("Gateway ONLINE!")
print("Waiting for SOS messages and GPS updates...")

try:
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopping gateway...")

finally:
    radio.close()