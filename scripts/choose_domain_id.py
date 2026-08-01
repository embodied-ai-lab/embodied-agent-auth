#!/usr/bin/env python3
"""Select or check a ROS_DOMAIN_ID for this run.

A domain ID keeps concurrent student teams on one shared machine from seeing
each other's nodes. It is a multiplexing knob, NOT an authentication boundary:
anyone who can run a process on this machine can join any domain. This script
never implies otherwise.

Selection order:
  1. An explicit --domain-id, checked against the allowed range.
  2. $ROS_DOMAIN_ID if already set and valid.
  3. A deterministic per-user default derived from the username, so the same
     user tends to get the same domain across sessions, plus an optional probe
     that avoids a domain where lab nodes already appear to be running.

Valid range is 1..101. Zero is avoided because it is the ROS 2 default and thus
the most crowded. Values above 101 can collide with ephemeral port ranges on
some systems, which the ROS 2 documentation warns about.
"""

from __future__ import annotations

import argparse
import getpass
import os
import socket
import sys

DOMAIN_MIN = 1
DOMAIN_MAX = 101


def in_range(value: int) -> bool:
    return DOMAIN_MIN <= value <= DOMAIN_MAX


def deterministic_default(username: str) -> int:
    """A stable per-user domain ID in range. Not a security property."""
    # Sum of bytes keeps it stable and readable; modulo maps into range.
    base = sum(username.encode("utf-8")) % (DOMAIN_MAX - DOMAIN_MIN + 1)
    return DOMAIN_MIN + base


def domain_looks_busy(domain_id: int) -> bool:
    """Heuristic: is a DDS participant already discoverable on this domain?

    Best-effort only. It briefly binds the conventional Fast DDS multicast
    discovery port for the domain on loopback; if binding fails because the port
    is in use, some participant is likely present. A negative result never
    proves the domain is free, and this is only a courtesy, never a guarantee.
    """

    # Fast DDS default: discovery multicast port = 7400 + 250 * domainId.
    port = 7400 + 250 * domain_id
    if port > 65535:
        return False
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain-id", type=int, default=None, help="Use and validate this ID.")
    parser.add_argument(
        "--quiet", action="store_true", help="Print only the chosen ID (for use in scripts)."
    )
    parser.add_argument(
        "--no-probe", action="store_true", help="Skip the busy-domain heuristic."
    )
    args = parser.parse_args()

    def emit(domain_id: int, note: str) -> int:
        if args.quiet:
            print(domain_id)
        else:
            print(f"ROS_DOMAIN_ID={domain_id}  ({note})")
            print(
                "Note: a domain ID isolates lab traffic between teams. It is NOT an "
                "authentication boundary; anyone on this machine can join it.",
                file=sys.stderr,
            )
        return 0

    if args.domain_id is not None:
        if not in_range(args.domain_id):
            print(
                f"ERROR: --domain-id {args.domain_id} is outside {DOMAIN_MIN}..{DOMAIN_MAX}",
                file=sys.stderr,
            )
            return 2
        return emit(args.domain_id, "explicitly requested")

    env_value = os.environ.get("ROS_DOMAIN_ID")
    if env_value:
        try:
            parsed = int(env_value)
        except ValueError:
            print(f"ERROR: ROS_DOMAIN_ID={env_value!r} is not an integer", file=sys.stderr)
            return 2
        if not in_range(parsed):
            print(
                f"ERROR: ROS_DOMAIN_ID={parsed} is outside {DOMAIN_MIN}..{DOMAIN_MAX}",
                file=sys.stderr,
            )
            return 2
        return emit(parsed, "from the existing ROS_DOMAIN_ID")

    try:
        username = getpass.getuser()
    except Exception:
        username = "student"
    domain_id = deterministic_default(username)

    if not args.no_probe:
        for _ in range(DOMAIN_MAX):
            if not domain_looks_busy(domain_id):
                break
            domain_id = DOMAIN_MIN + (domain_id - DOMAIN_MIN + 1) % (DOMAIN_MAX - DOMAIN_MIN + 1)

    return emit(domain_id, f"per-user default for {username!r}")


if __name__ == "__main__":
    raise SystemExit(main())
