#!/usr/bin/env python3
"""Write the three iotauth Python configs into runtime/sst/configs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = {
    "net1.vlm_agent": "Net1.VLMAgent",
    "net1.distance_sensor": "Net1.DistanceSensor",
    "net1.vision_sensor": "Net1.VisionSensor",
}


def relative(source: Path, target: Path) -> str:
    return os.path.relpath(target, source).replace(os.sep, "/")


def render(lines: list[tuple[str, str]]) -> str:
    return (
        "# Generated runtime configuration. Contains paths but no key material.\n"
        + "\n".join(f"{key}={value}" for key, value in lines)
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime-dir", default=str(ROOT / "runtime" / "sst")
    )
    args = parser.parse_args()
    runtime = Path(args.runtime_dir).resolve()
    out = runtime / "configs"
    out.mkdir(parents=True, exist_ok=True)

    sst = yaml.safe_load((ROOT / "configs" / "sst.yaml").read_text())
    scenario = yaml.safe_load((ROOT / "configs" / "scenario.yaml").read_text())
    identities = scenario["identities"]
    auth = sst["auth"]
    links = sst["links"]
    auth_cert = runtime / "credentials" / "entities" / "auth_certs" / (
        f"Auth{auth['id']}EntityCert.pem"
    )
    key_dir = runtime / "credentials" / "entities" / "keys" / "net1"

    def credentials(entity: str) -> list[tuple[str, str]]:
        return [
            ("authInfo.pubkey.path", relative(out, auth_cert)),
            (
                "entityInfo.privkey.path",
                relative(out, key_dir / f"{PREFIXES[entity]}Key.pem"),
            ),
        ]

    def common(entity: str, purpose: str) -> list[tuple[str, str]]:
        return [
            ("entityInfo.name", entity),
            ("entityInfo.purpose", json.dumps({"group": purpose}, separators=(",", ":"))),
            ("entityInfo.number_key", "1"),
            ("authInfo.id", str(auth["id"])),
            ("sessionKey.encryptionMode", "AES_128_CBC"),
            ("HmacMode", "on"),
            *credentials(entity),
            ("auth.ip.address", str(auth["host"])),
            ("auth.port.number", str(auth["port"])),
        ]

    agent = identities["agent"]
    agent_lines = common(agent, str(links["distance"]["target_group"]))
    agent_lines += [
        ("entity.server.ip.address", str(links["distance"]["host"])),
        ("entity.server.port.number", str(links["distance"]["port"])),
        ("targetServerInfo.name_1", str(links["vision"]["source_entity"])),
        ("targetServerInfo.host_1", str(links["vision"]["host"])),
        ("targetServerInfo.port_1", str(links["vision"]["port"])),
        ("network.protocol", "TCP"),
    ]
    (out / f"{agent}.config").write_text(render(agent_lines), encoding="utf-8")

    for role in ("distance", "vision"):
        entity = identities[role]
        link = links[role]
        lines = common(entity, str(link["target_group"]))
        lines += [
            ("entity.server.ip.address", str(link["host"])),
            ("entity.server.port.number", str(link["port"])),
            ("network.protocol", "TCP"),
        ]
        (out / f"{entity}.config").write_text(render(lines), encoding="utf-8")

    (out / "entities.json").write_text(
        json.dumps(
            {
                "registered": [agent, identities["distance"], identities["vision"]],
                "unregistered": [
                    identities["rogue_distance"],
                    identities["rogue_vision"],
                ],
                "links": links,
                "source": "sst/configs/warehouse_cart.graph",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote SST entity configs to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
