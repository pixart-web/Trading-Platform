"""Provision the single existing workspace owner; never accepts passwords in argv."""

from getpass import getpass
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from pocket_alpha.config import Settings
from pocket_alpha.database import build_engine
from pocket_alpha.mobile.auth import Login
from pocket_alpha.mobile.models import OperatorRecord
from pocket_alpha.mobile.security import password_hash


def main() -> None:
    username = input("Operator login (lowercase): ").strip()
    password = getpass("New password (at least 12 characters): ")
    if password != getpass("Repeat password: "):
        raise SystemExit("passwords differ")
    Login(username=username, password=SecretStr(password), device_name="provisioning")
    encoded = password_hash(password)
    engine = build_engine(Settings())
    try:
        with Session(engine) as db, db.begin():
            if db.scalar(select(OperatorRecord.user_id).limit(1)) is not None:
                raise SystemExit("workspace already provisioned; no second owner is permitted")
            db.add(
                OperatorRecord(
                    user_id=uuid4(),
                    workspace="operator",
                    username=username,
                    password_hash=encoded,
                    disabled=False,
                )
            )
    finally:
        engine.dispose()
    print("Operator provisioned. No broker permissions granted.")


if __name__ == "__main__":
    main()
