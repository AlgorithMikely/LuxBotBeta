# Discord Music Review Bot

## Overview

A Discord bot designed for music review streaming with TikTok Live integration. The bot manages music submissions through a sophisticated 9-tier priority queue system, tracks viewer engagement across TikTok Live events, and implements a virtual economy (Luxury Coins) to incentivize participation. Built with Python, Discord.py, and PostgreSQL, it provides real-time queue management through auto-updating embeds and combines Discord interactions with TikTok Live streaming metrics.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Framework
- **Core Technology**: Python 3.10+ with Discord.py bot framework
- **Architecture Pattern**: Cog-based modular system where each major feature is isolated into separate cog modules
- **Bot Design**: Hybrid command system supporting both slash commands (app_commands) and message content processing for passive link detection
- **Rationale**: Cog architecture enables clean separation of concerns and hot-reloading of features without full bot restarts

### Database Layer
- **Primary Database**: PostgreSQL with asyncpg driver for async/await operations
- **Connection Management**: Connection pooling (5-20 connections) with 60-second command timeout
- **Schema Design**: 
  - Live sessions tracking with start/end timestamps
  - TikTok accounts table with Discord linking capability
  - Submissions queue with priority tiers and scoring system
  - User points and watch time tracking
  - Persistent embed configurations
  - Interaction logging for analytics
- **Data Persistence**: Hourly JSON backups for user_points and tiktok_accounts tables
- **Rationale**: PostgreSQL chosen for relational data integrity and complex query support (scoring, queue ordering). Connection pooling prevents resource exhaustion during high load.

### Queue Management System
- **9-Tier Priority Structure**: 
  1. 25+ Skip (highest)
  2. 20 Skip
  3. 15 Skip
  4. 10 Skip
  5. 5 Skip
  6. Free (score-based ordering)
  7. Pending Skips
  8. Songs Played
  9. Removed (lowest)
- **Free Queue Scoring**: Combines Discord user points + linked TikTok account points, synced every 30 seconds
- **Concurrency Safety**: Row-level locking (FOR UPDATE SKIP LOCKED) prevents race conditions when retrieving next submission
- **Rationale**: Tiered system monetizes skip privileges while Free tier remains meritocratic through engagement scoring

### TikTok Live Integration
- **Event Processing**: Real-time webhook listeners for:
  - Gifts (coin conversion at 2 coins per 100 TikTok coins)
  - Joins, likes, comments, shares, follows
  - Watch time tracking (1 coin per 30 minutes)
- **Session Management**: Live session tracking with start/end timestamps, interaction logging per session
- **Account Linking**: Manual Discord-to-TikTok handle linking with autocomplete, optional admin force-linking
- **Gift Streak Detection**: In-memory tracking to prevent duplicate gift processing
- **Rationale**: Bridges platform gap, allowing TikTok viewers to earn queue priority through Discord-linked accounts

### Luxury Coins Economy
- **Earning Mechanisms**:
  - Watch time: 1 coin per 30 minutes (tracked via 1-minute loop)
  - Gifts: 2 coins per 100 TikTok coins gifted
- **Point Synchronization**: 30-second sync loop updates Free queue submission scores
- **Storage**: Separate user_points (Discord) and tiktok_accounts points tables, combined for scoring
- **Rationale**: Dual-source point system incentivizes both Discord and TikTok engagement without platform bias

### Submission System
- **Input Methods**:
  1. Slash commands with artist/song metadata
  2. File uploads (MP3, M4A, WAV, FLAC up to 25MB)
  3. Passive link detection in submission channel messages
- **Platform Support**: SoundCloud, Spotify, YouTube, Deezer, Ditto (Apple/iTunes explicitly rejected)
- **Validation**: URL validation via validators library, file type/size enforcement
- **File Storage**: Local filesystem with UUID-based naming
- **Rationale**: Multi-modal submission reduces friction—users can paste links naturally or use structured commands

### Real-Time Embed System
- **Auto-Updating Embeds**: 10-second refresh loop for:
  - Live queue display (paginated)
  - Reviewer main queue
  - Reviewer pending skips
- **Content Hashing**: MD5 hash comparison prevents unnecessary Discord API calls when content unchanged
- **Staggered Updates**: 1-second delay between embed updates to avoid rate limits
- **Persistent Storage**: Embed configurations stored in database with active/inactive flags
- **Rationale**: Live queue visibility critical for transparency; hash comparison minimizes API overhead

### Admin Tools
- **Channel Configuration**: Slash commands to set submission channel, create embed instances
- **Force Linking**: Admin override for TikTok-Discord account linking
- **Metrics Reporting**: Exportable interaction data for stream analytics
- **Configuration Storage**: Database-backed bot_config table for runtime settings
- **Rationale**: Centralized admin controls simplify multi-server deployments and troubleshooting

### Background Task Management
- **Task Loops**:
  - Watch time tracker (1 minute)
  - Embed refresh (10 seconds)
  - Score sync (30 seconds)
  - Hourly backups (60 minutes)
- **Lifecycle Hooks**: Proper task cancellation in cog_unload prevents orphaned loops
- **Bot Ready Wait**: Tasks wait for bot.wait_until_ready() before execution
- **Rationale**: Discord.py task system ensures reliable periodic execution with automatic reconnection handling

## External Dependencies

### Third-Party Services
- **Discord API**: Primary interaction platform via discord.py library (v2.3.0+)
  - Webhooks for message handling
  - Slash command registration
  - Embed rendering and updates
- **TikTokLive API**: Real-time event streaming (v5.0.0+)
  - Gift, join, like, comment, share, follow events
  - Room user sequence tracking
  - Connection state management

### Database
- **PostgreSQL**: Relational database for persistent storage
  - asyncpg driver for async operations
  - Connection pooling configuration
  - Schema migrations via runtime execute statements

### Python Libraries
- **Core Dependencies**:
  - `discord.py` (>=2.3.0): Bot framework and Discord API wrapper
  - `asyncpg` (>=0.29.0): PostgreSQL async driver
  - `TikTokLive` (>=5.0.0): TikTok Live event streaming
  - `python-dotenv` (>=1.0.0): Environment variable management
  - `validators` (>=0.22.0): URL validation for submissions
  - `aiofiles` (>=23.2.1): Async file I/O for backups and uploads

### Environment Configuration
- **Required Variables**:
  - `DISCORD_BOT_TOKEN`: Bot authentication
  - `DATABASE_URL`: PostgreSQL connection string (format: postgresql://user:password@host:port/database)
  - `ALLOW_ANY_HANDLE_LINKING`: Boolean flag for TikTok linking restrictions (default: false)

### File System
- **Local Storage**:
  - `/backups`: Hourly JSON dumps of points and accounts
  - Uploaded music files stored with UUID naming scheme
  - No CDN integration—files remain local to bot instance