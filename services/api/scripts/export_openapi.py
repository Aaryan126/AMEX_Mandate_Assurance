from __future__ import annotations

import json

from app.main import app

print(json.dumps(app.openapi()))
