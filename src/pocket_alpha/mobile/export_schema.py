"""Export the allowlisted native contract without starting any backend service."""

import json
import sys
from pathlib import Path

from pocket_alpha.config import Settings
from pocket_alpha.main import create_app
from pocket_alpha.mobile.app import create_mobile_app


def main() -> None:
    parent = create_app(Settings(environment="test"))
    schema = create_mobile_app(parent).openapi()
    schema["servers"] = [{"url": "/mobile"}]
    content = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    path = Path("docs/android/native-openapi.json")
    if "--check" in sys.argv:
        if not path.exists() or path.read_text() != content:
            raise SystemExit("native API schema drift; regenerate with mobile.export_schema")
    else:
        path.write_text(content)


if __name__ == "__main__":
    main()
