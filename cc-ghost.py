#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "anthropic",
#     "python-dotenv",
# ]
# ///
"""
cc-ghost — Claude Code Session Digest for Social Media
Reads ~/.claude/projects/ JSONL files, summarizes what you built,
and generates ready-to-copy social posts.

Usage:
  uv run cc-ghost.py                    # last 7 days, all projects
  uv run cc-ghost.py --project          # pick a project (all sessions)
  uv run cc-ghost.py --days 14          # last 14 days
  uv run cc-ghost.py --dry-run          # show sessions found, no API call
  uv run cc-ghost.py --setup            # create/redo persona
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
import anthropic

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
PERSONA_PATH = SCRIPT_DIR / "persona.md"
POSTS_DIR = SCRIPT_DIR / "posts"
LAST_RUN_PATH = SCRIPT_DIR / ".last_run"

DEFAULT_MODEL = os.getenv("CC_GHOST_MODEL", "claude-haiku-4-5-20251001")

# How many user messages to sample per session (keeps tokens low)
SAMPLE_MESSAGES_PER_SESSION = 12

# How many recent published posts to feed as style examples
PAST_POSTS_LIMIT = 10

# ── ANSI Colors ────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
PURPLE = "\033[35m"
TEAL   = "\033[36m"
AMBER  = "\033[33m"
GREEN  = "\033[32m"
GRAY   = "\033[90m"


# ── Last Run ──────────────────────────────────────────────────────────────────

def load_last_run() -> datetime | None:
    """Read the last-run timestamp from .last_run, or None if missing."""
    if not LAST_RUN_PATH.exists():
        return None
    try:
        text = LAST_RUN_PATH.read_text(encoding="utf-8").strip()
        return datetime.fromisoformat(text)
    except (ValueError, OSError):
        return None


def save_last_run(dt: datetime) -> None:
    """Write the last-run timestamp to .last_run."""
    LAST_RUN_PATH.write_text(dt.isoformat() + "\n", encoding="utf-8")


# ── Persona ────────────────────────────────────────────────────────────────────

def load_persona() -> str:
    """Load persona.md and return its contents."""
    if not PERSONA_PATH.exists():
        return ""
    return PERSONA_PATH.read_text(encoding="utf-8").strip()


def setup_persona():
    """Interactive first-run setup that creates persona.md."""
    print(f"\n{BOLD}cc-ghost setup{RESET}\n")
    print("  Let's set up your ghostwriter persona.\n")

    print(f"  {BOLD}1. Voice{RESET} — Who are you? What do you build? What's your tone?")
    print(f"  {DIM}(A few sentences. Press Enter twice when done.){RESET}\n")
    voice_lines = []
    while True:
        line = input("    ")
        if not line and voice_lines and not voice_lines[-1]:
            voice_lines.pop()
            break
        voice_lines.append(line)
    voice = "\n".join(voice_lines).strip()

    print(f"\n  {BOLD}2. Rules{RESET} — What should the ghostwriter always/never do?")
    print(f"  {DIM}(One rule per line. Press Enter twice when done.){RESET}\n")
    rules = []
    while True:
        line = input("    ")
        if not line and rules and not rules[-1]:
            rules.pop()
            break
        rules.append(line)
    rules_text = "\n".join(f"- {r}" if r and not r.startswith("-") else r for r in rules).strip()

    print(f"\n  {BOLD}3. Sample posts{RESET} — Paste 3-5 real posts you've written.")
    print(f"  {DIM}(Paste one post, press Enter twice, repeat. Empty to finish.){RESET}\n")
    samples = []
    while True:
        sample_lines = []
        while True:
            line = input("    ")
            if not line and sample_lines and not sample_lines[-1]:
                sample_lines.pop()
                break
            if not line and not sample_lines:
                break
            sample_lines.append(line)
        if not sample_lines:
            break
        samples.append("\n".join(sample_lines).strip())

    # Build persona.md
    lines = ["# Persona", "", "## Voice", "", "```", voice, "```", ""]
    lines += ["## Rules", "", rules_text, ""]
    if samples:
        lines += ["", "## Samples", ""]
        for s in samples:
            lines += ["```", s, "```", ""]

    PERSONA_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  {GREEN}Saved:{RESET} {PERSONA_PATH}")
    print(f"  {DIM}Edit this file anytime to adjust your voice.{RESET}\n")


# ── Past Posts ─────────────────────────────────────────────────────────────────

def load_past_posts(limit: int = PAST_POSTS_LIMIT) -> list[str]:
    """Load the most recent published posts from posts/ as style examples."""
    if not POSTS_DIR.exists():
        return []

    # All .md files across project subfolders, newest first by filename
    files = sorted(POSTS_DIR.rglob("*.md"), key=lambda f: f.name, reverse=True)[:limit]
    posts = []
    for f in files:
        content = f.read_text(encoding="utf-8").strip()
        # Strip markdown heading — just get the post body
        lines = content.split("\n")
        body_lines = []
        for line in lines:
            if line.startswith("# ") and not body_lines:
                continue  # skip title
            if line.strip() == "---":
                break  # stop before metadata
            body_lines.append(line)
        body = "\n".join(body_lines).strip()
        if body:
            project = f.parent.name if f.parent != POSTS_DIR else ""
            prefix = f"[{project}] " if project else ""
            posts.append(f"{prefix}{body}")

    return posts


# ── JSONL Parsing ───────────────────────────────────────────────────────────────

def _project_name_from_folder(folder_name: str) -> str:
    """Derive a readable project name from a Claude projects folder name.
    e.g. '-Users-michael-Documents-Development-XCode-DiskBuddy' → 'DiskBuddy'
    """
    parts = folder_name.lstrip("-").split("-")
    # Common path segments that aren't the project name
    noise = {
        "users", "home", "usr", "private", "var", "volumes",
        "documents", "development", "developer", "dev",
        "projects", "repos", "src", "code", "workspace",
        "xcode", "web", "python", "swift", "go", "rust",
        "playground",
    }
    # Drop all noise words and the username (first non-noise word)
    clean = []
    skipped_username = False
    for p in parts:
        if p.lower() in noise:
            continue
        if not skipped_username:
            skipped_username = True
            continue
        clean.append(p)
    return "-".join(clean) if clean else folder_name


def parse_session(filepath: Path) -> dict | None:
    """Parse a single .jsonl session file. Returns None if empty/unparseable."""
    messages = []
    first_ts = None
    last_ts = None
    cwd = None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_raw = event.get("timestamp")
                if ts_raw:
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts
                    except ValueError:
                        pass

                if cwd is None:
                    cwd = event.get("cwd")

                msg_type = event.get("type")
                msg = event.get("message", {})
                role = msg.get("role") if isinstance(msg, dict) else None

                # Collect user messages only (what you typed / what you asked)
                if msg_type == "user" and role == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        # Extract text parts
                        text_parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                        content = " ".join(text_parts)
                    if isinstance(content, str) and content.strip():
                        messages.append(content.strip())

    except (OSError, PermissionError):
        return None

    if not messages or first_ts is None:
        return None

    # Derive project name from the .claude/projects folder name
    # (consistent with project discovery in main)
    project = _project_name_from_folder(filepath.parent.name)

    return {
        "file": str(filepath),
        "project": project,
        "started_at": first_ts,
        "ended_at": last_ts,
        "duration_min": int((last_ts - first_ts).total_seconds() / 60) if last_ts else 0,
        "message_count": len(messages),
        "sampled_messages": messages[:SAMPLE_MESSAGES_PER_SESSION],
    }


def _parse_sessions_index(index_path: Path, from_dt: datetime, to_dt: datetime) -> list[dict]:
    """Parse a sessions-index.json file and return sessions within the date range.

    This handles newer Claude Code versions where .jsonl files may no longer
    exist at the top level — the index has enough metadata (firstPrompt,
    summary, timestamps) to generate posts from.
    """
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    entries = data.get("entries", [])
    sessions = []
    for entry in entries:
        # Parse created timestamp
        created_raw = entry.get("created")
        if not created_raw:
            continue
        try:
            created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except ValueError:
            continue

        if not (from_dt <= created <= to_dt):
            continue

        # Parse modified timestamp
        modified = created
        modified_raw = entry.get("modified")
        if modified_raw:
            try:
                modified = datetime.fromisoformat(modified_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Skip if the .jsonl file exists — parse_session will handle it
        full_path = Path(entry.get("fullPath", ""))
        if full_path.exists():
            continue

        # Derive project name from folder name (consistent with parse_session)
        project = _project_name_from_folder(index_path.parent.name)

        # Use firstPrompt and summary as the message content
        messages = []
        first_prompt = entry.get("firstPrompt", "")
        if first_prompt:
            messages.append(first_prompt.strip())
        summary = entry.get("summary", "")
        if summary:
            messages.append(f"[session summary: {summary}]")

        if not messages:
            continue

        sessions.append({
            "file": str(full_path),
            "project": project,
            "started_at": created,
            "ended_at": modified,
            "duration_min": int((modified - created).total_seconds() / 60),
            "message_count": entry.get("messageCount", len(messages)),
            "sampled_messages": messages,
        })

    return sessions


def load_sessions(from_dt: datetime, to_dt: datetime, project_folders: list[Path] | None = None) -> list[dict]:
    """Load all sessions within the date range.

    When project_folders is provided, only glob those dirs instead of
    scanning everything under CLAUDE_PROJECTS_DIR.

    Sessions are loaded from .jsonl files first, then from sessions-index.json
    as a fallback for newer Claude Code versions where .jsonl files may not
    exist at the top level.
    """
    if not CLAUDE_PROJECTS_DIR.exists():
        print(f"[error] Claude projects directory not found: {CLAUDE_PROJECTS_DIR}")
        print("Make sure you have Claude Code installed and have used it at least once.")
        return []

    dirs = project_folders if project_folders else [
        d for d in CLAUDE_PROJECTS_DIR.iterdir() if d.is_dir()
    ]

    sessions = []

    for d in dirs:
        # 1. Parse top-level .jsonl files (older format)
        for f in sorted(d.glob("*.jsonl")):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < from_dt or mtime > to_dt:
                continue

            session = parse_session(f)
            if session is None:
                continue

            if from_dt <= session["started_at"] <= to_dt:
                sessions.append(session)

        # 2. Parse sessions-index.json (newer format, fallback for missing .jsonl)
        index_path = d / "sessions-index.json"
        if index_path.exists():
            sessions.extend(_parse_sessions_index(index_path, from_dt, to_dt))

    # Sort by start time
    sessions.sort(key=lambda s: s["started_at"])
    return sessions


# ── Claude API ──────────────────────────────────────────────────────────────────

def build_post_prompt(sessions: list[dict], persona: str, past_posts: list[str]) -> str:
    """Build a prompt that asks ONLY for post drafts (no summary/digest)."""
    lines = []
    for i, s in enumerate(sessions, 1):
        date_str = s["started_at"].strftime("%a %b %d, %H:%M")
        lines.append(f"\n--- Session {i}: {s['project']} | {date_str} | {s['duration_min']} min ---")
        for msg in s["sampled_messages"]:
            short = msg[:300] + "…" if len(msg) > 300 else msg
            lines.append(f"  > {short}")

    sessions_text = "\n".join(lines)
    date_range = f"{sessions[0]['started_at'].strftime('%b %d')} – {sessions[-1]['started_at'].strftime('%b %d, %Y')}"

    persona_section = f"""PERSONA (voice, rules, and sample posts — match this style closely):
{persona}""" if persona else "Write posts in first person, casual tone."

    past_section = ""
    if past_posts:
        past_section = "\n\nPUBLISHED POSTS (these are real posts the author wrote and published — "
        past_section += "match this style and tone closely, they are the best reference for the author's voice. "
        past_section += "Also avoid repeating the same topics or phrasing):\n"
        for i, pp in enumerate(past_posts, 1):
            past_section += f"\n--- Published post {i} ---\n{pp}\n"

    return f"""You are a social media ghostwriter.
Read these Claude Code sessions and generate post drafts.

{persona_section}
{past_section}
DATE RANGE: {date_range}
TOTAL SESSIONS: {len(sessions)}

SESSION LOG (user messages sampled from each session):
{sessions_text}

---

Generate posts as a valid JSON array with this structure:

[
  {{
    "type": "<post-type>",
    "draft": "post text here, ready to copy, authentic voice, max 500 chars",
    "source": "which session or topic this comes from"
  }}
]

Available post types (choose 4-6 that fit what actually happened):
- "build-update" — what was shipped or worked on (30-35% of posts, weekly+)
- "lesson" — specific insight or decision learned (25-30%, weekly)
- "behind-the-scenes" — process, struggles, personal context (20-25%, weekly)
- "engagement" — question or ask to the audience (15-20%, weekly)
- "milestone" — concrete numbers, launches, celebrations (rare, 1-3x/month)
- "weekly-recap" — casual week wrap-up (1x/week)

Pick types based on what the sessions contain. Don't force a type if the sessions don't support it.
Always include a "weekly-recap". Prefer variety over repetition.
Write posts in first person, casual, no cringe startup-speak.
Return ONLY the JSON array, no markdown fences, no preamble.
"""


def generate_posts(sessions: list[dict], model: str, persona: str, past_posts: list[str]) -> list[dict]:
    """Call Claude API to generate post drafts. Returns a list of post dicts."""
    client = anthropic.Anthropic()
    prompt = build_post_prompt(sessions, persona, past_posts)

    print(f"  Calling Claude API ({model})…")
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        print(f"\n{BOLD}[error]{RESET} API call failed: {e}")
        sys.exit(1)

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"\n{BOLD}[error]{RESET} Failed to parse API response as JSON.")
        print(f"Raw response:\n{raw[:500]}")
        sys.exit(1)


# ── Output ──────────────────────────────────────────────────────────────────────

POST_TYPES = {
    "build-update": {
        "label": "Build update",
        "color": GREEN,
        "freq":  "30-35% of posts · weekly+",
        "desc":  "What you shipped or are working on. Demos, screenshots, progress.",
    },
    "lesson": {
        "label": "Lesson",
        "color": AMBER,
        "freq":  "25-30% of posts · weekly",
        "desc":  "Specific insight or decision. Not generic advice.",
    },
    "behind-the-scenes": {
        "label": "Behind the scenes",
        "color": PURPLE,
        "freq":  "20-25% of posts · weekly",
        "desc":  "Process, struggles, personal context. The human side.",
    },
    "engagement": {
        "label": "Engagement",
        "color": TEAL,
        "freq":  "15-20% of posts · weekly",
        "desc":  "Questions, polls, asking for input. Community building.",
    },
    "milestone": {
        "label": "Milestone",
        "color": GREEN,
        "freq":  "rare · 1-3x/month",
        "desc":  "Concrete numbers, launches, celebrations. High impact.",
    },
    "weekly-recap": {
        "label": "Weekly recap",
        "color": TEAL,
        "freq":  "1x/week",
        "desc":  "Casual wrap-up of the week's work.",
    },
    "win": {  # legacy compat
        "label": "Win",
        "color": GREEN,
        "freq":  "30-35% of posts",
        "desc":  "Shipped something.",
    },
}

def print_overview(sessions: list[dict]):
    """Print a locally-computed overview of sessions (no API call needed)."""
    first = sessions[0]["started_at"]
    last = sessions[-1]["started_at"]
    date_range = f"{first.strftime('%b %d')} – {last.strftime('%b %d, %Y')}"

    print()
    print(f"{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}  Claude Code Overview  ·  {date_range}{RESET}")
    print(f"{BOLD}{'─' * 60}{RESET}")
    print()

    print(f"  {BOLD}Sessions:{RESET} {len(sessions)}")
    print()

    # Projects breakdown
    projects: dict[str, int] = defaultdict(int)
    for s in sessions:
        projects[s["project"]] += 1
    print(f"  {BOLD}Projects:{RESET}")
    for name, count in sorted(projects.items(), key=lambda x: -x[1]):
        print(f"    {TEAL}·{RESET} {name}  {DIM}({count} sessions){RESET}")
    print()

    # Activity timeline
    print(f"  {BOLD}Activity:{RESET}")
    by_day: dict[datetime, int] = defaultdict(int)
    for sess in sessions:
        day = sess["started_at"].replace(hour=0, minute=0, second=0, microsecond=0)
        by_day[day] += 1
    max_count = max(by_day.values(), default=1)
    for day, count in sorted(by_day.items()):
        label = day.strftime("%a %b %d")
        bar = "█" * count + "░" * (max_count - count)
        print(f"    {DIM}{label}{RESET}  {TEAL}{bar}{RESET}  {count}")
    print()


def print_posts(posts: list[dict]):
    for i, post in enumerate(posts, 1):
        ptype = post.get("type", "")
        info = POST_TYPES.get(ptype, {})
        color = info.get("color", RESET)
        label = info.get("label", ptype)
        freq = info.get("freq", "")
        source = post.get("source", "")
        draft = post.get("draft", "")

        print(f"  {color}{BOLD}[{i}. {label}]{RESET}  {DIM}{source}{RESET}")
        if freq:
            print(f"  {DIM}recommended: {freq}{RESET}")
        print()
        # Word-wrap the draft at 70 chars
        words = draft.split()
        line = "    "
        for word in words:
            if len(line) + len(word) + 1 > 74:
                print(line)
                line = "    " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(line)
        print()
        print(f"  {DIM}{'─' * 56}{RESET}")
        print()


def refine_posts(posts: list[dict], model: str, persona: str) -> list[dict]:
    """Interactive loop: let the user give feedback and regenerate posts."""
    client = anthropic.Anthropic()
    conversation = [
        {"role": "assistant", "content": json.dumps(posts, indent=2)},
    ]

    persona_hint = f"\n\nPERSONA:\n{persona}" if persona else ""

    while True:
        print(f"  {DIM}Give feedback to refine, or press Enter to accept:{RESET}")
        try:
            feedback = input(f"  {TEAL}>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not feedback:
            break

        conversation.append({"role": "user", "content": feedback})

        print(f"\n  Refining ({model})…\n")
        try:
            response = client.messages.create(
                model=model,
                max_tokens=2000,
                system=f"""You are refining social media post drafts.
{persona_hint}

You were given a set of posts (as JSON) and the user is giving feedback.
Apply their feedback and return the updated posts array as valid JSON.
Keep the same structure: each post has "type", "draft", "source".
Return ONLY the JSON array, no markdown fences, no preamble.""",
                messages=conversation,
            )
        except anthropic.APIError as e:
            print(f"\n{BOLD}[error]{RESET} API call failed: {e}")
            continue

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            posts = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  {BOLD}[error]{RESET} Couldn't parse response. Try again.\n")
            conversation.pop()  # remove failed feedback so conversation stays clean
            continue

        conversation.append({"role": "assistant", "content": raw})

        print_posts(posts)

    return posts


def save_posts(posts: list[dict], date_str: str, project: str | None = None):
    """Let user pick which posts to save as individual files."""
    print(f"\n  {BOLD}Save posts{RESET}")
    print(f"  {DIM}Enter post numbers to save (e.g. 1 3 5), 'all', or Enter to skip:{RESET}")
    try:
        choice = input(f"  {TEAL}>{RESET} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not choice:
        print(f"  {DIM}No posts saved.{RESET}")
        return

    if choice.lower() == "all":
        indices = list(range(len(posts)))
    else:
        try:
            indices = [int(x) - 1 for x in choice.split()]
            indices = [i for i in indices if 0 <= i < len(posts)]
        except ValueError:
            print(f"  {AMBER}Couldn't parse selection. No posts saved.{RESET}")
            return

    if not indices:
        print(f"  {DIM}No valid posts selected.{RESET}")
        return

    # Build output dir: posts/ or posts/<project>/
    out_dir = POSTS_DIR / project if project else POSTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for idx in indices:
        post = posts[idx]
        ptype = post.get("type", "post")
        draft = post.get("draft", "")
        source = post.get("source", "")
        info = POST_TYPES.get(ptype, {})
        label = info.get("label", ptype)

        # Filename: 2026-04-12-build-update.md
        slug = ptype.replace(" ", "-").lower()
        filename = f"{date_str}-{slug}.md"

        # Avoid overwriting — append a number if needed
        path = out_dir / filename
        counter = 2
        while path.exists():
            path = out_dir / f"{date_str}-{slug}-{counter}.md"
            counter += 1

        content = f"# {label}\n\n{draft}\n\n---\n*{source}*\n"
        path.write_text(content, encoding="utf-8")
        saved.append(path)

    for p in saved:
        print(f"  {GREEN}Saved:{RESET} {p}")

    print(f"\n  {DIM}Edit these files before publishing.{RESET}")


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a social media digest from your Claude Code sessions."
    )
    parser.add_argument("--days", type=int, default=None, help="Number of past days to include (default: 7, or all when --project)")
    parser.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Anthropic model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--project", nargs="?", const="__pick__", help="Filter by project (shows picker if no name given)")
    parser.add_argument("--dry-run", action="store_true", help="List sessions found, skip API call")
    parser.add_argument("--no-refine", action="store_true", help="Skip the interactive refinement loop")
    parser.add_argument("--setup", action="store_true", help="Run persona setup (create/overwrite persona.md)")
    args = parser.parse_args()

    if args.setup:
        setup_persona()
        return

    # Load persona — prompt setup on first run
    persona = load_persona()
    if not persona:
        print(f"  {AMBER}No persona.md found.{RESET} Let's set one up.\n")
        setup_persona()
        persona = load_persona()

    now = datetime.now(tz=timezone.utc)
    explicit_date_range = args.from_date or args.to_date or args.days is not None

    # Project filter — scan all known projects before applying date range
    selected_project = None
    project_folders: list[Path] | None = None
    if args.project:
        # Discover projects with last-activity dates (from mtime, fast)
        # Also track which folders map to each project name for pre-filtering
        project_info: dict[str, datetime] = {}
        project_folders_map: dict[str, list[Path]] = defaultdict(list)
        if CLAUDE_PROJECTS_DIR.exists():
            for d in CLAUDE_PROJECTS_DIR.iterdir():
                if not d.is_dir():
                    continue
                jsonl_files = list(d.glob("*.jsonl"))
                index_file = d / "sessions-index.json"
                if not jsonl_files and not index_file.exists():
                    continue
                name = _project_name_from_folder(d.name)
                # Get latest mtime from jsonl files or index file
                mtimes = [
                    datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                    for f in jsonl_files
                ]
                if index_file.exists():
                    mtimes.append(datetime.fromtimestamp(index_file.stat().st_mtime, tz=timezone.utc))
                latest = max(mtimes)
                project_folders_map[name].append(d)
                if name not in project_info or latest > project_info[name]:
                    project_info[name] = latest

        projects = sorted(project_info.keys())

        if args.project == "__pick__":
            print(f"\n{BOLD}cc-ghost{RESET}  all projects\n")
            for i, p in enumerate(projects, 1):
                last = project_info[p]
                age = (now - last).days
                if age == 0:
                    age_str = "today"
                elif age == 1:
                    age_str = "yesterday"
                else:
                    age_str = f"{age}d ago"
                print(f"    {TEAL}{i}.{RESET} {p}  {DIM}({age_str}){RESET}")
            print(f"\n  {DIM}Enter number or name:{RESET}")
            try:
                pick = input(f"  {TEAL}>{RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if pick:
                try:
                    idx = int(pick) - 1
                    if 0 <= idx < len(projects):
                        selected_project = projects[idx]
                except ValueError:
                    matches = [p for p in projects if pick.lower() in p.lower()]
                    if matches:
                        selected_project = matches[0]
                if not selected_project:
                    print(f"  {AMBER}No matching project found.{RESET}")
                    return
            else:
                return
        else:
            matches = [p for p in projects if args.project.lower() in p.lower()]
            if matches:
                selected_project = matches[0]
            else:
                print(f"  {AMBER}No project matching '{args.project}' found.{RESET}")
                return

        project_folders = project_folders_map.get(selected_project)

    # Date range — when --project is used without explicit dates, load all sessions
    used_last_run = False
    if args.from_date:
        from_dt = datetime.fromisoformat(args.from_date).replace(tzinfo=timezone.utc)
    elif args.days is not None:
        from_dt = now - timedelta(days=args.days)
    elif selected_project and not explicit_date_range:
        from_dt = datetime.min.replace(tzinfo=timezone.utc)
    else:
        last_run = load_last_run()
        if last_run is not None:
            from_dt = last_run
            used_last_run = True
        else:
            from_dt = now - timedelta(days=7)
            used_last_run = False

    if args.to_date:
        to_dt = datetime.fromisoformat(args.to_date).replace(hour=23, minute=59, tzinfo=timezone.utc)
    else:
        to_dt = now

    print(f"\n{BOLD}cc-ghost{RESET}  scanning {CLAUDE_PROJECTS_DIR}")
    if selected_project:
        print(f"  {BOLD}Project:{RESET} {selected_project}")
    if from_dt.year > 1:
        since = " (since last run)" if used_last_run else ""
        print(f"  Range: {from_dt.strftime('%Y-%m-%d %H:%M')}{since} → {to_dt.strftime('%Y-%m-%d %H:%M')}")
    print()

    sessions = load_sessions(from_dt, to_dt, project_folders=project_folders)

    if selected_project:
        sessions = [s for s in sessions if s["project"] == selected_project]

    if not sessions:
        msg = f"No sessions found for '{selected_project}'" if selected_project else "No sessions found"
        print(f"{msg}.")
        if not selected_project:
            print(f"Tip: check that {CLAUDE_PROJECTS_DIR} contains .jsonl files.")
        return

    # Local overview — always shown, even on dry-run
    print_overview(sessions)

    if args.dry_run:
        print("[dry-run] Skipping API call.")
        return

    # Load past posts for context
    past_posts = load_past_posts()
    if past_posts:
        print(f"  {DIM}Loaded {len(past_posts)} published post(s) as style reference.{RESET}")

    print()
    posts = generate_posts(sessions, model=args.model, persona=persona, past_posts=past_posts)
    save_last_run(now)

    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}  Suggested posts{RESET}")
    print(f"{BOLD}{'─' * 60}{RESET}\n")

    print_posts(posts)

    # Interactive refinement
    if not args.no_refine:
        posts = refine_posts(posts, model=args.model, persona=persona)

    # Save individual posts
    save_posts(posts, now.strftime("%Y-%m-%d"), project=selected_project)


if __name__ == "__main__":
    main()