"""
Brand Profile System — Venture-level brand identity for content sessions.

Loads brand configuration from a YAML file (``brand.yaml``) in the venture
directory and injects it into the prompt builder for content-focused agents.

Brand profiles include:
- Company identity (name, tagline, mission)
- Visual identity (colors, typography notes)
- Voice & tone guidelines
- Target audience
- Key topics and domains
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BrandProfile(BaseModel):
    """
    Venture-level brand profile.

    Loaded from ``brand.yaml`` in the venture directory.
    """

    # Core identity
    name: str = Field(description="Brand / company name")
    tagline: str = Field(default="", description="Brand tagline or slogan")
    mission: str = Field(default="", description="Mission statement")

    # Visual (advisory — agents can reference in content)
    primary_color: str = Field(default="", description="Primary brand color (hex)")
    secondary_color: str = Field(default="", description="Secondary brand color (hex)")
    typography_note: str = Field(
        default="",
        description="Typography guidance (e.g. 'Use modern sans-serif')",
    )

    # Voice & tone
    voice: str = Field(default="professional", description="Brand voice (e.g. professional, playful, authoritative)")
    tone: str = Field(default="", description="Tone nuances (e.g. warm but expert)")
    writing_guidelines: list[str] = Field(
        default_factory=list,
        description="Specific writing rules (e.g. 'Always use active voice')",
    )

    # Audience & domain
    target_audience: str = Field(default="", description="Primary audience description")
    domains: list[str] = Field(
        default_factory=list,
        description="Content domains (e.g. ['technology', 'SaaS', 'productivity'])",
    )
    social_handles: dict[str, str] = Field(
        default_factory=dict,
        description="Social media handles {platform: handle}",
    )

    # Differentiators
    key_differentiators: list[str] = Field(
        default_factory=list,
        description="What makes this brand unique",
    )

    model_config = {"extra": "allow"}


def load_brand_profile(path: Path | str) -> BrandProfile | None:
    """
    Load a brand profile from a YAML file.

    Args:
        path: Path to brand.yaml file.

    Returns:
        BrandProfile instance, or None if file doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        logger.debug("Brand profile not found: %s", path)
        return None

    try:
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML in brand file %s: %s", path, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("Brand YAML must be a mapping, got %s in %s", type(data).__name__, path)
        return None

    # Support nested structure: brand: { ... }
    if "brand" in data and isinstance(data["brand"], dict):
        data = data["brand"]

    if "name" not in data:
        data["name"] = "Untitled Brand"

    return BrandProfile(**data)


def brand_to_prompt(brand: BrandProfile) -> str:
    """
    Convert a BrandProfile into a prompt injection string.

    Produces a structured markdown section for the prompt builder.
    """
    parts = [f"## Brand Profile: {brand.name}"]

    if brand.tagline:
        parts.append(f"**Tagline:** {brand.tagline}")

    if brand.mission:
        parts.append(f"**Mission:** {brand.mission}")

    if brand.voice:
        parts.append(f"**Voice:** {brand.voice}")

    if brand.tone:
        parts.append(f"**Tone:** {brand.tone}")

    if brand.target_audience:
        parts.append(f"**Target Audience:** {brand.target_audience}")

    if brand.domains:
        parts.append(f"**Content Domains:** {', '.join(brand.domains)}")

    if brand.writing_guidelines:
        parts.append("\n**Writing Guidelines:**")
        for guideline in brand.writing_guidelines:
            parts.append(f"- {guideline}")

    if brand.key_differentiators:
        parts.append("\n**Key Differentiators:**")
        for diff in brand.key_differentiators:
            parts.append(f"- {diff}")

    if brand.primary_color:
        parts.append(f"\n**Primary Color:** {brand.primary_color}")

    if brand.social_handles:
        handles = ", ".join(f"{k}: {v}" for k, v in brand.social_handles.items())
        parts.append(f"**Social:** {handles}")

    return "\n".join(parts)


def resolve_brand(
    venture_dir: Path | str | None = None,
    config: dict[str, Any] | None = None,
) -> BrandProfile | None:
    """
    Resolve brand profile from venture directory or config.

    Resolution order:
    1. In-memory config dict (if provided)
    2. brand.yaml file in venture directory
    3. None (no brand defined)
    """
    # 1. From config dict
    if config and isinstance(config, dict):
        brand_data = config.get("brand", config)
        if "name" in brand_data:
            return BrandProfile(**brand_data)

    # 2. From file
    if venture_dir:
        brand_path = Path(venture_dir) / "brand.yaml"
        return load_brand_profile(brand_path)

    return None
