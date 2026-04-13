# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

cc-ghost is a single-file Python CLI that reads Claude Code session logs (`~/.claude/projects/**/*.jsonl`), generates social media post drafts in the user's voice, and lets them refine interactively. Published posts feed back as style examples so the voice improves over time.

## Running

Installable as a CLI tool via `uv tool install` or runnable directly via `uv run cc-ghost.py`.

```bash
cc-ghost                              # since last run (or last 7 days)
cc-ghost --project                    # pick a project (all sessions)
cc-ghost --project Mountain           # filter by name substring
cc-ghost --days 14                    # last 14 days
cc-ghost --platform twitter           # optimize for Twitter (280 chars)
cc-ghost --dry-run                    # list sessions, skip API call
cc-ghost --setup                      # configure API key and persona
cc-ghost --model claude-sonnet-4-5    # override model
cc-ghost --no-refine                  # skip interactive refinement
```

Configuration lives in `~/.config/cc-ghost/` (XDG-compliant):
- `config.env` — API key and model override (created by `--setup`, chmod 600)
- `persona.md` — user's voice/rules/samples
- `posts/` — saved posts, used as style examples
- `.last_run` — timestamp for incremental scanning

Environment variables: `ANTHROPIC_API_KEY` (required), `CC_GHOST_MODEL` (optional, defaults to `claude-haiku-4-5-20251001`).

## Architecture

Core logic lives in `cc_ghost.py`, with `cc-ghost.py` as a thin `uv run` wrapper.

1. **Setup** (`setup_api_key`, `setup_persona`, `load_persona`) — API key setup writes to `~/.config/cc-ghost/config.env`. Persona setup creates `persona.md`. Both run interactively on first use or via `--setup`.
2. **Past Posts** (`load_past_posts`) — Loads up to 10 recent published posts from `posts/` as style examples.
3. **Session Parsing** (`parse_session`, `_parse_sessions_index`, `load_sessions`) — Three data sources: top-level `.jsonl` files, `sessions-index.json` metadata, and `session-memory/summary.md` structured summaries. Sessions deduplicated by UUID.
4. **Git Integration** (`load_git_logs`) — Runs `git log` in each project directory for recent commits.
5. **Overview** (`print_overview`) — Local terminal display: projects, session counts, activity chart. No API call.
6. **Claude API** (`build_post_prompt`, `generate_posts`) — Focused prompt with sessions, git logs, effort metrics, persona, and past posts. Platform-aware char limits via `--platform`.
7. **Output** (`print_posts`) — Terminal output with ANSI colors. Post types chosen dynamically.
8. **Refinement** (`refine_posts`) — Multi-turn conversation loop.
9. **Saving** (`save_posts`) — Individual files in `posts/` or `posts/<project>/`.
10. **CLI** (`main`) — argparse entry point with `.last_run` tracking for incremental scans.

## Key Files

- `cc_ghost.py` — the tool (single file, all logic)
- `cc-ghost.py` — thin wrapper for `uv run` compatibility
- `pyproject.toml` — package config for `uv tool install` / `pipx install`
- `persona.example.md` — template for new users

## Key Details

- Three session data sources: JSONL files, sessions-index.json, session-memory/summary.md.
- Messages are sampled (max 12 per session) to keep token usage low.
- `--project` without a date range loads all sessions for that project; pre-filters by folder.
- Git commit history is loaded from project directories when available.
- Post types (build-update, lesson, behind-the-scenes, engagement, milestone, weekly-recap) are chosen dynamically.
- `--platform` adjusts char limits and tone (twitter=280, bluesky=300, mastodon/threads=500, linkedin=3000).
- Model defaults to Haiku (cheap/fast).
