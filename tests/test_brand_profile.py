"""
Tests for Brand Profile System — Intent 3.3.

Covers:
- BrandProfile model creation and validation
- load_brand_profile() from YAML
- brand_to_prompt() formatting
- resolve_brand() resolution chain
- Sample profile loading
"""

from __future__ import annotations

from pathlib import Path

import pytest
from realize_core.prompt.brand import (
    BrandProfile,
    brand_to_prompt,
    load_brand_profile,
    resolve_brand,
)

# ---------------------------------------------------------------------------
# BrandProfile model
# ---------------------------------------------------------------------------


class TestBrandProfile:
    def test_minimal(self):
        brand = BrandProfile(name="TestBrand")
        assert brand.name == "TestBrand"
        assert brand.voice == "professional"
        assert brand.domains == []

    def test_full_profile(self):
        brand = BrandProfile(
            name="Acme Corp",
            tagline="We build things",
            mission="Make the world better",
            primary_color="#FF5733",
            secondary_color="#33FF57",
            voice="playful",
            tone="Warm and inviting",
            writing_guidelines=["Use active voice", "Keep it short"],
            target_audience="Small business owners",
            domains=["SaaS", "productivity"],
            social_handles={"twitter": "@acme", "linkedin": "acme-corp"},
            key_differentiators=["AI-powered", "Open source"],
        )
        assert brand.primary_color == "#FF5733"
        assert len(brand.writing_guidelines) == 2
        assert brand.social_handles["twitter"] == "@acme"

    def test_extra_fields_allowed(self):
        brand = BrandProfile(name="Test", custom_field="value")
        assert brand.custom_field == "value"


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestLoadBrandProfile:
    def test_load_from_yaml(self, tmp_path):
        brand_yaml = tmp_path / "brand.yaml"
        brand_yaml.write_text(
            "name: TestBrand\ntagline: Testing things\nvoice: casual\n",
            encoding="utf-8",
        )
        brand = load_brand_profile(brand_yaml)
        assert brand is not None
        assert brand.name == "TestBrand"
        assert brand.tagline == "Testing things"
        assert brand.voice == "casual"

    def test_missing_file(self, tmp_path):
        brand = load_brand_profile(tmp_path / "nope.yaml")
        assert brand is None

    def test_nested_brand_key(self, tmp_path):
        brand_yaml = tmp_path / "brand.yaml"
        brand_yaml.write_text(
            "brand:\n  name: NestedBrand\n  tagline: Nested test\n",
            encoding="utf-8",
        )
        brand = load_brand_profile(brand_yaml)
        assert brand is not None
        assert brand.name == "NestedBrand"

    def test_invalid_yaml(self, tmp_path):
        brand_yaml = tmp_path / "brand.yaml"
        brand_yaml.write_text("[invalid yaml: {{{", encoding="utf-8")
        brand = load_brand_profile(brand_yaml)
        assert brand is None

    def test_non_mapping_yaml(self, tmp_path):
        brand_yaml = tmp_path / "brand.yaml"
        brand_yaml.write_text("- just\n- a\n- list\n", encoding="utf-8")
        brand = load_brand_profile(brand_yaml)
        assert brand is None

    def test_missing_name_defaults(self, tmp_path):
        brand_yaml = tmp_path / "brand.yaml"
        brand_yaml.write_text("tagline: No name\n", encoding="utf-8")
        brand = load_brand_profile(brand_yaml)
        assert brand is not None
        assert brand.name == "Untitled Brand"


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


class TestBrandToPrompt:
    def test_basic(self):
        brand = BrandProfile(
            name="TestBrand",
            tagline="Test tagline",
            voice="professional",
        )
        prompt = brand_to_prompt(brand)
        assert "## Brand Profile: TestBrand" in prompt
        assert "Test tagline" in prompt
        assert "professional" in prompt

    def test_full_profile_format(self):
        brand = BrandProfile(
            name="Acme",
            tagline="We build",
            mission="Build better",
            voice="bold",
            tone="Confident",
            target_audience="Engineers",
            domains=["SaaS", "DevTools"],
            writing_guidelines=["Be brief", "Use data"],
            key_differentiators=["Fast", "Reliable"],
            primary_color="#000",
            social_handles={"twitter": "@acme"},
        )
        prompt = brand_to_prompt(brand)
        assert "Engineers" in prompt
        assert "SaaS, DevTools" in prompt
        assert "- Be brief" in prompt
        assert "- Fast" in prompt
        assert "#000" in prompt
        assert "@acme" in prompt

    def test_empty_optional_fields(self):
        brand = BrandProfile(name="Minimal")
        prompt = brand_to_prompt(brand)
        assert "## Brand Profile: Minimal" in prompt
        assert "Writing Guidelines" not in prompt


# ---------------------------------------------------------------------------
# resolve_brand
# ---------------------------------------------------------------------------


class TestResolveBrand:
    def test_from_file(self, tmp_path):
        brand_yaml = tmp_path / "brand.yaml"
        brand_yaml.write_text("name: FileBrand\nvoice: casual\n", encoding="utf-8")
        brand = resolve_brand(venture_dir=tmp_path)
        assert brand is not None
        assert brand.name == "FileBrand"

    def test_from_config(self):
        config = {"brand": {"name": "ConfigBrand", "voice": "technical"}}
        brand = resolve_brand(config=config)
        assert brand is not None
        assert brand.name == "ConfigBrand"

    def test_config_priority_over_file(self, tmp_path):
        brand_yaml = tmp_path / "brand.yaml"
        brand_yaml.write_text("name: FileBrand\n", encoding="utf-8")
        config = {"brand": {"name": "ConfigBrand"}}
        brand = resolve_brand(venture_dir=tmp_path, config=config)
        assert brand.name == "ConfigBrand"

    def test_no_sources(self):
        brand = resolve_brand()
        assert brand is None


# ---------------------------------------------------------------------------
# Sample profiles
# ---------------------------------------------------------------------------


class TestSampleProfiles:
    """Test that the shipped sample brand profiles load correctly."""

    SAMPLES_DIR = Path(__file__).parent.parent / "ventures" / "_templates"

    def test_agency_profile(self):
        path = self.SAMPLES_DIR / "agency" / "brand.yaml"
        if not path.exists():
            pytest.skip("Agency sample not found")
        brand = load_brand_profile(path)
        assert brand is not None
        assert brand.name == "CreativeFlow Agency"
        assert len(brand.writing_guidelines) > 0

    def test_saas_profile(self):
        path = self.SAMPLES_DIR / "saas" / "brand.yaml"
        if not path.exists():
            pytest.skip("SaaS sample not found")
        brand = load_brand_profile(path)
        assert brand is not None
        assert brand.name == "LaunchPad SaaS"
        assert "developer tools" in brand.domains
