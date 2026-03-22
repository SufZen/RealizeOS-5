"""Tests for realize_core.kb.indexer — KB indexing and hybrid search.

Covers:
- Database initialization and schema creation
- Markdown file indexing with title extraction
- System detection from file paths
- FTS5 keyword search
- Cosine similarity computation
- Hybrid merge scoring
- Incremental indexing (mtime-based skip)
- Edge cases: empty KB, no match, binary data conversion
"""
import pytest
import struct
from pathlib import Path
from realize_core.kb.indexer import (
    _init_index_db,
    _get_conn,
    _extract_title,
    _detect_system,
    _cosine_similarity,
    _bytes_to_vec,
    _build_search_dirs,
    _merge_hybrid,
    index_kb_files,
    semantic_search,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def index_db(tmp_path):
    """Create an initialized index database."""
    db_path = tmp_path / "test_index.db"
    _init_index_db(db_path)
    return db_path


@pytest.fixture
def kb_with_files(tmp_path):
    """Create a KB directory with markdown files for indexing."""
    # System files
    sys_dir = tmp_path / "systems" / "venture1" / "F-foundations"
    sys_dir.mkdir(parents=True)
    (sys_dir / "venture-identity.md").write_text(
        "# Venture Identity\nWe are a tech company focused on AI solutions."
    )
    (sys_dir / "venture-voice.md").write_text(
        "# Venture Voice\nProfessional, concise, and innovative."
    )

    agents_dir = tmp_path / "systems" / "venture1" / "A-agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "orchestrator.md").write_text(
        "# Orchestrator\nCoordinates all agent activities."
    )

    insights_dir = tmp_path / "systems" / "venture1" / "I-insights"
    insights_dir.mkdir(parents=True)
    (insights_dir / "learning-log.md").write_text(
        "# Learning Log\n- Users prefer markdown tables\n- CTA should be bold"
    )

    # Shared files
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    (shared_dir / "identity.md").write_text(
        "# Identity\nI am a business owner managing multiple ventures."
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Database and schema
# ---------------------------------------------------------------------------

class TestDatabase:
    def test_init_creates_tables(self, index_db):
        """Database should have kb_files and kb_fts tables after init."""
        conn = _get_conn(index_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "kb_files" in table_names
        assert "kb_fts" in table_names
        conn.close()

    def test_init_is_idempotent(self, tmp_path):
        """Calling init twice should not fail."""
        db_path = tmp_path / "test.db"
        _init_index_db(db_path)
        _init_index_db(db_path)  # Should not raise


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_heading_extraction(self):
        content = "# My Document Title\nSome content here."
        assert _extract_title(content, "any/path.md") == "My Document Title"

    def test_heading_with_whitespace(self):
        content = "#   Spaced Title   \nContent."
        assert _extract_title(content, "any/path.md") == "Spaced Title"

    def test_no_heading_uses_filename(self):
        content = "Just content without any heading."
        result = _extract_title(content, "path/to/my-document.md")
        assert result == "My Document"

    def test_empty_content_uses_filename(self):
        result = _extract_title("", "path/some-file.md")
        assert result == "Some File"

    def test_multiline_content_uses_first_heading(self):
        content = "Some preamble\n# First Heading\n## Second Heading\nContent."
        assert _extract_title(content, "path.md") == "First Heading"


# ---------------------------------------------------------------------------
# System detection
# ---------------------------------------------------------------------------

class TestDetectSystem:
    def test_detects_from_path_structure(self):
        assert _detect_system("systems/venture1/F-foundations/venture.md") == "venture1"

    def test_detects_second_system(self):
        assert _detect_system("systems/venture2/A-agents/writer.md") == "venture2"

    def test_shared_files(self):
        result = _detect_system("shared/identity.md")
        assert result == "shared"

    def test_arbitrary_path_defaults_to_shared(self):
        result = _detect_system("some/random/path.md")
        assert result == "shared"

    def test_detect_from_config(self):
        config = {
            "myventure": {"system_dir": "systems/myventure"},
        }
        result = _detect_system("systems/myventure/F-foundations/test.md", config)
        assert result == "myventure"


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        a = [1.0, 0.0, 0.0]
        assert abs(_cosine_similarity(a, a) - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 0.001

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 0.001

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 1.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_nonunit_vectors(self):
        a = [3.0, 4.0]
        b = [3.0, 4.0]
        assert abs(_cosine_similarity(a, b) - 1.0) < 0.001


# ---------------------------------------------------------------------------
# Vector byte conversion
# ---------------------------------------------------------------------------

class TestBytesConversion:
    def test_roundtrip(self):
        original = [1.0, 2.5, -3.7, 0.0]
        packed = struct.pack(f"{len(original)}f", *original)
        result = _bytes_to_vec(packed)
        for a, b in zip(original, result):
            assert abs(a - b) < 0.001

    def test_empty_vector(self):
        packed = struct.pack("0f")
        result = _bytes_to_vec(packed)
        assert result == []


# ---------------------------------------------------------------------------
# Directory discovery
# ---------------------------------------------------------------------------

class TestBuildSearchDirs:
    def test_discovers_fabric_dirs(self, kb_with_files):
        dirs = _build_search_dirs(kb_with_files)
        # Should find F-foundations, A-agents, I-insights under venture1
        dir_names = [Path(d).name for d in dirs if "venture1" in d]
        assert "F-foundations" in dir_names
        assert "A-agents" in dir_names
        assert "I-insights" in dir_names

    def test_discovers_shared_dir(self, kb_with_files):
        dirs = _build_search_dirs(kb_with_files)
        assert any(Path(d).name == "shared" for d in dirs)

    def test_empty_kb(self, tmp_path):
        dirs = _build_search_dirs(tmp_path)
        assert dirs == []


# ---------------------------------------------------------------------------
# File indexing
# ---------------------------------------------------------------------------

class TestIndexKBFiles:
    def test_indexes_markdown_files(self, kb_with_files):
        db_path = kb_with_files / "test_index.db"
        count = index_kb_files(
            kb_root=str(kb_with_files),
            db_path=db_path,
            force=True,
        )
        assert count > 0

    def test_indexed_files_searchable(self, kb_with_files):
        db_path = kb_with_files / "test_index.db"
        index_kb_files(kb_root=str(kb_with_files), db_path=db_path, force=True)

        # FTS5 search should find results
        results = semantic_search(
            "venture identity",
            db_path=db_path,
            kb_root=str(kb_with_files),
        )
        assert len(results) > 0
        assert any("venture" in r.get("title", "").lower() for r in results)

    def test_incremental_skip(self, kb_with_files):
        """Second indexing run should skip unchanged files."""
        db_path = kb_with_files / "test_index.db"
        count1 = index_kb_files(kb_root=str(kb_with_files), db_path=db_path, force=True)
        count2 = index_kb_files(kb_root=str(kb_with_files), db_path=db_path, force=False)
        assert count1 > 0
        assert count2 == 0  # Nothing changed

    def test_force_reindexes(self, kb_with_files):
        """Force flag should re-index all files."""
        db_path = kb_with_files / "test_index.db"
        count1 = index_kb_files(kb_root=str(kb_with_files), db_path=db_path, force=True)
        count2 = index_kb_files(kb_root=str(kb_with_files), db_path=db_path, force=True)
        assert count1 == count2

    def test_empty_kb_returns_zero(self, tmp_path):
        db_path = tmp_path / "test_index.db"
        count = index_kb_files(kb_root=str(tmp_path), db_path=db_path, force=True)
        assert count == 0


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_with_system_filter(self, kb_with_files):
        db_path = kb_with_files / "test_index.db"
        index_kb_files(kb_root=str(kb_with_files), db_path=db_path, force=True)

        results = semantic_search(
            "venture",
            system_key="venture1",
            db_path=db_path,
            kb_root=str(kb_with_files),
        )
        assert all(r.get("system_key") == "venture1" for r in results)

    def test_search_no_results(self, kb_with_files):
        db_path = kb_with_files / "test_index.db"
        index_kb_files(kb_root=str(kb_with_files), db_path=db_path, force=True)

        results = semantic_search(
            "xyznonexistentterm123",
            db_path=db_path,
            kb_root=str(kb_with_files),
        )
        assert len(results) == 0

    def test_search_top_k_limit(self, kb_with_files):
        db_path = kb_with_files / "test_index.db"
        index_kb_files(kb_root=str(kb_with_files), db_path=db_path, force=True)

        results = semantic_search(
            "venture",
            top_k=1,
            db_path=db_path,
            kb_root=str(kb_with_files),
        )
        assert len(results) <= 1


# ---------------------------------------------------------------------------
# Hybrid merge
# ---------------------------------------------------------------------------

class TestHybridMerge:
    def test_merge_combines_scores(self):
        fts = [
            {"path": "a.md", "title": "A", "system_key": "s", "snippet": "...", "keyword_score": 1.0},
            {"path": "b.md", "title": "B", "system_key": "s", "snippet": "...", "keyword_score": 0.5},
        ]
        vector = [
            {"path": "a.md", "title": "A", "system_key": "s", "snippet": "...", "vector_score": 0.8},
            {"path": "c.md", "title": "C", "system_key": "s", "snippet": "...", "vector_score": 0.9},
        ]
        results = _merge_hybrid(fts, vector, top_k=5)
        paths = [r["path"] for r in results]
        assert "a.md" in paths  # Appears in both
        assert "b.md" in paths  # FTS only
        assert "c.md" in paths  # Vector only

    def test_merge_scoring_weights(self):
        fts = [{"path": "x.md", "title": "X", "system_key": "s", "snippet": "...", "keyword_score": 1.0}]
        vector = [{"path": "x.md", "title": "X", "system_key": "s", "snippet": "...", "vector_score": 1.0}]
        results = _merge_hybrid(fts, vector, top_k=5, vector_weight=0.7, keyword_weight=0.3)
        # Score should be 0.7*1.0 + 0.3*1.0 = 1.0
        assert abs(results[0]["score"] - 1.0) < 0.001

    def test_merge_respects_top_k(self):
        fts = [
            {"path": f"{i}.md", "title": f"Doc{i}", "system_key": "s", "snippet": "...", "keyword_score": 0.5}
            for i in range(10)
        ]
        results = _merge_hybrid(fts, [], top_k=3)
        assert len(results) <= 3

    def test_merge_empty_inputs(self):
        results = _merge_hybrid([], [], top_k=5)
        assert results == []
