import os
import tempfile
import pytest
from pathlib import Path
from agent_engine.tools.ast_ops import (
    get_document_map,
    get_entity_coordinates,
    get_references,
    get_html_attribute_bytes,
    verify_ast_integrity,
    batch_ast_query,
    TreeCache
)

@pytest.fixture
def temp_python_file():
    content = """import os
import sys
from collections import defaultdict

class UserService:
    def __init__(self, db_conn):
        self.db = db_conn

    def fetch_user_profile(self, user_id):
        # Fetching profile
        logger.info("Fetching profile")
        return {"id": user_id, "name": "Tobias"}

def calculate_premium_tax(amount):
    base_tax = amount * 0.15
    return base_tax
"""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(content.encode("utf-8"))
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture
def temp_html_file():
    content = """<!DOCTYPE html>
<html>
<body>
    <div class="awesome menu-item main-container" id="nav">
        <button class="btn-primary">Click Me</button>
    </div>
</body>
</html>
"""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(content.encode("utf-8"))
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)

async def test_get_document_map(temp_python_file):
    res = await get_document_map(temp_python_file)
    assert "classes" in res
    assert "functions" in res
    assert "imports" in res
    
    assert any(c["name"] == "UserService" for c in res["classes"])
    assert any(f["name"] == "calculate_premium_tax" for f in res["functions"])
    assert any("import os" in imp for imp in res["imports"])

async def test_get_entity_coordinates(temp_python_file):
    # Test Class coordinates
    res_class = await get_entity_coordinates(temp_python_file, "UserService", "class")
    assert res_class["found"] is True
    assert "class UserService:" in res_class["original_text_guard"]
    
    # Test Function coordinates
    res_func = await get_entity_coordinates(temp_python_file, "calculate_premium_tax", "function")
    assert res_func["found"] is True
    assert "def calculate_premium_tax(amount):" in res_func["original_text_guard"]

    # Test nested method coordinates (ClassName.method_name)
    res_method = await get_entity_coordinates(temp_python_file, "UserService.fetch_user_profile", "function")
    assert res_method["found"] is True
    assert "def fetch_user_profile(self, user_id):" in res_method["original_text_guard"]

    # Test optional entity_type auto-detection
    res_class_opt = await get_entity_coordinates(temp_python_file, "UserService")
    assert res_class_opt["found"] is True
    assert "class UserService:" in res_class_opt["original_text_guard"]

    res_func_opt = await get_entity_coordinates(temp_python_file, "calculate_premium_tax")
    assert res_func_opt["found"] is True
    assert "def calculate_premium_tax(amount):" in res_func_opt["original_text_guard"]

    # Test suggestion for missing symbol
    res_missing = await get_entity_coordinates(temp_python_file, "calculate_premium_taxx", "function")
    assert res_missing["found"] is False
    assert "calculate_premium_tax" in res_missing["suggestions"]

    # Verify that include_content=False correctly suppresses the original_text_guard field to save tokens
    res_no_content = await get_entity_coordinates(temp_python_file, "UserService", include_content=False)
    assert res_no_content["found"] is True
    assert "original_text_guard" not in res_no_content
    assert res_no_content["start_byte"] is not None

async def test_get_references(temp_python_file):
    res = await get_references(temp_python_file, "user_id")
    assert "references" in res
    assert len(res["references"]) >= 2
    # Verify exact references are captured
    assert all(ref["context"] != "" for ref in res["references"])

    # Verify that include_context=False correctly suppresses context lines to save tokens
    res_no_ctx = await get_references(temp_python_file, "user_id", include_context=False)
    assert "references" in res_no_ctx
    assert len(res_no_ctx["references"]) >= 2
    assert all("context" not in ref for ref in res_no_ctx["references"])

async def test_get_html_attribute_bytes(temp_html_file):
    res = await get_html_attribute_bytes(
        filepath=temp_html_file,
        tag_name="div",
        attribute_name="class",
        target_substring="awesome menu-item"
    )
    assert res["found"] is True
    
    # Check that bytes match the target substring on disk
    with open(temp_html_file, "rb") as f:
        file_bytes = f.read()
    matched_substring = file_bytes[res["start_byte"]:res["end_byte"]].decode("utf-8")
    assert matched_substring == "awesome menu-item"

async def test_verify_ast_integrity_valid(temp_python_file):
    res = await verify_ast_integrity(temp_python_file)
    assert res["syntax_valid"] is True
    assert len(res["errors"]) == 0

async def test_verify_ast_integrity_invalid():
    invalid_content = "def broken_syntax(:\n    print('broken')"
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(invalid_content.encode("utf-8"))
        path = f.name
        
    try:
        res = await verify_ast_integrity(path)
        assert res["syntax_valid"] is False
        assert len(res["errors"]) > 0
    finally:
        if os.path.exists(path):
            os.remove(path)

async def test_ast_path_safety():
    # Test that querying a path outside workdir is rejected
    res = await get_document_map("/etc/passwd", workdir="/tmp")
    assert "error" in res
    assert "Security Error" in res["error"]

    res_coords = await get_entity_coordinates("/etc/passwd", "some_symbol", workdir="/tmp")
    assert "error" in res_coords
    assert "Security Error" in res_coords["error"]

async def test_batch_ast_query(temp_python_file):
    queries = [
        {"action": "get_document_map", "params": {"filepath": temp_python_file}},
        {"action": "get_entity_coordinates", "params": {"filepath": temp_python_file, "entity_name": "UserService"}},
        {"action": "verify_ast_integrity", "params": {"filepath": temp_python_file}}
    ]
    res = await batch_ast_query(queries)
    assert "results" in res
    assert len(res["results"]) == 3
    assert res["results"][0]["success"] is True
    assert "classes" in res["results"][0]["result"]
    assert res["results"][1]["success"] is True
    assert res["results"][1]["result"]["found"] is True
    assert res["results"][2]["success"] is True
    assert res["results"][2]["result"]["syntax_valid"] is True


async def test_html_multi_and_element_coordinates():
    html_content = """<!DOCTYPE html>
<html>
<body>
    <nav>
        <a class="menu-item1" href="#home">Home</a>
        <a class="menu-item1" href="#menu">Menu</a>
        <a class="menu-item1" href="#contact">Contact</a>
    </nav>
    <div class="opening-hours">
        <h3>Hours</h3>
        <p>Mon - Fri: 6:30 AM - 5:00 PM</p>
    </div>
</body>
</html>
"""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(html_content.encode("utf-8"))
        path = f.name
        
    try:
        # 1. Test get_html_attribute_bytes multi-match
        res_multi = await get_html_attribute_bytes(
            filepath=path,
            tag_name="a",
            attribute_name="class",
            target_substring="menu-item1"
        )
        assert res_multi["found"] is True
        assert "matches" in res_multi
        assert len(res_multi["matches"]) == 3
        
        # Verify coordinates of all 3 matches
        with open(path, "rb") as f:
            file_bytes = f.read()
        for m in res_multi["matches"]:
            assert file_bytes[m["start_byte"]:m["end_byte"]].decode("utf-8") == "menu-item1"
            
        # 2. Test get_entity_coordinates HTML element matching by class/id
        res_element = await get_entity_coordinates(
            filepath=path,
            entity_name="opening-hours"
        )
        assert res_element["found"] is True
        assert "<div class=\"opening-hours\">" in res_element["original_text_guard"]
        assert "</div>" in res_element["original_text_guard"]
        
        # 3. Test wildcard tag search
        res_wildcard = await get_html_attribute_bytes(
            filepath=path,
            tag_name="*",
            attribute_name="class",
            target_substring="menu-item1"
        )
        assert res_wildcard["found"] is True
        assert len(res_wildcard["matches"]) == 3
        
        # Test optional tag search (omitted tag_name)
        res_optional = await get_html_attribute_bytes(
            filepath=path,
            attribute_name="class",
            target_substring="menu-item1"
        )
        assert res_optional["found"] is True
        assert len(res_optional["matches"]) == 3
        
    finally:
        if os.path.exists(path):
            os.remove(path)


async def test_get_html_style_element_bytes():
    html_content = """<!DOCTYPE html>
<html>
<head>
    <style>
        .old-button { padding: 10px; }
        div.old-button { color: red; }
    </style>
</head>
<body>
    <button class="old-button">Click</button>
</body>
</html>"""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(html_content.encode("utf-8"))
        path = f.name
        
    try:
        res = await get_html_attribute_bytes(
            filepath=path,
            attribute_name="class",
            target_substring="old-button"
        )
        assert res["found"] is True
        # It should match twice in style_element (css class_name) and once in the button tag class attribute!
        assert len(res["matches"]) == 3
        
        with open(path, "rb") as f:
            file_bytes = f.read()
        for m in res["matches"]:
            matched = file_bytes[m["start_byte"]:m["end_byte"]].decode("utf-8")
            assert matched == "old-button"
            
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_get_references_pagination():
    """Validates limit, offset, total_count, and has_more fields on get_references."""
    content = b"x = 1\nprint(x)\ny = x + x\nresult = x * 2\n"
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(content)
        path = f.name
    try:
        # Unpaginated: all refs, no pagination metadata
        res_all = await get_references(path, "x")
        total = res_all["total_count"]
        assert total >= 4  # declaration + multiple usages
        assert "has_more" not in res_all
        assert "limit" not in res_all

        # Paginated with limit=2: should return only 2, flag has_more=True
        res_limit = await get_references(path, "x", limit=2)
        assert len(res_limit["references"]) == 2
        assert res_limit["total_count"] == total
        assert res_limit["has_more"] is True
        assert res_limit["limit"] == 2
        assert res_limit["offset"] == 0

        # offset=2, limit=2: next page
        res_page2 = await get_references(path, "x", limit=2, offset=2)
        assert len(res_page2["references"]) == 2
        assert res_page2["offset"] == 2
        # Bytes should be different from first page
        assert res_page2["references"][0]["start_byte"] != res_limit["references"][0]["start_byte"]

        # limit=1000 (larger than total): has_more should be False
        res_big = await get_references(path, "x", limit=1000)
        assert res_big["has_more"] is False
        assert len(res_big["references"]) == total

    finally:
        if os.path.exists(path):
            os.remove(path)
