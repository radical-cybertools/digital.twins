"""MkDocs hook: render the pre-release dependency pins from deploy/install.sh.

Until rhapsody, asyncflow and ROSE are released together with this
package, a working install needs the exact dependency versions and
commits `deploy/install.sh` pins.  The page carries the marker
`<!-- stack-pins -->`; this hook replaces it with those pins, so the
docs and the installer cannot disagree on the dependencies.  The package
itself comes from the `devel` branch: the installer's own `REF` pins a
deployment commit, not what a new user should start from.  Remove the
hook and the marker once the stack installs from PyPI.
"""

import re

from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[2] / "deploy" / "install.sh"
MARKER = "<!-- stack-pins -->"

# installer variable -> what the docs call it
PINS = {"PYTHON": "Python", "ASYNCFLOW": "radical.asyncflow",
        "RHAPSODY": "rhapsody", "ORBIT": "radical.orbit", "ROSE": "ROSE"}


def read_pins(text: str) -> dict:
    pins = {}
    for var in PINS:
        match = re.search(rf'^{var}="([^"]+)"', text, re.MULTILINE)
        if not match:
            raise ValueError(f"{INSTALLER}: no {var}= pin found")
        pins[var] = match.group(1)

    # PYTHON="${DT_PYTHON:-python3.12}" -> python3.12
    pins["PYTHON"] = re.sub(r"^\$\{[A-Z_]+:-(.*)\}$", r"\1", pins["PYTHON"])

    return pins


def render(pins: dict) -> str:
    deps = " \\\n    ".join(f'"{pins[v]}"' for v in PINS if v != "PYTHON")

    return (
        f"```sh\n"
        f"{pins['PYTHON']} -m venv ve && . ve/bin/activate\n"
        f"pip install \\\n    {deps}\n"
        f'pip install "radical.doppelganger[service,learn] @ '
        f'git+https://github.com/radical-cybertools/digital.twins@devel"\n'
        f"```\n"
    )


def on_page_markdown(markdown, page, **kwargs):
    if MARKER not in markdown:
        return markdown

    return markdown.replace(MARKER, render(read_pins(INSTALLER.read_text())))
