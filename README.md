<p align="center">
  <img src="cc-ghost.png" alt="cc-ghost logo" width="200">
</p>

# cc-ghost

A ghostwriter for your [Claude Code](https://claude.ai/code) sessions. Reads your local session logs, analyzes what you built, and drafts social media posts in your voice — then lets you refine them interactively.

Your published posts feed back as style examples, so the ghostwriter learns your voice over time.

## Install

Install as a CLI tool (requires [uv](https://docs.astral.sh/uv/)):

```bash
uv tool install git+https://github.com/mich312/cc-ghost
```

Or with pip/pipx:

```bash
pipx install git+https://github.com/mich312/cc-ghost
```

On first run, cc-ghost will prompt you for your [Anthropic API key](https://console.anthropic.com/) and walk you through creating a persona. You can also run `cc-ghost --setup` at any time to reconfigure.

Alternatively, run directly without installing:

```bash
git clone https://github.com/mich312/cc-ghost.git
cd cc-ghost
uv run cc-ghost.py
```

## Usage

```bash
cc-ghost                                    # since last run (or last 7 days)
cc-ghost --days 14                          # last 14 days
cc-ghost --project                          # pick a project (loads all sessions)
cc-ghost --project MyApp                    # filter by name
cc-ghost --platform twitter                 # optimize for Twitter (280 chars)
cc-ghost --platform blog                    # write a long-form devlog post
cc-ghost --dry-run                          # preview sessions, no API call
cc-ghost --setup                            # configure API key and persona
cc-ghost --model claude-sonnet-4-5          # override model
cc-ghost --no-refine                        # skip interactive refinement
```

### Project picker

`--project` without a value shows an arrow-key picker with last-activity dates:

```
? Pick a project: (Use arrow keys)
 ❯ MyApp           (today)
   SideProject     (23d ago)
   OldThing        (81d ago)
   WeekendHack     (yesterday)
```

When picking a project without `--days` or `--from`, all sessions for that project are loaded regardless of date.

### Platform targeting

If `--platform` is omitted, cc-ghost asks where you want to post:

```
? Where do you want to post? (Use arrow keys)
 ❯ Twitter  (280 chars, punchy)
   Bluesky  (300 chars, casual)
   Mastodon (500 chars, technical)
   Threads  (500 chars, brief)
   LinkedIn (3000 chars, professional)
   Blog post (long-form devlog)
```

| Platform | Char limit | Tone |
|---|---|---|
| `twitter` | 280 | Punchy, concise, no fluff |
| `bluesky` | 300 | Conversational, slightly nerdy |
| `mastodon` | 500 | Casual, technical depth welcome |
| `threads` | 500 | Brief, conversation-starting |
| `linkedin` | 3000 | Professional but authentic |
| `blog` | — | Long-form devlog with markdown headings |

### Blog post flow

Blog generation has two extra steps before drafting:

1. **Project checkbox** — pick which projects' sessions to include (skipped if `--project` was used)
2. **Angle picker** — the AI suggests 4-5 possible angles ranging from broad (weekly recap) to narrow (deep-dive on one feature). Pick one, write your own, or skip for an unfocused post.

The result is a single markdown file you can edit and publish.

### Refinement loop

After generating posts, choose what to do next:

```
? What next? (Use arrow keys)
 ❯ Accept and continue
   Refine all with AI feedback
   Edit 1. Build update — Shipped the new share card pipeline today…
   Edit 2. Lesson — Realized I was over-engineering the caching layer…
   Edit 3. Engagement — How do you handle migrations that touch…
```

- **Accept** — keep the posts as-is and move to saving.
- **Refine** — type natural-language feedback ("make the recap shorter"), AI rewrites all posts.
- **Edit a specific post** — opens the draft in an inline editor (Meta+Enter to submit).

For blog posts, "Edit directly" opens the full markdown in the editor.

### Saving posts

After refinement, pick which posts to save with a checkbox:

```
? Save which posts? (use arrow keys, space to toggle, enter to confirm)
 ❯ ◉ 1. Build update — Shipped the new share card pipeline today…
   ◯ 2. Lesson — Realized I was over-engineering the caching layer…
   ◉ 3. Engagement — How do you handle migrations that touch…
   ◉ 4. Weekly recap — A quiet week, but a productive one…
```

Posts are saved as individual markdown files in `~/.config/cc-ghost/posts/`. Edit them before publishing.

## How it works

1. Loads your **persona** (voice, rules, sample posts) from `persona.md`
2. Loads **published posts** from `posts/` as style examples — the ghostwriter matches your real voice, not just the persona description
3. Scans `~/.claude/projects/` for session logs, session indexes, and session memory summaries
4. Shows a **local overview** — projects, session counts, activity chart (no API call)
5. Asks **where you want to post** (or uses `--platform`)
6. Loads **git commit history** from each project for technical specifics
7. Sends everything to the Claude API with **effort metrics** (session count, duration, messages per project)
8. **Refine** interactively (edit individual posts or rewrite all with feedback), then **save** the ones you want

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

For social platforms, posts are chosen dynamically based on what your sessions actually contain (blog mode generates a single long-form post instead):

| Type | Recommended frequency |
|---|---|
| **Build update** | 30-35% of posts, weekly+ |
| **Lesson** | 25-30%, weekly |
| **Behind the scenes** | 20-25%, weekly |
| **Engagement** | 15-20%, weekly |
| **Milestone** | rare, 1-3x/month |
| **Weekly recap** | 1x/week |

## Configuration

All config lives in `~/.config/cc-ghost/` (or `$XDG_CONFIG_HOME/cc-ghost/`):

| File | Purpose |
|---|---|
| `config.env` | API key and model override (created by `--setup`) |
| `persona.md` | Your voice, rules, and sample posts |
| `posts/` | Saved posts, organized by project |
| `.last_run` | Timestamp of last generation |

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Your Anthropic API key |
| `CC_GHOST_MODEL` | No | `claude-sonnet-4-5` | Model to use |

The `--model` flag overrides `CC_GHOST_MODEL`. Variables can be set in `~/.config/cc-ghost/config.env`, a `.env` file in the current directory, or your shell environment.

## License

[MIT](LICENSE)
