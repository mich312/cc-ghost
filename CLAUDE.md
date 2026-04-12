# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

cc-ghost is a single-file Python CLI that reads Claude Code session logs (`~/.claude/projects/**/*.jsonl`), generates social media post drafts in the user's voice, and lets them refine interactively. Published posts feed back as style examples so the voice improves over time.

## Running

Dependencies are declared inline via PEP 723 — `uv` handles everything.

```bash
uv run cc-ghost.py                    # last 7 days, all projects
uv run cc-ghost.py --project          # pick a project (all sessions)
uv run cc-ghost.py --project Mountain # filter by name substring
uv run cc-ghost.py --days 14          # last 14 days
uv run cc-ghost.py --dry-run          # list sessions, skip API call
uv run cc-ghost.py --setup            # create/overwrite persona.md
uv run cc-ghost.py --model claude-sonnet-4-5  # override model
uv run cc-ghost.py --no-refine        # skip interactive refinement
```

Configuration via `.env` or environment variables:
- `ANTHROPIC_API_KEY` — required
- `CC_GHOST_MODEL` — optional, defaults to `claude-haiku-4-5-20251001`

## Architecture

Everything lives in `cc-ghost.py`:

1. **Persona** (`load_persona`, `setup_persona`) — Reads `persona.md` (voice, rules, sample posts). Interactive setup on first run or via `--setup`.
2. **Past Posts** (`load_past_posts`) — Loads up to 10 recent published posts from `posts/` as style examples. These take priority over persona samples.
3. **JSONL Parsing** (`_project_name_from_folder`, `parse_session`, `load_sessions`) — Reads session files, extracts user messages, derives project names from cwd (with folder-name fallback). `load_sessions` accepts optional `project_folders` to pre-filter instead of scanning everything.
4. **Overview** (`print_overview`) — Locally-computed terminal display: date range, session count, projects breakdown, activity chart. No API call needed.
5. **Claude API** (`build_post_prompt`, `generate_posts`) — Builds a focused prompt for post generation only (no summary/highlights). Returns a JSON array of post dicts.
6. **Output** (`print_posts`) — Terminal output with ANSI colors. Post types are dynamic (chosen by the model based on session content).
7. **Refinement** (`refine_posts`) — Multi-turn conversation loop for adjusting posts.
8. **Saving** (`save_posts`) — User picks which posts to save as individual files in `posts/` or `posts/<project>/`.
9. **CLI** (`main`) — argparse entry point. `--project` shows a picker with folder pre-filtering; `--dry-run` shows the local overview without an API call.

## Key Files

- `cc-ghost.py` — the tool (single file, self-contained deps via PEP 723)
- `persona.md` — user's voice/rules/samples (created via `--setup`, gitignored)
- `persona.example.md` — template for new users
- `posts/` — saved posts organized by project, also used as style examples for future runs

## Key Details

- Only user messages are extracted from sessions (not assistant responses).
- Messages are sampled (max 12 per session) to keep token usage low.
- `--project` without a date range loads all sessions for that project.
- Post types (build-update, lesson, behind-the-scenes, engagement, milestone, weekly-recap) are chosen dynamically based on session content.
- Model defaults to Haiku (cheap/fast).
