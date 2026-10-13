"""Tender requirements register: method, checks and finished document (STORY-46)."""

from __future__ import annotations

from typing import Any

from realize_core.packs import discover_packs
from realize_core.packs.models import VERIFICATION_NAMES

#: A register larger than this is outside the free pilot (about a 50-page tender).
MAX_ITEMS = 300
MAX_TEXT = 1000
CATEGORIES = ("administrative", "technical", "financial", "legal", "schedule")

STEPS = [
    "Read the whole tender package, including annexes and the bill of quantities.",
    "List every requirement as one item: what must be submitted, met or priced.",
    "Mark each item mandatory or optional exactly as the document says; when unclear, mark mandatory and say why.",
    "Give each item a category: administrative, technical, financial, legal or schedule.",
    "Record where each item is: the file name and the page or section (the locator). Items without a locator are flagged.",
    "Note deadlines and owners when the document names them.",
    "Use the market's local terms and rule cards below; say which rule an item relies on.",
]

LIMITS = [
    "The register is a draft prepared by your agent and checked by RealizeOS. A person decides what to bid.",
    "It does not replace legal review of the tender conditions.",
]


def _market_context(market: str | None) -> dict[str, Any]:
    """Glossary, rule cards and verification level for a market, or level 0 when there is no pack."""
    packs = discover_packs()
    pack = packs.get(("market", (market or "").lower())) if market else None
    if pack is None:
        return {
            "market": market or "any",
            "verification": 0,
            "verification_name": VERIFICATION_NAMES[0],
            "notice": "No market pack: local rules come from your agent's general knowledge and are unverified.",
            "terms": [],
            "rules": [],
            "limits": [],
        }
    level = pack.verification_level if pack.verification_level is not None else 1
    return {
        "market": pack.id,
        "pack": pack.ref,
        "verification": level,
        "verification_name": VERIFICATION_NAMES.get(level, ""),
        "notice": f"Market pack {pack.title}, verification {level} ({VERIFICATION_NAMES.get(level, '')}).",
        "terms": [
            {"term": e["term"], "family": e["family"], "kind": e.get("kind"), "language": e.get("language")}
            for e in pack.terms.values()
        ],
        "rules": [
            {
                "id": c.id,
                "statement": c.statement,
                "source": c.source,
                "as_of": c.as_of,
                "verification": c.effective_level(pack.verification_level),
            }
            for c in pack.rules.values()
        ],
        "limits": pack.limits,
    }


def get_method(market: str | None = None) -> dict[str, Any]:
    """Everything the user's agent needs to build the register for a market."""
    return {
        "steps": STEPS,
        "register_format": {
            "items": [
                {
                    "statement": "string, what is required",
                    "mandatory": "boolean",
                    "category": "|".join(CATEGORIES),
                    "sources": [{"source": "file name", "locator": "page or section"}],
                    "due": "optional date (YYYY-MM-DD)",
                    "owner": "optional",
                    "rule": "optional rule card id the item relies on",
                }
            ],
            "max_items": MAX_ITEMS,
        },
        "market": _market_context(market),
        "limits": LIMITS,
    }


def check_register(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate and normalise a register. Returns items, warnings and counts."""
    if not isinstance(items, list) or not items:
        raise ValueError("The register needs at least one item")
    if len(items) > MAX_ITEMS:
        raise ValueError(f"The free pilot handles up to {MAX_ITEMS} items")
    clean: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for n, raw in enumerate(items, start=1):
        if not isinstance(raw, dict) or not str(raw.get("statement") or "").strip():
            warnings.append(f"Item {n}: no statement, skipped")
            continue
        statement = str(raw["statement"]).strip()[:MAX_TEXT]
        key = statement.casefold()
        if key in seen:
            warnings.append(f"Item {n}: duplicate of an earlier item, skipped")
            continue
        seen.add(key)
        sources = [
            {"source": str(s.get("source"))[:300], "locator": str(s.get("locator") or "")[:100]}
            for s in raw.get("sources") or []
            if isinstance(s, dict) and s.get("source")
        ]
        located = any(s["locator"] for s in sources)
        category = str(raw.get("category") or "").lower()
        if category not in CATEGORIES:
            warnings.append(f"Item {n}: category '{category or 'missing'}' is not one of {', '.join(CATEGORIES)}")
            category = category or "administrative"
        if not isinstance(raw.get("mandatory"), bool):
            warnings.append(f"Item {n}: mandatory not stated; treated as mandatory")
        if not located:
            warnings.append(f"Item {n}: no page or section given")
        clean.append(
            {
                "n": len(clean) + 1,
                "statement": statement,
                "mandatory": raw.get("mandatory") if isinstance(raw.get("mandatory"), bool) else True,
                "category": category,
                "sources": sources,
                "located": located,
                "due": str(raw.get("due") or "")[:20],
                "owner": str(raw.get("owner") or "")[:100],
                "rule": str(raw.get("rule") or "")[:100],
            }
        )
    if not clean:
        raise ValueError("No usable items in the register")
    return {
        "items": clean,
        "warnings": warnings,
        "counts": {
            "items": len(clean),
            "mandatory": sum(1 for i in clean if i["mandatory"]),
            "without_locator": sum(1 for i in clean if not i["located"]),
        },
    }


_HEAD = {
    "en": ("Tender requirements register", "Item", "Requirement", "Mandatory", "Category", "Where", "yes", "no"),
    "he": ("מרשם דרישות המכרז", "#", "דרישה", "חובה", "קטגוריה", "מקור", "כן", "לא"),
    "pt": ("Registo de requisitos do concurso", "N.º", "Requisito", "Obrigatório", "Categoria", "Onde", "sim", "não"),
}


def render_register(checked: dict[str, Any], *, market: str | None, language: str = "en", title: str = "") -> str:
    """Finished-document markdown with the verification level and limits on top."""
    head = _HEAD.get(language, _HEAD["en"])
    ctx = _market_context(market)
    lines = [f"# {head[0]}" + (f" — {title}" if title else ""), "", f"> {ctx['notice']}"]
    for limit in [*LIMITS, *ctx["limits"]]:
        lines.append(f"> {limit}")
    c = checked["counts"]
    lines += [
        "",
        f"{c['items']} items · {c['mandatory']} mandatory · {c['without_locator']} without a page or section",
        "",
        f"| {head[1]} | {head[2]} | {head[3]} | {head[4]} | {head[5]} |",
        "|---|---|---|---|---|",
    ]
    for item in checked["items"]:
        where = "; ".join(f"{s['source']} {s['locator']}".strip() for s in item["sources"]) or "⚠"
        text = item["statement"].replace("|", "/")
        mandatory = head[6] if item["mandatory"] else head[7]
        lines.append(f"| {item['n']} | {text} | {mandatory} | {item['category']} | {where.replace('|', '/')} |")
    return "\n".join(lines) + "\n"
