# DisasterMesh

**Team:** Toby Townsley, Brando Vasquez, Matthew Lee, and Owen

DisasterMesh is an offline-first emergency communication system. It uses a LoRa mesh to send emergency reports to a local NVIDIA Jetson hub, where responders can view and manage incidents without relying on the internet or cellular service.

## Tools

- Python FastAPI backend
- React dashboard
- PostgreSQL database
- LoRa field nodes and gateway hardware
- NVIDIA Jetson Orin
- Docker and Docker Compose

## Workflow

1. Build and test the software using simulated messages on a laptop.
2. Connect the backend, database, and dashboard locally.
3. Containerize the services with Docker.
4. Deploy the local system to the Jetson.
5. Connect the LoRa gateway and field nodes.
6. Test message delivery, relays, duplicates, range, and offline operation.