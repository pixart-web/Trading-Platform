"""Explicit local native READ-only qualification; no order operation exists in this CLI."""

import argparse
import json
import os
from pathlib import Path

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.spot_execution.binance import BinanceSpotBroker, NativeError
from pocket_alpha.spot_execution.models import SpotPolicy


def main() -> int:
    parser = argparse.ArgumentParser(description="Binance spot read-only protocol qualification")
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.output.exists():
            print("OUTPUT_ALREADY_EXISTS")
            return 2
        policy = SpotPolicy.model_validate_json(args.policy.read_text(encoding="utf-8"))
        result = BinanceSpotBroker(policy).qualify()
        receipt = {
            "schema_version": "spot-native-qualification-1.0.0",
            "recorded_at": SystemClock().now().isoformat(),
            "result": result,
        }
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(receipt, indent=2) + "\n")
        print("NATIVE_READ_ONLY_QUALIFIED")
        return 0
    except NativeError as error:
        print(str(error))
        return 2
    except Exception:
        print("NATIVE_CONFIGURATION_OR_IO_FAILED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
