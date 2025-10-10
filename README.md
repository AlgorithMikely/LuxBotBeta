# Discord Music Review Bot

A comprehensive Discord bot with TikTok Live integration for managing music submissions, queue prioritization, and viewer engagement tracking.

## Features

- **9-Tier Priority Queue System**: 25+ Skip, 20 Skip, 15 Skip, 10 Skip, 5 Skip, Free, Pending Skips, Songs Played, Removed
- **TikTok Live Integration**: Real-time event tracking for gifts, joins, likes, comments, shares, follows
- **Luxury Coins Economy**: Earn coins via watch time (1 coin/30min) and gifts (2 coins/100 gifted coins)
- **Hybrid Submission System**: Slash commands, file uploads, and passive link detection
- **Persistent Auto-Updating Embeds**: Live queue, reviewer queue, and pending skips with 10-second refresh
- **Points & Engagement Tracking**: Automatic score calculation for Free queue ordering
- **Admin Tools**: Force link/unlink TikTok handles, metrics reporting, channel configuration

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL database
- Discord Bot Token

### Installation

1. Clone the repository and install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure environment variables:

```bash
cp .env.example .env
```

Edit `.env` and add your Discord bot token:

```
DISCORD_BOT_TOKEN=your_bot_token_here
DATABASE_URL=postgresql://user:password@localhost:5432/music_bot
ALLOW_ANY_HANDLE_LINKING=false
```

3. Run the bot:

```bash
python main.py
```

## Database

The bot automatically creates all required tables and indexes on first run:

- `live_sessions` - TikTok live stream sessions
- `tiktok_accounts` - TikTok user handles and points
- `tiktok_interactions` - Event tracking (gifts, joins, likes, etc.)
- `viewer_count_snapshots` - Viewer count tracking
- `submissions` - Music submissions
- `user_points` - Discord user engagement points
- `bot_config` - Bot configuration
- `persistent_embeds` - Auto-updating embed tracking
- `queue_config` - Queue channel configuration
- `luxury_coins` - Luxury Coins economy
- `tiktok_watch_time` - Watch time tracking for coin rewards

## Commands

### User Commands

- `/submit` - Submit a music link (YouTube, Spotify, SoundCloud, Deezer, Ditto)
- `/submitfile` - Submit a music file (mp3, m4a, wav, flac - max 25MB)
- `/queue [page]` - View the current queue
- `/link-tiktok <handle>` - Link your TikTok handle
- `/unlink-tiktok <handle>` - Unlink a TikTok handle
- `/my-links` - View your linked TikTok handles
- `/coins` - Check your Luxury Coins balance
- `/buy-skip` - Spend 1000 Luxury Coins to move submission to 10 Skip tier
- `/leaderboard-coins` - View Luxury Coins leaderboard

### Admin Commands

- `/next` - Play the next song in queue (resets points for Free tier)
- `/remove-submission <id>` - Remove a submission from queue
- `/set-submission-channel <#channel>` - Configure submissions-only channel
- `/setup-live-queue <#channel>` - Setup live queue embed
- `/setup-reviewer-channel <#channel>` - Setup reviewer embeds with approve/remove buttons
- `/set-metrics-channel <#channel>` - Set metrics reporting channel
- `/post-live-metrics` - Post metrics for last live session
- `/admin-link <@user> <handle>` - Force link TikTok handle to user
- `/admin-unlink <@user> <handle>` - Force unlink TikTok handle
- `/admin-give-coins <@user> <amount>` - Give Luxury Coins to user

### TikTok Commands

- `/tiktok-connect <username> [persistent=true]` - Connect to TikTok live stream
- `/tiktok-status` - Check connection status
- `/tiktok-disconnect` - Disconnect from live stream

## Queue Priority System

1. **25+ Skip** (≥6000 coins) - Highest priority, FIFO
2. **20 Skip** (5000-5999 coins)
3. **15 Skip** (4000-4999 coins)
4. **10 Skip** (2000-3999 coins)
5. **5 Skip** (1000-1999 coins)
6. **Free** - Sorted by engagement points (DESC), then submission time (ASC)
7. **Pending Skips** - Admin review required
8. **Songs Played** - Archive
9. **Removed** - Deleted by admin

## Submissions

### Channel Enforcement

- Configure submissions channel with `/set-submission-channel`
- Passive submissions (links/files) only accepted in configured channel
- Submissions in other channels are deleted with error message

### Supported Platforms

- YouTube
- Spotify
- SoundCloud
- Deezer
- Ditto

### Rejected Platforms

- Apple Music
- iTunes

### File Uploads

- Supported formats: mp3, m4a, wav, flac
- Maximum size: 25MB
- Auto-uploaded to Discord CDN

## TikTok Integration

### Event Tracking

All TikTok Live events are tracked:
- JoinEvent
- LikeEvent
- CommentEvent
- ShareEvent
- FollowEvent
- SubscribeEvent
- GiftEvent (with streak detection)
- RoomUserSeqEvent
- ViewerCountUpdateEvent
- ConnectEvent
- DisconnectEvent
- LiveEndEvent

### Gift Processing

Points calculation:
- If diamond_count < 1000: `points = diamond_count * 2`
- Else: `points = diamond_count`

Skip tier determination:
- ≥6000 coins → 25+ Skip
- ≥5000 coins → 20 Skip
- ≥4000 coins → 15 Skip
- ≥2000 coins → 10 Skip
- ≥1000 coins → 5 Skip

## Luxury Coins Economy

### Earning Coins

- **Watch Time**: 1 coin per 30 minutes watched (requires linked TikTok handle)
- **Gifts**: 2 coins per 100 gifted coins

### Spending Coins

- **Buy Skip**: 1000 coins moves submission from Free/Pending Skips/5 Skip to 10 Skip tier

## Persistent Embeds

### Auto-Refresh System

- Updates every 10 seconds
- 1-second delay between embed updates to avoid rate limits
- Content-hash optimization skips unchanged content
- Self-healing: recreates deleted messages

### Embed Types

1. **Live Queue** - Public view with pagination and emoji indicators
2. **Reviewer Main Queue** - Admin view with approve/remove buttons
3. **Reviewer Pending Skips** - Awaiting admin approval

## Points & Engagement

### Point Sources

- Discord user points (`user_points` table)
- TikTok handle points (`tiktok_accounts` table)
- Points sync to linked Discord users

### Lifecycle

1. TikTok event awards points to handle
2. If linked to Discord user, points added to `user_points`
3. `sync_submission_scores()` runs every 30 seconds
4. Updates `submissions.total_score` for Free queue ordering
5. When Free-line song plays, submitter's points reset to 0

## Backups

- Hourly JSON backups of `user_points` and `tiktok_accounts`
- Stored in `backups/` directory with timestamps
- Automatic cleanup: keeps last 48 backups (2 days)

## Architecture

### File Structure

```
.
├── main.py              # Bot entry point
├── database.py          # Database schema and connection pool
├── requirements.txt     # Python dependencies
├── .env                 # Environment configuration
├── cogs/
│   ├── submissions.py   # Submission commands and passive detection
│   ├── queue.py         # Queue management and /next command
│   ├── tiktok_integration.py  # TikTok Live connection and events
│   ├── tiktok_linking.py      # Handle linking commands
│   ├── luxury_coins.py        # Coins economy system
│   ├── persistent_embeds.py   # Auto-updating embeds
│   ├── admin.py               # Admin commands
│   └── points_sync.py         # Points sync and backups
├── tests/
│   └── test_bot.py      # Unit tests
└── backups/             # Hourly JSON backups
```

### Async Architecture

- Full async/await implementation
- AsyncPG connection pooling
- Background tasks for:
  - Embed refresh (10s loop)
  - Points sync (30s loop)
  - Watch time tracking (1min loop)
  - Hourly backups

### Error Handling

- Comprehensive try/except blocks
- Logging throughout all cogs
- Self-healing embeds on deletion
- Transaction rollback on failures

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Code Style

- PEP8 compliant
- Parameterized SQL queries (SQL injection safe)
- Type hints where applicable
- Comprehensive logging

## Deployment

1. Set up PostgreSQL database
2. Configure environment variables
3. Run bot with `python main.py`
4. Configure channels with admin commands
5. Connect to TikTok live stream
6. Start accepting submissions!

## License

MIT License
