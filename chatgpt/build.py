#!/usr/bin/env python3
"""Build cro-autopilot-chatgpt.zip, the ChatGPT upload of the CRO Autopilot skill.

The Claude plugin's skill folder stays the single source. This script copies it,
swaps the few Claude-specific lines for ChatGPT ones, adds references/chatgpt.md
(memory, scheduling, phrases instead of slash commands) and agents/openai.yaml,
checks the SKILL.md front matter against the Agent Skills spec, and zips one
top-level cro-autopilot/ folder (OpenAI's skill upload format).

Every swap must match exactly once: if the source text changes, the build fails
instead of shipping a stale ChatGPT version.

Usage: python3 chatgpt/build.py
"""
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKILL_DIR = ROOT / "perspective-cro-autopilot" / "skills" / "cro-autopilot"
OUT = ROOT / "cro-autopilot-chatgpt.zip"
EXCLUDE = {"evals", "__pycache__", ".DS_Store"}

CLIENT_MODE = "references/client-mode.md"
SWAPS = [
    ("SKILL.md",
     "or invokes /cro-weekly, /cro-setup, /cro-report or /cro-rollout.",
     "or asks to set up or schedule CRO Autopilot."),
    ("SKILL.md",
     "https://intercom.help/perspective-funnels/en/articles/15374243-how-to-connect-perspective-mcp-with-claude",
     "https://intercom.help/perspective-funnels/en/articles/15533402-how-to-connect-perspective-mcp-in-chatgpt"),
    ("SKILL.md",
     "in the working directory (create it on first run; recommend a dedicated folder or repo so the log survives):",
     "in the working directory (create it on first run). In ChatGPT the working directory may not outlive the chat: "
     "`references/chatgpt.md` says where the memory lives and how it carries over to next week. Read it before step 0 of every run:"),
    ("SKILL.md", "## First run (/cro-setup)", "## First run (setup)"),
    ("SKILL.md",
     "| `references/client-mode.md` | client reports and rollouts |",
     "| `references/client-mode.md` | client reports and rollouts |\n"
     "| `references/chatgpt.md` | the start and end of every run: where the memory lives, weekly scheduling, what the user's words map to |"),
    (CLIENT_MODE,
     "build an HTML artifact from the same content (load the `artifact-design` skill first); give the user the link to pass on",
     "build a self-contained HTML file from the same content and give it to the user to pass on"),
    (CLIENT_MODE, "Trigger: `/cro-rollout`, or the user says", "Trigger: the user says"),
    (CLIENT_MODE, " (`AskUserQuestion` when available, otherwise a lettered list)", " (a lettered list)"),
]
# Claude-only text that must never reach the ChatGPT package, also when it is added to the source later.
DENY = re.compile(r"/cro-|AskUserQuestion|artifact|claude", re.I)
EXTRA = {
    "references/chatgpt.md": HERE / "chatgpt.md",
    "agents/openai.yaml": HERE / "openai.yaml",
}


def package_files():
    """Map each package path (relative to the skill folder) to its bytes."""
    files = {
        p.relative_to(SKILL_DIR).as_posix(): p.read_bytes()
        for p in sorted(SKILL_DIR.rglob("*"))
        if p.is_file() and not EXCLUDE & set(p.relative_to(SKILL_DIR).parts)
    }
    for rel, old, new in SWAPS:
        text = files[rel].decode("utf-8")
        if text.count(old) != 1:
            sys.exit(f"build failed: expected exactly one match in {rel} for: {old[:70]}")
        files[rel] = text.replace(old, new).encode("utf-8")
    for rel, src in EXTRA.items():
        files[rel] = src.read_bytes()
    for rel, data in files.items():
        if rel.endswith(".md") and (hit := DENY.search(data.decode("utf-8"))):
            sys.exit(f"build failed: Claude-only text {hit.group(0)!r} left in {rel}; add a swap for it")
    return files


def check_front_matter(skill_md):
    """Agent Skills spec: name 1-64 chars of a-z0-9 and single hyphens, equal to the folder; description 1-1024 chars."""
    match = re.match(r"---\n(.*?)\n---\n", skill_md, re.S)
    if not match:
        sys.exit("build failed: SKILL.md has no front matter")
    fields = dict(re.findall(r'^(\w[\w-]*):\s*"?(.*?)"?\s*$', match.group(1), re.M))
    name, description = fields.get("name", ""), fields.get("description", "")
    if name != SKILL_DIR.name or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(name) > 64:
        sys.exit(f"build failed: bad skill name {name!r}")
    if not 1 <= len(description) <= 1024:
        sys.exit(f"build failed: description is {len(description)} characters (1-1024 allowed)")


def main():
    files = package_files()
    check_front_matter(files["SKILL.md"].decode("utf-8"))
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in sorted(files):
            # Fixed timestamp and modes so a rebuild of the same sources gives the same zip.
            info = zipfile.ZipInfo(f"{SKILL_DIR.name}/{rel}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if rel.startswith("scripts/") else 0o644) << 16
            zf.writestr(info, files[rel])
    print(f"wrote {OUT.relative_to(ROOT)} ({len(files)} files)")


if __name__ == "__main__":
    main()
