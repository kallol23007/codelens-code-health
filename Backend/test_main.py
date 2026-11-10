from main import scan_python_file, scan_javascript_file, find_duplicate_blocks


def test_python_scan_returns_maintainability():
    result = scan_python_file("example.py", "def add(a, b):\n    return a + b\n")

    assert result["score"] >= 0
    assert result["maintainability_index"] is not None
    assert result["maintainability_rank"] in {"A", "B", "C"}


def test_javascript_scan_returns_score():
    result = scan_javascript_file("example.js", "function add(a, b) {\n  return a + b;\n}")

    assert result["score"] >= 0
    assert result["functions"] >= 1


def test_duplicate_blocks_are_found():
    sources = {
        "one.py": "first_line()\nsecond_line()\nthird_line()\n",
        "two.py": "first_line()\nsecond_line()\nthird_line()\n",
    }

    duplicates = find_duplicate_blocks(sources)

    assert len(duplicates) == 1