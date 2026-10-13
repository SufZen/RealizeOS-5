"""Regenerate dashboard/src/design-system/tokens.json from the CSS tokens.

The CSS files are the source of truth; the JSON (Style Dictionary format) is
for consumers that can't read CSS, such as the marketing site build or native
apps. Run after editing tokens.css or motion.css:

    python scripts/build_design_tokens.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DS = Path(__file__).resolve().parent.parent / "dashboard" / "src" / "design-system"


def _block(src: str, selector: str) -> str:
    """Return the body of the first rule that starts at ``selector``."""
    start = src.index(selector)
    open_ = src.index("{", start)
    close = src.index("\n}", open_)
    return src[open_ + 1 : close]


def _vars(body: str) -> dict[str, str]:
    """Map ``--rz-name`` declarations in a rule body to their values."""
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    return {k: " ".join(v.split()) for k, v in re.findall(r"--rz-([a-z0-9-]+):\s*([^;]+);", body)}


def build() -> dict:
    """Collect colour, type, space, radius and motion tokens into one dict."""
    tokens = (DS / "tokens.css").read_text(encoding="utf-8")
    motion = (DS / "motion.css").read_text(encoding="utf-8")
    dark = _vars(_block(tokens, ":root,\n[data-mode='dark']"))
    light = _vars(_block(tokens, "[data-mode='light'] {"))
    common = _vars(_block(tokens, "/* ── Mode-independent"))
    mo = _vars(_block(motion, ":root {"))

    def pick(prefix: str) -> dict[str, str]:
        return {k[len(prefix) :]: v for k, v in common.items() if k.startswith(prefix)}

    by_mode = {k: {"dark": dark[k], "light": light[k]} for k in dark}
    return {
        "$schema": "https://schemas.amazon.com/style-dictionary/3.0/tokens.json",
        "name": "@realizeos/design-system",
        "version": "2.0.0",
        "description": "Drawing Set. Generated from tokens.css and motion.css by "
        "scripts/build_design_tokens.py; edit the CSS, not this file.",
        "color": {k: v for k, v in by_mode.items() if not k.startswith("shadow")},
        "shadow": {k: v for k, v in by_mode.items() if k.startswith("shadow")},
        "font": pick("font-"),
        "text": pick("text-"),
        "leading": pick("leading-"),
        "tracking": pick("tracking-"),
        "space": pick("space-"),
        "radius": pick("radius-"),
        "z": pick("z-"),
        "layout": {k: common[k] for k in ("sidebar-w", "content-max", "reading-max")},
        "motion": {
            "duration": {k[4:]: v for k, v in mo.items() if k.startswith("dur-") and not v.startswith("var")},
            "easing": {k[5:]: v for k, v in mo.items() if k.startswith("ease-")},
            "spring": {
                "settle": {"fallback": mo["spring-settle"], "duration": mo["spring-settle-dur"]},
                "bounce": {"fallback": mo["spring-bounce"], "duration": mo["spring-bounce-dur"]},
            },
            "stagger": mo["stagger"],
        },
    }


def main() -> None:
    """Write tokens.json next to the CSS it was built from."""
    out = DS / "tokens.json"
    out.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(DS.parents[2])}")


if __name__ == "__main__":
    main()
