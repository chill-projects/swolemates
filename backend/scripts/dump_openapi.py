#!/usr/bin/env python
"""Write the OpenAPI schema to stdout without booting a server.

`make types` and CI both use this. Importing the app is enough — no database connection
is opened at import time — so the generated-client drift check needs no services.

Run with `python -m scripts.dump_openapi` from backend/ so that `app` is importable.
"""

import json
import sys

from app.main import app


def main() -> None:
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
