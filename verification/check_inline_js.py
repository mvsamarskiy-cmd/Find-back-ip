#!/usr/bin/env python3
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "index.html"


def inline_scripts(html):
    pattern = re.compile(r"<script(?:\s[^>]*)?>(.*?)</script>", re.IGNORECASE | re.DOTALL)
    return pattern.findall(html)


def main():
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required for JavaScript syntax validation")

    scripts = inline_scripts(TEMPLATE.read_text(encoding="utf-8"))
    if not scripts:
        raise SystemExit(f"No inline JavaScript found in {TEMPLATE}")

    with tempfile.TemporaryDirectory(prefix="namemachine-js-") as directory:
        for index, script in enumerate(scripts, start=1):
            path = Path(directory) / f"inline-{index}.js"
            path.write_text(script, encoding="utf-8")
            subprocess.run([node, "--check", str(path)], check=True)

    print(f"Validated {len(scripts)} inline script block(s) from {TEMPLATE}")


if __name__ == "__main__":
    main()

