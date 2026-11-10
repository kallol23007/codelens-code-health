import ast
import io
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from radon.metrics import mi_visit, mi_rank

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="CodeLens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "scans.db"

MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 100 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000
MAX_SOURCE_FILE_BYTES = 1_000_000

SKIPPED_FOLDERS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
}


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                grade TEXT NOT NULL,
                score INTEGER NOT NULL,
                files_scanned INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


init_db()


def calculate_file_score(
    complexity: int,
    line_count: int,
    smells: list,
    maintainability_index=None,
) -> dict:
    complexity_penalty = max(0, complexity - 5) * 5
    size_penalty = max(0, line_count - 100) // 2
    smell_penalty = min(len(smells) * 5, 20)

    maintainability_penalty = 0
    if maintainability_index is not None and maintainability_index < 65:
        maintainability_penalty = round((65 - maintainability_index) / 3)

    score_reasons = []
    if complexity_penalty:
        score_reasons.append(f"Complexity penalty: -{complexity_penalty}")
    if size_penalty:
        score_reasons.append(f"File size penalty: -{size_penalty}")
    if smell_penalty:
        score_reasons.append(f"Code smell penalty: -{smell_penalty}")
    if maintainability_penalty:
        score_reasons.append(
            f"Low maintainability penalty: -{maintainability_penalty}"
        )
    if not score_reasons:
        score_reasons.append("No score penalties")

    score = max(
        0,
        100 - complexity_penalty - size_penalty
        - smell_penalty - maintainability_penalty,
    )

    return {"score": score, "score_reasons": score_reasons}

def scan_python_file(path: str, source: str) -> dict:
    lines = source.splitlines()
    smells = []

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return {
            "file": path,
            "lines": len(lines),
            "functions": 0,
            "complexity": 0,
            "maintainability_index": None,
            "maintainability_rank": "N/A",
            "issue": f"Syntax error on line {error.lineno}",
            "smells": ["File has a syntax error"],
            "score_reasons": ["Syntax error: score is 0"],
            "score": 0,
        }
    maintainability_index = round(mi_visit(source, multi=True), 1)
    maintainability_rank = mi_rank(maintainability_index)

    functions = 0
    complexity = 1

    branches = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.ExceptHandler,
        ast.IfExp,
        ast.Assert,
    )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions += 1

        if isinstance(node, branches):
            complexity += 1

        if isinstance(node, ast.BoolOp):
            complexity += max(0, len(node.values) - 1)

    if len(lines) > 200:
        smells.append("Long file: more than 200 lines")

    if complexity > 10:
        smells.append("High complexity: code has many branches")

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_lines = (node.end_lineno or node.lineno) - node.lineno + 1

            if function_lines > 40:
                smells.append(
                    f"Long function '{node.name}': {function_lines} lines"
                )

    scoring = calculate_file_score(
    complexity,
    len(lines),
    smells,
    maintainability_index,)

    return {
        "file": path,
        "lines": len(lines),
        "functions": functions,
        "complexity": complexity,
        "maintainability_index": maintainability_index,
        "maintainability_rank": maintainability_rank,
        "issue": None,
        "smells": smells or ["No major code smells found"],
        "score_reasons": scoring["score_reasons"],
        "score": scoring["score"],
    }


def scan_javascript_file(path: str, source: str) -> dict:
    lines = source.splitlines()

    function_pattern = (
        r"\bfunction\s+\w+"
        r"|\b(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\("
    )
    functions = len(re.findall(function_pattern, source))

    branch_pattern = r"\b(if|for|while|catch|case)\b|&&|\|\||\?"
    complexity = 1 + len(re.findall(branch_pattern, source))

    smells = []

    if len(lines) > 200:
        smells.append("Long file: more than 200 lines")

    if complexity > 10:
        smells.append("High complexity: code has many branches")

    scoring = calculate_file_score(complexity, len(lines), smells)

    return {
        "file": path,
        "lines": len(lines),
        "functions": functions,
        "complexity": complexity,
        "issue": None,
        "smells": smells or ["No major code smells found"],
        "score_reasons": scoring["score_reasons"],
        "score": scoring["score"],
    }


def find_duplicate_blocks(source_files: dict) -> list:
    found = {}

    for path, source in source_files.items():
        useful_lines = []

        for number, line in enumerate(source.splitlines(), start=1):
            text = line.strip()

            if not text:
                continue

            if text.startswith("#") or text.startswith("//"):
                continue

            useful_lines.append((number, text))

        for index in range(len(useful_lines) - 2):
            block_lines = useful_lines[index:index + 3]
            block = tuple(text for _, text in block_lines)

            if any(len(line) < 8 for line in block):
                continue

            found.setdefault(block, []).append(
                {
                    "file": path,
                    "line": block_lines[0][0],
                }
            )

    return [
        {
            "code": "\n".join(block),
            "locations": locations,
        }
        for block, locations in found.items()
        if len(locations) > 1
    ][:10]


@app.get("/")
def home():
    return {"message": "CodeLens backend is running"}


@app.post("/upload")
async def upload_project(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a ZIP file.",
        )

    contents = await file.read(MAX_ZIP_BYTES + 1)

    if len(contents) > MAX_ZIP_BYTES:
        raise HTTPException(
            status_code=413,
            detail="ZIP file must be smaller than 20 MB.",
        )

    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            members = archive.infolist()

            if len(members) > MAX_ZIP_ENTRIES:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP contains too many files.",
                )

            total_size = sum(
                item.file_size
                for item in members
                if not item.is_dir()
            )

            if total_size > MAX_UNPACKED_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP unpacked size is too large.",
                )

            for item in members:
                name = item.filename.replace("\\", "/")
                parts = name.split("/")

                if (
                    name.startswith("/")
                    or (parts and ":" in parts[0])
                    or ".." in parts
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="ZIP contains an unsafe file path.",
                    )

            code_files = [
                item
                for item in members
                if item.filename.lower().endswith((".py", ".js"))
                and not item.is_dir()
                and not any(
                    folder in SKIPPED_FOLDERS
                    for folder in (
                        item.filename.lower()
                        .replace("\\", "/")
                        .split("/")
                    )
                )
            ]

            results = []
            source_files = {}

            for item in code_files:
                if item.file_size > MAX_SOURCE_FILE_BYTES:
                    continue

                source = archive.read(item).decode(
                    "utf-8",
                    errors="replace",
                )
                source_files[item.filename] = source

                if item.filename.lower().endswith(".py"):
                    results.append(scan_python_file(item.filename, source))
                else:
                    results.append(
                        scan_javascript_file(item.filename, source)
                    )

    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="That file is not a valid ZIP.",
        )

    if not results:
        raise HTTPException(
            status_code=400,
            detail="No Python (.py) or JavaScript (.js) files found in ZIP.",
        )
    mi_values = [
    row["maintainability_index"]
    for row in results
    if row.get("maintainability_index") is not None
]
    average_maintainability = (
        round(sum(mi_values) / len(mi_values), 1)
        if mi_values
        else None
)

    duplicates = find_duplicate_blocks(source_files)
    duplicate_penalty = min(len(duplicates) * 5, 20)

    project_score_reasons = []

    if duplicate_penalty:
        project_score_reasons.append(
            f"Duplicate code penalty: -{duplicate_penalty}"
        )
    else:
        project_score_reasons.append("No duplicate code penalty")

    average_score = max(
        0,
        round(sum(row["score"] for row in results) / len(results))
        - duplicate_penalty,
    )

    grade = (
        "A" if average_score >= 90
        else "B" if average_score >= 80
        else "C" if average_score >= 70
        else "D" if average_score >= 60
        else "F"
    )

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.execute(
            """
            INSERT INTO scans (
                filename, grade, score, files_scanned, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                file.filename,
                grade,
                average_score,
                len(results),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        scan_id = cursor.lastrowid

    return {
        "scan_id": scan_id,
        "filename": file.filename,
        "grade": grade,
        "score": average_score,
        "maintainability_index": average_maintainability,
        "files_scanned": len(results),
        "total_lines": sum(row["lines"] for row in results),
        "total_functions": sum(row["functions"] for row in results),
        "duplicates": duplicates,
        "project_score_reasons": project_score_reasons,
        "files": sorted(results, key=lambda row: row["score"]),
    }


@app.get("/history")
def get_history():
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT * FROM scans ORDER BY id DESC LIMIT 10"
        ).fetchall()

    return [dict(row) for row in rows]