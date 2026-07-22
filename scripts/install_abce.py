#!/usr/bin/env python3
"""Install abcEconomics, working around a broken published setup.py.

abcEconomics 0.9.7b2 ships an sdist whose install_requires contains
"numpy >= 1.10.2p" — not a valid PEP 440 specifier — so `pip install abcEconomics`
fails at metadata generation on any modern pip. The library itself is fine.

We download the sdist, rewrite that one line, and install from source. Nothing
else about the package is touched.
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

PYPI = "https://pypi.org/pypi/abcEconomics/json"


def main() -> int:
    try:
        import abcEconomics  # noqa: F401
        print("abcEconomics already installed.")
        return 0
    except Exception:
        pass

    # --no-build-isolation (below) means pip will NOT set up an isolated
    # build environment with its own setuptools — it expects setuptools to
    # already be importable in this interpreter. Some base Python images
    # (Render's included) don't ship it by default, so the build fails with
    # "ModuleNotFoundError: No module named 'setuptools'" if we skip this.
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
                           "--upgrade", "setuptools", "wheel"])

    import json
    with urllib.request.urlopen(PYPI, timeout=60) as r:
        meta = json.load(r)

    sdist = next(u for u in meta["urls"] if u["packagetype"] == "sdist")
    print(f"Downloading {sdist['filename']} …")
    with urllib.request.urlopen(sdist["url"], timeout=120) as r:
        blob = r.read()

    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
            tar.extractall(tmp)
        root = next(Path(tmp).iterdir())
        setup = root / "setup.py"
        src = setup.read_text()

        # The broken pin isn't in the initial `install_requires = [...]` — it's
        # appended later via `install_requires += [...]` inside a platform
        # check. Neutralize both the assignment and every += append, so the
        # final list passed to setup() is just ['future'] regardless of what
        # those append lines would otherwise have added.
        patched = re.sub(
            r"install_requires\s*=\s*\[[^\]]*\]",
            "install_requires = ['future']",
            src,
            count=1,
        )
        patched, n_appends = re.subn(
            r"install_requires\s*\+=\s*\[[^\]]*\]",
            "pass",
            patched,
        )
        if patched == src:
            print("Could not find install_requires — installing unpatched.", file=sys.stderr)
        setup.write_text(patched)
        print(f"Patched setup.py (invalid pin 'numpy >= 1.10.2p' removed, "
              f"{n_appends} append line(s) neutralized).")

        cmd = [sys.executable, "-m", "pip", "install", ".", "--no-build-isolation"]
        return subprocess.call(cmd, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
