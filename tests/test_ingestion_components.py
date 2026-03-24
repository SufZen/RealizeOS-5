"""Test content ingestion module."""

import pytest
from realize_core.ingestion.extractor import extract_from_url, save_to_kb


@pytest.fixture
def test_pdf(tmp_path):
    # we don't need a real pdf, just test the fallback
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_text("dummy")
    return pdf_path


@pytest.mark.asyncio
async def test_extract_from_url(monkeypatch):
    result = await extract_from_url("https://example.com")
    # Will fail or fallback but we just want to ensure it doesn't crash
    assert isinstance(result, dict)


def test_save_to_kb(tmp_path):
    system_config = {"brain_dir": "brain"}

    result = save_to_kb(
        content="Test content",
        title="My Document",
        kb_path=tmp_path,
        system_config=system_config,
        category="brain",
    )

    assert result["saved"] is True

    # check file exists
    saved_file = tmp_path / "brain" / "my-document.md"
    assert saved_file.exists()
    content = saved_file.read_text(encoding="utf-8")
    assert "# My Document" in content
    assert "Test content" in content


def test_url_to_title():
    from realize_core.ingestion.extractor import _url_to_title

    title = _url_to_title("https://example.com/some-blog-post")
    assert title == "Some Blog Post"

    title2 = _url_to_title("https://github.com/")
    assert title2 == "Github.Com"
