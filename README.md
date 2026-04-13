<p align="center">
  <img src="cc-ghost.png" alt="cc-ghost logo" width="200">
</p>

# cc-ghost

A ghostwriter for your [Claude Code](https://claude.ai/code) sessions. Reads your local session logs, analyzes what you built, and drafts social media posts in your voice — then lets you refine them interactively.

Your published posts feed back as style examples, so the ghostwriter learns your voice over time.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

```bash
git clone https://github.com/mich312/cc-ghost.git
cd cc-ghost
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

On first run, cc-ghost walks you through creating a `persona.md` — your voice, rules, and sample posts that teach the ghostwriter how to write like you. You can also copy the example and edit directly:

```bash
cp persona.example.md persona.md
```

## Usage

```bash
uv run cc-ghost.py                          # since last run (or last 7 days)
uv run cc-ghost.py --days 14                # last 14 days
uv run cc-ghost.py --project                # pick a project (loads all sessions)
uv run cc-ghost.py --project Mountain       # filter by name
uv run cc-ghost.py --platform twitter       # optimize for Twitter (280 chars)
uv run cc-ghost.py --dry-run                # preview sessions, no API call
uv run cc-ghost.py --setup                  # create/redo persona
uv run cc-ghost.py --model claude-sonnet-4-5  # override model
uv run cc-ghost.py --no-refine              # skip interactive refinement
```

### Project picker

`--project` without a value shows all your projects with last-activity dates:

```
cc-ghost  all projects

    1. Customer-Support-Agent  (today)
    2. DiskBuddy  (23d ago)
    3. Film-Tracker  (81d ago)
    4. Mountain-Passes  (yesterday)

  Enter number or name:
  >
```

When picking a project without `--days` or `--from`, all sessions for that project are loaded regardless of date.

### Platform targeting

Use `--platform` to tailor posts for a specific platform:

| Platform | Char limit | Tone |
|---|---|---|
| `twitter` | 280 | Punchy, concise, no fluff |
| `bluesky` | 300 | Conversational, slightly nerdy |
| `mastodon` | 500 | Casual, technical depth welcome |
| `threads` | 500 | Brief, conversation-starting |
| `linkedin` | 3000 | Professional but authentic |

Without `--platform`, posts default to 500 characters with no platform-specific tone.

### Refinement loop

After generating posts, you can give feedback to adjust them:

```
  Give feedback to refine, or press Enter to accept:
  > make the recap shorter
  > add something about the MapKit workaround
  > drop post 3
  >
```

### Saving posts

After refinement, choose which posts to save:

```
  Save posts
  Enter post numbers to save (e.g. 1 3 5), 'all', or Enter to skip:
  > 1 4
  Saved: posts/Mountain-Passes/2026-04-12-build-update.md
  Saved: posts/Mountain-Passes/2026-04-12-weekly-recap.md
```

Posts are saved as individual markdown files in `posts/` (or `posts/<project>/` when using `--project`). Edit them before publishing.

## How it works

1. Loads your **persona** (voice, rules, sample posts) from `persona.md`
2. Loads **published posts** from `posts/` as style examples — the ghostwriter matches your real voice, not just the persona description
3. Scans `~/.claude/projects/` for session logs, session indexes, and session memory summaries
4. Shows a **local overview** — projects, session counts, activity chart (no API call)
5. Loads **git commit history** from each project for technical specifics
6. Sends everything to the Claude API with **effort metrics** (session count, duration, messages per project)
7. **Refine** interactively, then **save** the ones you want

### Smart date ranges

On the first run, cc-ghost scans the last 7 days. After that, it remembers when you last generated posts and only scans new sessions. Use `--days` or `--from`/`--to` to override.

### Voice learning

Every post you save and manually edit becomes a style example for future runs. Over time, the `persona.md` samples matter less and your actual published posts take over. The feedback loop:

```
generate → refine → save → edit → publish
                              ↓
                    future runs match your real voice
```

### Session data sources

cc-ghost reads from multiple sources to maximize coverage:

- **JSONL session files** — full conversation transcripts (older Claude Code format)
- **sessions-index.json** — session metadata with first prompt and summary (newer format)
- **session-memory/summary.md** — rich structured summaries with features completed, files modified, and errors fixed
- **Git history** — recent commits from each project directory

Sessions are deduplicated by UUID and the richest available data source is preferred.

## Post types

Posts are chosen dynamically based on what your sessions actually contain:

| Type | Recommended frequency |
|---|---|
| **Build update** | 30-35% of posts, weekly+ |
| **Lesson** | 25-30%, weekly |
| **Behind the scenes** | 20-25%, weekly |
| **Engagement** | 15-20%, weekly |
| **Milestone** | rare, 1-3x/month |
| **Weekly recap** | 1x/week |

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Your Anthropic API key |
| `CC_GHOST_MODEL` | No | `claude-haiku-4-5-20251001` | Model to use |

The `--model` flag overrides `CC_GHOST_MODEL`. Set variables in `.env` or your shell.

## License

[MIT](LICENSE)
