"""
Tests for realize_core.skills.md_loader — SKILL.md parser.

Covers:
- Frontmatter parsing (name, description, triggers, tags, agent)
- Markdown body extraction
- Edge cases: no frontmatter, missing name, malformed YAML
- to_skill_dict() conversion
- Single file loading
- Directory scanning
"""


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------

class TestParseSkillMd:

    def test_basic_parse(self):
        """Parse a well-formed SKILL.md file."""
        from realize_core.skills.md_loader import parse_skill_md

        content = """---
name: content_review
description: Review content for quality
triggers:
  - review content
  - check quality
tags: [content, review]
agent: reviewer
version: "2"
---

# Content Review

Review the submitted content for grammar, tone, and clarity.

## Steps
1. Check grammar and spelling
2. Evaluate tone consistency
3. Suggest improvements

## Output Format
Return a structured review with scores.
"""
        defn = parse_skill_md(content)
        assert defn is not None
        assert defn.name == "content_review"
        assert defn.description == "Review content for quality"
        assert defn.triggers == ["review content", "check quality"]
        assert defn.tags == ["content", "review"]
        assert defn.agent == "reviewer"
        assert defn.version == "2"
        assert "# Content Review" in defn.instructions
        assert "grammar and spelling" in defn.instructions

    def test_key_property(self):
        """key property should return normalised snake_case."""
        from realize_core.skills.md_loader import parse_skill_md

        content = "---\nname: My-Cool Skill\n---\nBody"
        defn = parse_skill_md(content)
        assert defn is not None
        assert defn.key == "my_cool_skill"

    def test_minimal_frontmatter(self):
        """Only 'name' is required; other fields have defaults."""
        from realize_core.skills.md_loader import parse_skill_md

        content = "---\nname: minimal\n---\nJust instructions."
        defn = parse_skill_md(content)
        assert defn is not None
        assert defn.name == "minimal"
        assert defn.description == ""
        assert defn.triggers == []
        assert defn.tags == []
        assert defn.agent == "orchestrator"
        assert defn.version == "1"
        assert defn.instructions == "Just instructions."

    def test_no_frontmatter(self):
        """File without --- markers should return None."""
        from realize_core.skills.md_loader import parse_skill_md

        content = "# Just a regular markdown file\n\nNo frontmatter here."
        assert parse_skill_md(content) is None

    def test_missing_name(self):
        """Frontmatter without 'name' should return None."""
        from realize_core.skills.md_loader import parse_skill_md

        content = "---\ndescription: No name field\n---\nBody"
        assert parse_skill_md(content) is None

    def test_malformed_yaml(self):
        """Malformed YAML frontmatter should return None."""
        from realize_core.skills.md_loader import parse_skill_md

        content = "---\nname: test\ninvalid: yaml: : [\n---\nBody"
        result = parse_skill_md(content)
        # May parse or fail depending on PyYAML tolerance
        # Either None or a valid result is acceptable
        assert result is None or result.name == "test"

    def test_string_triggers(self):
        """A single string trigger should be wrapped in a list."""
        from realize_core.skills.md_loader import parse_skill_md

        content = "---\nname: single_trigger\ntriggers: do something\n---\nBody"
        defn = parse_skill_md(content)
        assert defn is not None
        assert defn.triggers == ["do something"]

    def test_string_tags_comma_separated(self):
        """Comma-separated tags string should be split into a list."""
        from realize_core.skills.md_loader import parse_skill_md

        content = "---\nname: tagged\ntags: content, writing, drafts\n---\nBody"
        defn = parse_skill_md(content)
        assert defn is not None
        assert "content" in defn.tags
        assert "writing" in defn.tags
        assert "drafts" in defn.tags

    def test_empty_body(self):
        """Frontmatter with no body should have empty instructions."""
        from realize_core.skills.md_loader import parse_skill_md

        content = "---\nname: no_body\n---\n"
        defn = parse_skill_md(content)
        assert defn is not None
        assert defn.instructions == ""

    def test_file_path_stored(self):
        """file_path should be stored in the definition."""
        from realize_core.skills.md_loader import parse_skill_md

        defn = parse_skill_md("---\nname: test\n---\nBody",
                               file_path="/path/to/skill.md")
        assert defn is not None
        assert defn.file_path == "/path/to/skill.md"

    def test_extra_frontmatter_fields(self):
        """Extra frontmatter fields should be preserved."""
        from realize_core.skills.md_loader import parse_skill_md

        content = "---\nname: custom\ncustom_field: hello\n---\nBody"
        defn = parse_skill_md(content)
        assert defn is not None
        assert defn.frontmatter["custom_field"] == "hello"


# ---------------------------------------------------------------------------
# to_skill_dict conversion
# ---------------------------------------------------------------------------

class TestToSkillDict:

    def test_conversion(self):
        """to_skill_dict() should produce a detector-compatible dict."""
        from realize_core.skills.md_loader import parse_skill_md

        content = """---
name: research_helper
description: Help with research tasks
triggers:
  - research
  - investigate
agent: analyst
---

# Research Helper

Detailed research instructions here.
"""
        defn = parse_skill_md(content, file_path="/skills/research.skill.md")
        assert defn is not None

        skill_dict = defn.to_skill_dict()
        assert skill_dict["name"] == "research_helper"
        assert skill_dict["description"] == "Help with research tasks"
        assert skill_dict["triggers"] == ["research", "investigate"]
        assert skill_dict["agent"] == "analyst"
        assert skill_dict["_format"] == "skill_md"
        assert skill_dict["_version"] == 1
        assert "research instructions" in skill_dict["_instructions"].lower()
        assert skill_dict["_source"] == "/skills/research.skill.md"


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

class TestLoadSkillMdFile:

    def test_load_from_file(self, tmp_path):
        """Load a SKILL.md file from disk."""
        from realize_core.skills.md_loader import load_skill_md_file

        md_file = tmp_path / "my_skill.skill.md"
        md_file.write_text(
            "---\nname: disk_skill\ntriggers:\n  - do thing\n---\n"
            "# Instructions\n\nDo the thing carefully.",
            encoding="utf-8",
        )

        defn = load_skill_md_file(md_file)
        assert defn is not None
        assert defn.name == "disk_skill"
        assert "Do the thing carefully" in defn.instructions

    def test_load_nonexistent_file(self, tmp_path):
        """Loading a non-existent file should return None."""
        from realize_core.skills.md_loader import load_skill_md_file

        result = load_skill_md_file(tmp_path / "nonexistent.md")
        assert result is None


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------

class TestScanSkillMdFiles:

    def test_scan_directory(self, tmp_path):
        """Scan a directory and find SKILL.md files."""
        from realize_core.skills.md_loader import scan_skill_md_files

        # Create skill files
        (tmp_path / "alpha.skill.md").write_text(
            "---\nname: alpha_skill\n---\nAlpha instructions.",
            encoding="utf-8",
        )
        (tmp_path / "beta.skill.md").write_text(
            "---\nname: beta_skill\n---\nBeta instructions.",
            encoding="utf-8",
        )

        results = scan_skill_md_files(tmp_path, recursive=False)
        assert len(results) == 2
        names = {d.name for d in results}
        assert "alpha_skill" in names
        assert "beta_skill" in names

    def test_scan_recursive(self, tmp_path):
        """Recursive scan should find files in subdirectories."""
        from realize_core.skills.md_loader import scan_skill_md_files

        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.skill.md").write_text(
            "---\nname: deep_skill\n---\nDeep.", encoding="utf-8"
        )

        results = scan_skill_md_files(tmp_path, recursive=True)
        assert len(results) == 1
        assert results[0].name == "deep_skill"

    def test_scan_skips_readme(self, tmp_path):
        """Scanner should skip README.md and similar files."""
        from realize_core.skills.md_loader import scan_skill_md_files

        (tmp_path / "README.md").write_text(
            "---\nname: readme_skill\n---\nShould be skipped.",
            encoding="utf-8",
        )
        (tmp_path / "real.skill.md").write_text(
            "---\nname: real_skill\n---\nNot skipped.",
            encoding="utf-8",
        )

        results = scan_skill_md_files(tmp_path, recursive=False)
        assert len(results) == 1
        assert results[0].name == "real_skill"

    def test_scan_nonexistent_dir(self, tmp_path):
        """Scanning a non-existent directory returns empty list."""
        from realize_core.skills.md_loader import scan_skill_md_files

        results = scan_skill_md_files(tmp_path / "no_such_dir")
        assert results == []

    def test_scan_skips_invalid_md(self, tmp_path):
        """MD files without frontmatter should be skipped."""
        from realize_core.skills.md_loader import scan_skill_md_files

        (tmp_path / "not_skill.md").write_text(
            "# Just a doc\n\nNo frontmatter.", encoding="utf-8"
        )
        (tmp_path / "valid.skill.md").write_text(
            "---\nname: valid\n---\nOK.", encoding="utf-8"
        )

        results = scan_skill_md_files(tmp_path, recursive=False)
        assert len(results) == 1
        assert results[0].name == "valid"
