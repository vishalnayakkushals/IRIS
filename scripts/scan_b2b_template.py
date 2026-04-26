#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanResult:
    template_root: str
    sop_docx: str
    total_files: int
    total_dirs: int
    extension_counts: dict[str, int]
    key_paths: dict[str, bool]
    sop_sections_found: list[str]
    recommended_now: list[str]
    recommended_future: list[str]


def _extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", "ignore")
    text = " ".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml))
    return text


def _scan_template(root: Path) -> tuple[int, int, Counter[str], dict[str, bool]]:
    files = [p for p in root.rglob("*") if p.is_file()]
    dirs = [p for p in root.rglob("*") if p.is_dir()]
    ext = Counter((p.suffix.lower() or "<no_ext>") for p in files)

    key_paths = {
        "README.md": any(p.name.lower() == "readme.md" for p in files),
        ".gitignore": any(p.name == ".gitignore" for p in files),
        "backend/package.json": any(
            str(p).replace("\\", "/").lower().endswith("backend/package.json") for p in files
        ),
        "frontend/package.json": any(
            str(p).replace("\\", "/").lower().endswith("frontend/package.json") for p in files
        ),
        "backend env examples": any(
            p.name in {".env.local.example", ".env.production.example"}
            and "backend" in str(p).replace("\\", "/").lower()
            for p in files
        ),
        "frontend env examples": any(
            p.name in {".env.local.example", ".env.production.example"}
            and "frontend" in str(p).replace("\\", "/").lower()
            for p in files
        ),
    }
    return len(files), len(dirs), ext, key_paths


def _find_sop_sections(text: str) -> list[str]:
    checks = [
        "Mandatory Branching",
        "Pull Request",
        "Deployment Process",
        "Environment & Secrets",
        "Database Management",
        "User Access & Roles",
        "Non-Negotiable Rules",
    ]
    return [c for c in checks if c.lower() in text.lower()]


def run_scan(template_root: Path, sop_docx: Path) -> ScanResult:
    total_files, total_dirs, ext, key_paths = _scan_template(template_root)
    sop_text = _extract_docx_text(sop_docx)
    sop_sections = _find_sop_sections(sop_text)

    recommended_now = [
        "Keep SOP checklist and template scan report under docs/process for team onboarding.",
        "Reuse PR checklist/branching rules in existing GitHub workflow and AGENTS guidance.",
        "Keep template as external reference only (do not merge Node modules/frontend dist into IRIS).",
    ]
    recommended_future = [
        "If required, create a separate B2B service repo from template instead of mixing with IRIS runtime.",
        "Implement org-level branch protections and reviewer gates for SOP enforcement.",
        "Add infra-level backup/restore drill automation if moving to shared production standards.",
    ]

    return ScanResult(
        template_root=str(template_root),
        sop_docx=str(sop_docx),
        total_files=total_files,
        total_dirs=total_dirs,
        extension_counts=dict(ext.most_common(20)),
        key_paths=key_paths,
        sop_sections_found=sop_sections,
        recommended_now=recommended_now,
        recommended_future=recommended_future,
    )


def _write_markdown(result: ScanResult, out_md: Path) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# B2B Template Scan & Incorporation Report")
    lines.append("")
    lines.append(f"- Template root: `{result.template_root}`")
    lines.append(f"- SOP docx: `{result.sop_docx}`")
    lines.append(f"- Total files: `{result.total_files}`")
    lines.append(f"- Total directories: `{result.total_dirs}`")
    lines.append("")
    lines.append("## Key Path Presence")
    lines.append("| Item | Present |")
    lines.append("|---|---|")
    for k, v in result.key_paths.items():
        lines.append(f"| {k} | {'Yes' if v else 'No'} |")
    lines.append("")
    lines.append("## Top Extensions (20)")
    lines.append("| Extension | Count |")
    lines.append("|---|---:|")
    for ext, cnt in result.extension_counts.items():
        lines.append(f"| {ext} | {cnt} |")
    lines.append("")
    lines.append("## SOP Sections Found")
    for section in result.sop_sections_found:
        lines.append(f"- {section}")
    lines.append("")
    lines.append("## Incorporated Now")
    for item in result.recommended_now:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Future Scope")
    for item in result.recommended_future:
        lines.append(f"- {item}")
    lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan external B2B template and SOP for IRIS incorporation planning.")
    parser.add_argument("--template-root", required=True, help="Path to the b2b template root folder.")
    parser.add_argument("--sop-docx", required=True, help="Path to B2B SOP docx.")
    parser.add_argument(
        "--out-json",
        default="docs/process/b2b_template_scan_report.json",
        help="Output JSON path (repo-relative or absolute).",
    )
    parser.add_argument(
        "--out-md",
        default="docs/process/b2b_template_scan_report.md",
        help="Output markdown path (repo-relative or absolute).",
    )
    args = parser.parse_args()

    template_root = Path(args.template_root).expanduser().resolve()
    sop_docx = Path(args.sop_docx).expanduser().resolve()
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)

    if not template_root.exists():
        raise FileNotFoundError(f"Template root not found: {template_root}")
    if not sop_docx.exists():
        raise FileNotFoundError(f"SOP docx not found: {sop_docx}")

    result = run_scan(template_root=template_root, sop_docx=sop_docx)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result.__dict__, indent=2), encoding="utf-8")
    _write_markdown(result=result, out_md=out_md)

    print("B2B template scan complete.")
    print(f"JSON: {out_json}")
    print(f"MD:   {out_md}")


if __name__ == "__main__":
    main()
