"""
Content ingestion — extract text from URLs and PDF files, save to KB.

Supports:
- URL extraction (httpx + HTML-to-text)
- PDF text extraction (PyPDF2 / pdfplumber, with fallback)
- Plain text save
"""
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


async def extract_from_url(url: str, max_chars: int = 15000) -> dict:
    """
    Fetch a URL and extract readable text content.

    Returns:
        {title, content, url, char_count, extracted_at}
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (RealizeOS Content Ingestion)"
            })
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return {"error": f"Fetch failed: {e}", "url": url}

    # Try trafilatura first (best quality)
    content = None
    title = ""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            content = trafilatura.extract(downloaded, include_links=False, include_tables=True)
            # Extract title
            metadata = trafilatura.extract(downloaded, output_format="xml", include_links=False)
            if metadata:
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(metadata)
                    title = root.get("title", "") or ""
                except Exception:
                    pass
    except ImportError:
        pass

    # Fallback: simple HTML stripping
    if not content:
        content = _html_to_text(html)
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

    if not content:
        return {"error": "No content extracted", "url": url}

    content = content[:max_chars]

    return {
        "title": title or _url_to_title(url),
        "content": content,
        "url": url,
        "char_count": len(content),
        "extracted_at": datetime.now(UTC).isoformat(),
    }


def extract_from_pdf(file_path: Path, max_chars: int = 30000) -> dict:
    """
    Extract text from a PDF file.

    Returns:
        {title, content, pages, char_count, extracted_at}
    """
    text_parts = []
    pages = 0

    # Try pdfplumber first (better table handling)
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")

    # Fallback: PyPDF2
    if not text_parts:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(file_path))
            pages = len(reader.pages)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"PyPDF2 failed: {e}")

    if not text_parts:
        return {"error": "No text extracted from PDF", "path": str(file_path)}

    content = "\n\n".join(text_parts)[:max_chars]
    title = file_path.stem.replace("-", " ").replace("_", " ").title()

    return {
        "title": title,
        "content": content,
        "pages": pages,
        "char_count": len(content),
        "extracted_at": datetime.now(UTC).isoformat(),
    }


def save_to_kb(
    content: str,
    title: str,
    kb_path: Path,
    system_config: dict,
    source_url: str = "",
    category: str = "brain",
) -> dict:
    """
    Save extracted content to a venture's KB directory.

    Args:
        content: The extracted text
        title: Document title
        kb_path: Root KB path
        system_config: Venture system configuration
        source_url: Original URL (for attribution)
        category: Which FABRIC dir to save to (brain, insights, foundations)

    Returns:
        {saved, path, size}
    """
    # Determine target directory
    dir_map = {
        "brain": system_config.get("brain_dir", ""),
        "insights": system_config.get("insights_dir", ""),
        "foundations": system_config.get("foundations", ""),
    }
    rel_dir = dir_map.get(category, dir_map["brain"])
    if not rel_dir:
        return {"saved": False, "error": "No target directory configured"}

    target_dir = kb_path / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    safe_title = re.sub(r'[^\w\s-]', '', title.lower())
    safe_title = re.sub(r'[-\s]+', '-', safe_title).strip('-')[:60]
    if not safe_title:
        safe_title = f"ingested-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    filename = f"{safe_title}.md"

    file_path = target_dir / filename

    # Don't overwrite existing files
    if file_path.exists():
        counter = 1
        while file_path.exists():
            file_path = target_dir / f"{safe_title}-{counter}.md"
            counter += 1

    # Build markdown content
    md_lines = [f"# {title}", ""]
    if source_url:
        md_lines.append(f"> Source: {source_url}")
        md_lines.append(f"> Ingested: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        md_lines.append("")
    md_lines.append(content)

    file_path.write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "saved": True,
        "path": str(file_path.relative_to(kb_path)),
        "size": file_path.stat().st_size,
    }


def extract_from_text(text: str, title: str = "") -> dict:
    """Wrap plain text for KB saving."""
    return {
        "title": title or "Saved Note",
        "content": text,
        "char_count": len(text),
        "extracted_at": datetime.now(UTC).isoformat(),
    }


def _html_to_text(html: str) -> str:
    """Simple HTML to text extraction."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _url_to_title(url: str) -> str:
    """Generate a title from a URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path.strip("/").split("/")[-1] if parsed.path.strip("/") else parsed.hostname
    return path.replace("-", " ").replace("_", " ").title()[:80]
