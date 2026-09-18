"""Explicit local one-shot private observation; never starts with the application."""

import argparse
import json
import os
from pathlib import Path

from pocket_alpha.broker_readonly.binance import BinanceSpotReader, Credentials, ReadOnlyError
from pocket_alpha.broker_readonly.models import LocalState, ObservationRequest, reconcile
from pocket_alpha.common.clock import SystemClock


def main() -> int:
    parser = argparse.ArgumentParser(description="Binance Spot private read-only observation")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--local-state", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        # Reject an existing receipt before network access. O_EXCL also prevents overwrite races.
        if args.output.exists():
            raise ReadOnlyError("OUTPUT_ALREADY_EXISTS")
        request = ObservationRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
        local = (
            LocalState.model_validate_json(args.local_state.read_text(encoding="utf-8"))
            if args.local_state
            else None
        )
        observation = BinanceSpotReader(Credentials()).observe(
            request.instruments, request.history_scope
        )
        result = reconcile(observation, local, now=SystemClock().now())
        receipt = (
            json.dumps(
                {
                    "observation": observation.model_dump(mode="json"),
                    "reconciliation": result.model_dump(mode="json"),
                },
                indent=2,
            )
            + "\n"
        )
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(receipt)
        print("READ_ONLY_MATCHED" if result.read_only_ready else "READ_ONLY_BLOCKED")
        return 0 if result.read_only_ready else 2
    except ReadOnlyError as error:
        print(str(error))
        return 2
    except Exception:
        # Pydantic validation errors may echo secret environment inputs. Never print them.
        print("READ_ONLY_CONFIGURATION_OR_IO_FAILED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
