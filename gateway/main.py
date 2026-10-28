"""Gateway entry point.

    python3 main.py                          # read from the receiver on serial
    python3 main.py --simulate --count 100   # simulated packets, no hardware
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from pipeline import Pipeline
from simulator import SimConfig, simulate_lines
from storage import Storage

DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Farm weather station gateway")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--db", help="override storage.db_path")
    p.add_argument("--port", help="override serial.port")
    sim = p.add_argument_group("simulation")
    sim.add_argument("--simulate", action="store_true", help="use simulated packets")
    sim.add_argument("--count", type=int, default=288)
    sim.add_argument("--loss", type=float, default=0.02, help="packet loss rate")
    sim.add_argument("--duplicates", type=float, default=0.01)
    sim.add_argument("--corrupt", type=float, default=0.01)
    sim.add_argument("--reboot-at", type=int)
    sim.add_argument("--seed", type=int)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text())
    logging.basicConfig(
        level=config.get("logging", {}).get("level", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    db_path = args.db or config["storage"]["db_path"]
    mm_per_tip = float(config["rain"]["mm_per_tip"])

    with Storage(db_path) as storage:
        pipeline = Pipeline(storage, mm_per_tip)
        if args.simulate:
            lines = simulate_lines(SimConfig(
                count=args.count, loss_rate=args.loss, duplicate_rate=args.duplicates,
                corrupt_rate=args.corrupt, reboot_at=args.reboot_at, seed=args.seed,
            ))
        else:
            from serial_receiver import serial_lines
            lines = serial_lines(args.port or config["serial"]["port"],
                                 int(config["serial"]["baudrate"]))

        try:
            for line in lines:
                pipeline.handle_line(line)
        except KeyboardInterrupt:
            pass

        for station in storage.last_states():
            stats = storage.link_stats(station)
            logging.info(
                "station %d: %d received, %d missing (%.1f%% loss), %d duplicates, "
                "%d rejected lines, %.1f mm rain",
                station, stats.received, stats.missing, stats.loss_pct,
                stats.duplicates, stats.rejects, storage.total_rain_mm(station),
            )


if __name__ == "__main__":
    main()
