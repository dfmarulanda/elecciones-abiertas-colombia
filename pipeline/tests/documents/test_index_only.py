from __future__ import annotations

import ast
from pathlib import Path

import pytest
from elecciones_pipeline.documents import DocumentURLPolicy, index_official_documents
from elecciones_pipeline.ingest import PolicyDenied

ROOT = Path(__file__).resolve().parents[2]


def _policy() -> DocumentURLPolicy:
    return DocumentURLPolicy({"official.gov.co"}, resolver=lambda _host: ["8.8.8.8"])


def test_index_keeps_only_explicit_allowlisted_reference_and_source_index_hash() -> None:
    source_index_url = "https://official.gov.co/index.json"
    entry = index_official_documents(
        source_index_url,
        {
            "documents": [
                {
                    "mesa_id": "M-1",
                    "document_type": "e14_delegate",
                    "official_url": "https://official.gov.co/forms/m1.pdf",
                }
            ]
        },
        {"M-1"},
        policy=_policy(),
    )[0]
    assert entry.mesa_id == "M-1"
    assert entry.official_url == "https://official.gov.co/forms/m1.pdf"
    assert entry.source_index_url == source_index_url
    assert len(entry.source_index_hash) == 64


def test_index_refuses_unknown_mesa_or_external_url() -> None:
    with pytest.raises(ValueError, match="unknown/non-canonical"):
        index_official_documents(
            "https://official.gov.co/index.json",
            {
                "mesa_id": "forged",
                "document_type": "e14_delegate",
                "url": "https://official.gov.co/x.pdf",
            },
            {"M-1"},
            policy=_policy(),
        )


def test_index_never_constructs_a_document_url_from_a_relative_reference() -> None:
    with pytest.raises(ValueError, match="explicit absolute HTTPS"):
        index_official_documents(
            "https://official.gov.co/index.json",
            {"mesa_id": "M-1", "document_type": "e14_delegate", "url": "/forms/m1.pdf"},
            {"M-1"},
            policy=_policy(),
        )
    with pytest.raises(PolicyDenied, match="exact official"):
        index_official_documents(
            "https://official.gov.co/index.json",
            {
                "mesa_id": "M-1",
                "document_type": "e14_delegate",
                "url": "https://untrusted.example/f.pdf",
            },
            {"M-1"},
            policy=_policy(),
        )


def test_e14_indexer_has_no_http_client_or_binary_document_handling_path() -> None:
    """The entire E-14 package must remain metadata-only and offline."""
    package = ROOT / "src/elecciones_pipeline/documents"
    assert not (package / "fetch.py").exists()
    assert not (package / "redaction.py").exists()
    assert not (package / "transcription.py").exists()
    assert not (package / "verification.py").exists()
    forbidden_import_roots = {"httpx", "requests", "fitz", "PIL", "pytesseract", "easyocr"}
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert not imports & forbidden_import_roots, path
