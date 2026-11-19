#!/usr/bin/env python3
"""
Psyche Matrix Framework Linter
------------------------------
Scans drafted prose files or directories for system leaks, psychological jargon,
banned dialogue markers, and repetitive filler phrases.
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# Pre-compile regex patterns for performance optimization
# Define regex patterns for system leaks and psychological jargon
SYSTEM_LEAKS_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"\bRealm (I|II|III|IV|V|VI|VII|VIII|IX|X|\d+)\b", re.IGNORECASE), "Framework Jargon", "Realm [N] references on-page"),
    (re.compile(r"\bFocus Lock\b", re.IGNORECASE), "Framework Jargon", "Focus Lock status leak"),
    (re.compile(r"\bBias State\b", re.IGNORECASE), "Framework Jargon", "Bias State status leak"),
    (re.compile(r"\b(DEFENSIVE_ACTIVE|GENERATIVE_ACTIVE|DORMANT)\b"), "Framework Jargon", "Internal bias activation state leak"),
    (re.compile(r"\btransformation_weights\b", re.IGNORECASE), "Framework Jargon", "transformation_weights leak"),
    (re.compile(r"\btransformation_history\b", re.IGNORECASE), "Framework Jargon", "transformation_history leak"),
    (re.compile(r"\bPrism Distortion\b", re.IGNORECASE), "Framework Jargon", "Prism Distortion engine reference"),
    (re.compile(r"\bGenerative Prism\b", re.IGNORECASE), "Framework Jargon", "Generative Prism engine reference"),
    (re.compile(r"\bGreat Wheel\b", re.IGNORECASE), "Framework Jargon", "Great Wheel reference"),
    (re.compile(r"\b(cognitive_regime|bypassed_reactive|polyvagal_mode|ventral_grounded|sympathetic_mobilized|dorsal_freeze|dissociated_tunnel)\b", re.IGNORECASE), "Engine Circuit & Polyvagal Labels", "Autonomic polyvagal / cognitive regime status leak"),
    (re.compile(r"\b(subconscious_visceral_truth|conscious_rationalization|internal_friction|relational_momentum|relational_ambivalence|sensory_tunneling)\b", re.IGNORECASE), "Engine Inner Split / State Labels", "Inner split / state variable leak"),
    (re.compile(r"\b(mask_strain|mask_fracture|fracture_tell|facade_type)\b", re.IGNORECASE), "Social Mask Engine Labels", "Social mask engine label leak"),
    (re.compile(r"\bdefense_posture\b", re.IGNORECASE), "Defense Posture Engine Labels", "defense_posture engine reference"),
    (re.compile(r"\b(trauma|reframe|coping mechanism|emotional wound|active wound|psychological wound|emotional trigger|psychological trigger|wound trigger|cognitive gift|sacred anchor|virtue lens|self-actualiz\w+|empowerment|safe space|healing journey)\b", re.IGNORECASE), "Psychological Labels (Therapy Speak)", "Psychological/therapy labels (show body instead)"),
    (re.compile(r"\bDebt Ledger\b", re.IGNORECASE), "Engine Bias & Gift Names", "Debt Ledger bias name leak"),
    (re.compile(r"\bSaviour Complex\b", re.IGNORECASE), "Engine Bias & Gift Names", "Saviour Complex bias name leak"),
    (re.compile(r"\bSystem Architect\b", re.IGNORECASE), "Engine Bias & Gift Names", "System Architect bias name leak"),
    (re.compile(r"\bMirror (bias|reflector)\b", re.IGNORECASE), "Engine Bias & Gift Names", "Mirror bias name leak"),
    (re.compile(r"\b(Insulation|Dissolution)\s+(bias|engine|state|mechanism|complex)\b", re.IGNORECASE), "Engine Bias & Gift Names", "Insulation/Dissolution bias name leak"),
    (re.compile(r"\bSacred Stewardship\b", re.IGNORECASE), "Engine Bias & Gift Names", "Sacred Stewardship gift name leak"),
    (re.compile(r"\bTrue Sanctuary\b", re.IGNORECASE), "Engine Bias & Gift Names", "True Sanctuary gift name leak"),
    (re.compile(r"\bIlluminated Symmetry\b", re.IGNORECASE), "Engine Bias & Gift Names", "Illuminated Symmetry gift name leak"),
    (re.compile(r"\bResonant Truth\b", re.IGNORECASE), "Engine Bias & Gift Names", "Resonant Truth gift name leak"),
    (re.compile(r"\bSanctuary Bridge\b", re.IGNORECASE), "Engine Bias & Gift Names", "Sanctuary Bridge gift name leak"),
    (re.compile(r"\bThreshold Vision\b", re.IGNORECASE), "Engine Bias & Gift Names", "Threshold Vision gift name leak"),
    (re.compile(r"\b(look up|database|search the web|search web|as an AI|my database|retriev\w+ records|external search)\b", re.IGNORECASE), "Out-of-Character Lookup / Temporal Leaks", "Out-of-character AI lookup / temporal leak"),
    (re.compile(r"\b(it'?s important to remember|to be fair|let'?s look at this|while that is a common|actually, from a|safety guidelines?|safety protocols?|respectful conversation|inappropriate content|moral perspective|ethical considerations?|cannot fulfill this request)\b", re.IGNORECASE), "AI Safety / Preachy Tone Leaks", "AI safety tone / preachiness / correction leak"),
]

# Pre-compile banned phrases patterns
BANNED_PHRASES_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"\bwhispered\b", re.IGNORECASE), "Dialogue Tags & Markers", "Banned dialogue tag 'whispered'"),
    (re.compile(r"\bAre you okay\??", re.IGNORECASE), "Dialogue Tags & Markers", "Banned dialogue filler 'Are you okay?'"),
    (re.compile(r"\bI understand how you feel\b", re.IGNORECASE), "Dialogue Tags & Markers", "Banned dialogue filler 'I understand how you feel'"),
    (re.compile(r"\bI feel like\b", re.IGNORECASE), "Dialogue Tags & Markers", "Banned dialogue marker 'I feel like'"),
    (re.compile(r"\bsaid quietly\b", re.IGNORECASE), "Dialogue Tags & Markers", "Banned dialogue marker 'said quietly'"),
    (re.compile(r"\bsaid gently\b", re.IGNORECASE), "Dialogue Tags & Markers", "Banned dialogue marker 'said gently'"),
    (re.compile(r"^\s*(A\s+beat|Beat)\.\s*$", re.MULTILINE | re.IGNORECASE), "Pattern Limits", "Banned standalone beat — replace with physical reaction"),
    (re.compile(r"\[(tell|jaw\s+tightens?|blinks?|sighs?|swallows?|somatic)[^\]]*\]", re.IGNORECASE), "Formatting / Somatics", "Bracketed somatic direction — fold tells into prose without brackets"),
    (re.compile(r"\bproximity flag\b", re.IGNORECASE), "Document Bleed", "Document bleed term 'proximity flag'"),
    (re.compile(r"\blooked at\b", re.IGNORECASE), "Filler Phrases (Watchlist)", "Repetitive filler 'looked at'"),
    (re.compile(r"\bfor a moment\b", re.IGNORECASE), "Filler Phrases (Watchlist)", "Repetitive filler 'for a moment'"),
    (re.compile(r"\ba long moment\b", re.IGNORECASE), "Filler Phrases (Watchlist)", "Repetitive filler 'a long moment'"),
    (re.compile(r"\bgenuinely\b", re.IGNORECASE), "Filler Phrases (Watchlist)", "Repetitive filler 'genuinely'"),
    (re.compile(r"\balready\b", re.IGNORECASE), "Filler Phrases (Watchlist)", "Watchlist repetition 'already'"),
    (re.compile(r"\b(wound|trigger|mirror|gift|virtue|insulation|dissolution)\b", re.IGNORECASE), "Contextual Watchlist (Warning Only)", "Watchlist term (verify context does not leak framework/therapy jargon)"),
]

# Continuous action separators rule
ACTION_SEPARATORS = re.compile(r"^---$")

def audit_file(filepath: str) -> List[Dict[str, Any]]:
    """Audits a single file and returns a list of findings."""
    findings: List[Dict[str, Any]] = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        return [{"line": 0, "type": "Error", "message": f"Could not read file: {e}"}]
        
    hr_count = 0
    
    # First, let's detect if frontmatter is present at the start of the file
    has_frontmatter = len(lines) > 0 and lines[0].strip() == "---"
    frontmatter_end_line = -1
    
    if has_frontmatter:
        # Search for the closing '---'
        for line_idx in range(1, len(lines)):
            if lines[line_idx].strip() == "---":
                frontmatter_end_line = line_idx + 1 # 1-indexed
                break
                
    for line_idx, line in enumerate(lines, start=1):
        # Handle YAML frontmatter (skip checking leaks/fillers in headers)
        if has_frontmatter:
            if frontmatter_end_line != -1:
                if line_idx <= frontmatter_end_line:
                    # Skip all checks inside frontmatter
                    # Frontmatter '---' delimiters are NOT continuous action breaks
                    continue
            else:
                # Malformed frontmatter (never closed)
                if line_idx == 1:
                    findings.append({
                        "line": 1,
                        "type": "Formatting Violation",
                        "category": "YAML Frontmatter",
                        "match": "---",
                        "message": "Malformed YAML frontmatter. The opening '---' was never closed."
                    })
                # If malformed, we check everything except line 1
                if line.strip() == "---" and line_idx > 1:
                    hr_count += 1
                    
        # Check for horizontal rules using compiled ACTION_SEPARATORS
        if ACTION_SEPARATORS.match(line.strip()):
            hr_count += 1
            
        if has_frontmatter and frontmatter_end_line != -1 and line_idx <= frontmatter_end_line:
            continue
            
        # 1. Audit System Leaks (using pre-compiled patterns)
        critical_spans = []
        for compiled_pattern, category, desc in SYSTEM_LEAKS_PATTERNS:
            matches = compiled_pattern.finditer(line)
            for match in matches:
                critical_spans.append(match.span())
                findings.append({
                    "line": line_idx,
                    "type": "System Leak",
                    "category": category,
                    "match": match.group(0),
                    "message": desc
                })
                    
        # 2. Audit Banned Phrases (using pre-compiled patterns)
        for compiled_pattern, category, desc in BANNED_PHRASES_PATTERNS:
            matches = compiled_pattern.finditer(line)
            for match in matches:
                # Avoid overlapping warning findings if the text is already flagged as a critical leak
                start, end = match.span()
                if any(c_start <= start < c_end or c_start < end <= c_end for c_start, c_end in critical_spans):
                    continue
                findings.append({
                    "line": line_idx,
                    "type": "Banned/Filler Phrase",
                    "category": category,
                    "match": match.group(0),
                    "message": desc
                })
                    
    # 3. Check for excess horizontal rules (excluding frontmatter)
    actual_hr_count = hr_count
    # Frontmatter '---' lines are not counted in hr_count, so no adjustment needed
    
    if actual_hr_count > 2:
        findings.append({
            "line": 0,
            "type": "Formatting Violation",
            "category": "Continuous Action Break",
            "match": "---",
            "message": f"Found {actual_hr_count} horizontal rules. Rules must never separate continuous real-time action (use standard paragraph breaks instead)."
        })
        
    return findings

DOC_FILES = {
    "README.md",
    "CHANGELOG.md",
    "PROJECT_SCOPE.md",
    "OPTIMIZATION_SUMMARY.md",
    "DISCLAIMER.md",
    "LICENSE",
}

IGNORED_DIR_NAMES = {
    ".git",
    ".system_generated",
    "__pycache__",
    "Characters",
    "Framework",
    "Simulator",
    "Images",
    "Releases",
    "Build",
    "Research",
    "node_modules",
    ".obsidian",
}


def audit_directory(path: str, extensions: Optional[List[str]] = None) -> Tuple[Dict[str, List[Dict[str, Any]]], int]:
    """Recursively audits a directory for matching file extensions.
    Returns a tuple: (results_dict, audited_count)"""
    if extensions is None:
        extensions = [".md", ".txt"]
        
    results: Dict[str, List[Dict[str, Any]]] = {}
    audited_count: int = 0
    for root, dirs, files in os.walk(path):
        # Prune ignored directories from traversal
        dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
        rel_root = os.path.relpath(root, path)
        root_parts = rel_root.split(os.path.sep)
        if any(ignored in root_parts for ignored in IGNORED_DIR_NAMES):
            continue
        for file in files:
            if file in DOC_FILES or file.startswith("_template") or file.startswith("."):
                continue
            if any(file.endswith(ext) for ext in extensions):
                filepath = os.path.join(root, file)
                audited_count += 1
                findings = audit_file(filepath)
                if findings:
                    results[filepath] = findings
    return results, audited_count


def main():
    parser = argparse.ArgumentParser(description="Psyche Matrix Prose Linter")
    parser.add_argument("target", help="File or directory path to audit")
    parser.add_argument("--ext", help="File extensions to scan (comma-separated, default: .md,.txt)", default=".md,.txt")
    parser.add_argument("--only-critical", action="store_true", help="Report only critical system leaks")
    parser.add_argument("--broadcast", action="store_true", help="Also check broadcast skit constraints (banned openers, clinical drill leaks)")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    target_path = os.path.abspath(args.target)
    if not os.path.exists(target_path):
        print(f"Error: Target path does not exist: {target_path}", file=sys.stderr)
        sys.exit(1)

    extensions = [ext.strip() if ext.startswith('.') else f".{ext.strip()}" for ext in args.ext.split(',')]

    total_findings = 0
    file_count = 0
    has_critical = False
    files_with_findings = 0

    if os.path.isdir(target_path):
        results, audited_count = audit_directory(target_path, extensions)
        file_count = audited_count
    else:
        file_count = 1
        findings = audit_file(target_path)
        results = {target_path: findings} if findings else {}

    if args.broadcast:
        bc_patterns = [
            (re.compile(r'(^|["“])\s*Of course\.', re.IGNORECASE), "Broadcast Style", "Banned 'Of course.' opener"),
            (re.compile(r'\b(exact deficit|mechanics under repetition|repeat the baseline|center-rail|execute one|inventory|curriculum)\b', re.IGNORECASE), "Broadcast Register Leak", "Clinical/corporate/trainer diction in broadcast skit"),
            (re.compile(r'\bunhurried\b', re.IGNORECASE), "Broadcast Filler", "Overused card-parroted adjective 'unhurried'"),
        ]
        targets = list(results.keys()) if os.path.isdir(target_path) else [target_path]
        for fp in targets:
            with open(fp, "r", encoding="utf-8") as f_bc:
                for idx_bc, line_bc in enumerate(f_bc, 1):
                    for pat, cat, msg in bc_patterns:
                        m_bc = pat.search(line_bc)
                        if m_bc:
                            results.setdefault(fp, []).append({"line": idx_bc, "type": "Broadcast Constraint", "category": cat, "match": m_bc.group(0), "message": msg})

    filtered_results: Dict[str, List[Dict[str, Any]]] = {}
    for filepath, findings in results.items():
        if args.only_critical:
            f_list = [f for f in findings if f.get("type") == "System Leak"]
        else:
            f_list = findings
        if f_list:
            filtered_results[filepath] = f_list
            total_findings += len(f_list)
            if any(f.get("type") in ("System Leak", "Broadcast Constraint") for f in f_list):
                has_critical = True

    files_with_findings = len(filtered_results)

    if args.json:
        import json
        payload = {
            "target": target_path,
            "audited_files": file_count,
            "files_with_findings": files_with_findings,
            "total_findings": total_findings,
            "has_critical_leaks": has_critical,
            "results": filtered_results,
        }
        print(json.dumps(payload, indent=2))
        sys.exit(1 if has_critical else 0)

    print("==================================================")
    print("      Psyche Matrix Framework Prose Linter        ")
    print("==================================================")
    print(f"Scanning target: {target_path}")
    print(f"Extensions: {', '.join(extensions)}")
    print("--------------------------------------------------")

    for filepath, findings in filtered_results.items():
        rel_path = os.path.relpath(filepath, target_path) if os.path.isdir(target_path) else os.path.basename(filepath)
        print(f"\n[!] File: {rel_path} ({len(findings)} findings)")
        for f in findings:
            line_str = f"Line {f['line']}" if f['line'] > 0 else "File-level"
            print(f"    - {line_str} | [{f['type']}] ({f['category']}): Found '{f['match']}' -> {f['message']}")

    print("\n--------------------------------------------------")
    findings_context = f" ({files_with_findings} file(s) with findings)" if files_with_findings > 0 else ""
    print(f"Scan complete. Audited {file_count} file(s){findings_context} with {total_findings} total finding(s).")

    if total_findings > 0:
        if has_critical:
            print("[STATUS] FAIL: Critical system leaks detected. Cleanup required before saving.")
            sys.exit(1)
        else:
            print("[STATUS] WARNING: Non-critical filler/banned phrases detected.")
            sys.exit(0)
    else:
        print("[STATUS] PASS: Prose is clean and compliant with framework standards.")
        sys.exit(0)

if __name__ == "__main__":
    main()
