"""Validate against Render's public schema without calling Render's account API."""
import json
from pathlib import Path
from urllib.request import urlopen

import jsonschema
import yaml

if __name__ == "__main__":
    with urlopen("https://render.com/schema/render.yaml.json", timeout=30) as response:
        schema = json.load(response)
    document = yaml.safe_load(Path("render.yaml").read_text())
    jsonschema.validate(document, schema)
    print("render.yaml: schema valid")
