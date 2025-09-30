# Discord Music Queue Bot

A TikTok-style music review queue system built with Discord.py v2.x featuring slash commands, interactive modals, and real-time queue management.

## Features

### User Features
- **Submit Music**: Use `/submit` to open an interactive form for music submissions
- **View Queue**: Use `/myqueue` to see all your active submissions across queue lines
- **Help**: Use `/help` to see available commands and queue information

### Queue System
- **Four Priority Lines**:
  - **BackToBack**: Highest priority queue
  - **DoubleSkip**: High priority queue
  - **Skip**: Medium priority queue  
  - **Free**: Standard submissions (1 per user limit)

### Admin Features
- **Queue Management**: Move submissions between lines with `/move`
- **Remove Submissions**: Remove submissions with `/remove`
- **Next Review**: Get next submission to review with `/next` (follows priority order)
- **Channel Setup**: Configure queue line channels with `/setline`

### Technical Features
- Real-time auto-updating pinned embeds in designated channels
- SQLite database for persistent storage
- Async/await for concurrency-safe operations
- Discord UI Modals and interactive components
- Comprehensive error handling and validation

## Setup on Windows

These instructions will guide you through setting up and running the bot on a local Windows machine.

### 1. Install Dependencies

- **Python**: Install Python 3.8 or newer from the [official website](https://www.python.org/downloads/windows/). Make sure to check the box that says "Add Python to PATH" during installation.
- **Git**: Install Git from the [official website](https://git-scm.com/download/win).

### 2. Clone the Repository

Open Command Prompt or PowerShell and run the following command to clone the repository:
```bash
git clone <repository_url>
cd <repository_name>
```

### 3. Create a Virtual Environment

It's recommended to use a virtual environment to manage dependencies:
```bash
python -m venv venv
venv\Scripts\activate
```

### 4. Install Requirements

Install the required Python packages:
```bash
pip install -r requirements.txt
```

### 5. Install FFmpeg

The bot requires FFmpeg for audio processing.

1.  **Download FFmpeg**:
    - Go to the [FFmpeg downloads page](https://www.gyan.dev/ffmpeg/builds/).
    - Download the latest "essentials" release build.
2.  **Extract FFmpeg**:
    - Extract the downloaded `.zip` file to a permanent location (e.g., `C:\ffmpeg`).
3.  **Add FFmpeg to Path**:
    - Search for "Edit the system environment variables" in the Start Menu and open it.
    - Click the "Environment Variables..." button.
    - In the "System variables" section, select the `Path` variable and click "Edit...".
    - Click "New" and add the path to the `bin` folder inside your FFmpeg directory (e.g., `C:\ffmpeg\bin`).
    - Click "OK" to close all windows.
    - **Verify the installation** by opening a new Command Prompt and running `ffmpeg -version`.

### 6. Configure Environment Variables

Create a file named `.env` in the project's root directory and add your bot token:

```
DISCORD_BOT_TOKEN=your_discord_bot_token_here
```

### 7. Run the Bot

Execute the `main.py` script to start the bot:
```bash
python main.py
```

## Setup on Replit

### 1. Environment Variables
Set the following environment variable in your Replit project:
- `DISCORD_BOT_TOKEN`: Your Discord bot token

To get a Discord bot token:
1. Go to https://discord.com/developers/applications
2. Create a new application
3. Go to the "Bot" section
4. Create a bot and copy the token
5. Add the token to your Replit environment variables

### 2. Bot Permissions
Your Discord bot needs the following permissions:
- Send Messages
- Use Slash Commands
- Manage Messages (for pinning)
- Read Message History
- Embed Links

### 3. Running the Bot
1. Install dependencies: `pip install -r requirements.txt`
2. Run the bot: `python main.py`

The bot will automatically:
- Initialize the SQLite database
- Load all command cogs
- Sync slash commands with Discord
- Set presence activity

## Usage

### Initial Setup
1. Use `/setline` commands to configure channels for each queue line
2. Users can start submitting music with `/submit`
3. Admins can manage the queue with admin commands

### Queue Management
- Submissions are processed in priority order: BackToBack → DoubleSkip → Skip → Free
- Each queue line displays real-time updates in its designated channel
- Users can only have one submission in the Free line
- Admins can move submissions between any lines

## Project Structure

```
├── main.py                 # Bot entry point and initialization
├── database.py            # SQLite database operations
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── cogs/
    ├── submission_cog.py  # User submission commands
    ├── queue_cog.py      # Queue display and user commands
    └── admin_cog.py      # Administrative commands
```

## Dependencies

- `discord.py>=2.3.2`: Discord API wrapper with slash command support
- `aiosqlite>=0.19.0`: Async SQLite database operations
- `python-dotenv>=1.0.0`: Environment variable management

## Commands Reference

### User Commands
- `/submit` - Open submission form (Artist, Song, Link/File)
- `/myqueue` - View your submissions across all lines
- `/help` - Show help information

### Admin Commands
- `/setline [line] [#channel]` - Set channel for queue line
- `/move [submission_id] [target_line]` - Move submission between lines
- `/remove [submission_id]` - Remove submission from queue
- `/next` - Get next submission to review (priority order)

## Database Schema

The bot uses SQLite with the following tables:
- `submissions`: Store music submissions with metadata
- `channel_settings`: Map queue lines to Discord channels
- `bot_settings`: Store bot configuration options