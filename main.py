#!/usr/bin/python3
import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eq3btsmart.thermostat import (
    Eq3CommandException,
    Eq3ConnectionException,
    Eq3StateException,
    Eq3TimeoutException,
    Thermostat,
)

POLL_INTERVAL_SECONDS = 60
DATA_FILE = Path(__file__).parent / "data.json"


@dataclass
class ThermostatConfig:
    id: str
    room_name: str
    label: str
    address: str
    is_dummy: bool


def load_thermostats() -> list[ThermostatConfig]:
    with DATA_FILE.open() as fp:
        data: dict[str, Any] = json.load(fp)

    rooms_by_id = {room["id"]: room["name"] for room in data.get("rooms", [])}
    thermostats: list[ThermostatConfig] = []

    for entry in data.get("thermostats", []):
        address = entry.get("address", "")
        is_dummy = address.upper().endswith("XX:XX:XX")
        thermostats.append(
            ThermostatConfig(
                id=entry.get("id", ""),
                room_name=rooms_by_id.get(entry.get("roomId", ""), "Unbekannt"),
                label=entry.get("label", entry.get("id", "")),
                address=address,
                is_dummy=is_dummy,
            )
        )

    return thermostats


async def poll_thermostat(config: ThermostatConfig) -> None:
    if config.is_dummy:
        while True:
            logging.info(
                "Dummy-Thermostat %s (%s) in Raum %s – uebersprungen",
                config.label,
                config.address,
                config.room_name,
            )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    thermostat = Thermostat(config.address)

    while True:
        try:
            await thermostat.async_connect()
            status = await thermostat.async_get_status()
            logging.info(
                "%s (%s) [%s]: %.1f°C Ziel, Ventil %d%%, Modus %s, Fenster=%s, Boost=%s, Batterie_niedrig=%s",
                config.label,
                config.address,
                config.room_name,
                status.target_temperature,
                status.valve,
                status.operation_mode.name,
                status.is_window_open,
                status.is_boost,
                status.is_low_battery,
            )
        except (Eq3ConnectionException, Eq3TimeoutException, Eq3CommandException, Eq3StateException) as ex:
            logging.error(
                "Thermostat %s (%s) konnte nicht abgefragt werden: %s",
                config.label,
                config.address,
                ex,
            )
        except Exception:
            logging.exception(
                "Unerwarteter Fehler beim Abfragen von %s (%s)",
                config.label,
                config.address,
            )
        finally:
            try:
                if thermostat.is_connected:
                    await thermostat.async_disconnect()
            except Exception:
                logging.exception(
                    "Verbindung zu %s (%s) konnte nicht sauber getrennt werden",
                    config.label,
                    config.address,
                )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    configs = load_thermostats()
    if not configs:
        logging.error("Keine Thermostate in %s gefunden", DATA_FILE)
        return

    tasks = [asyncio.create_task(poll_thermostat(cfg)) for cfg in configs]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
