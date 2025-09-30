import asyncio
import os
import sys
import aiohttp
import ffmpeg
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

# Add project root to Python path to allow imports from other directories
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import Database

# Create necessary directories
os.makedirs("cache", exist_ok=True)

app = FastAPI()
templates = Jinja2Templates(directory="web/templates")

# Initialize database
db = Database()

async def download_file(url: str, destination: str):
    """Asynchronously download a file."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                with open(destination, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)
            else:
                raise HTTPException(status_code=response.status, detail="Failed to download file")

async def convert_to_mp3(input_path: str, output_path: str):
    """Convert an audio file to MP3 using ffmpeg."""
    try:
        process = (
            ffmpeg
            .input(input_path)
            .output(output_path, acodec='libmp3lame', audio_bitrate='192k')
            .overwrite_output()
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )
        await process.wait()
    except ffmpeg.Error as e:
        # If conversion fails, try to just copy the file if it's already an MP3
        if input_path.lower().endswith('.mp3'):
            import shutil
            shutil.copy(input_path, output_path)
        else:
            raise HTTPException(status_code=500, detail=f"FFmpeg error: {e.stderr.decode()}")


@app.get("/play/{submission_id}", response_class=HTMLResponse)
async def play_submission(request: Request, submission_id: int):
    """
    Prepare and serve the web player for a given submission.
    This endpoint downloads the audio, converts it to MP3, and serves the player page.
    """
    await db.initialize()
    submission = await db.get_submission_by_id(submission_id)

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    file_url = submission['link_or_file']

    # We only process file uploads, not external links
    if not file_url.startswith('https://cdn.discordapp.com'):
        raise HTTPException(status_code=400, detail="This player only supports direct file uploads, not external links.")

    original_filename = file_url.split('/')[-1]
    original_filepath = os.path.join("cache", f"original_{submission_id}_{original_filename}")
    cached_mp3_path = os.path.join("cache", f"{submission_id}.mp3")

    # Download and convert only if the cached file doesn't exist
    if not os.path.exists(cached_mp3_path):
        try:
            # Download the original file
            await download_file(file_url, original_filepath)

            # Convert to MP3
            await convert_to_mp3(original_filepath, cached_mp3_path)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
        finally:
            # Clean up the original downloaded file
            if os.path.exists(original_filepath):
                os.remove(original_filepath)

    return templates.TemplateResponse("player.html", {
        "request": request,
        "submission": submission,
        "audio_url": f"/audio/{submission_id}.mp3"
    })

@app.get("/audio/{submission_id}.mp3")
async def get_audio_file(submission_id: int):
    """Serve the cached MP3 audio file."""
    cached_mp3_path = os.path.join("cache", f"{submission_id}.mp3")

    if not os.path.exists(cached_mp3_path):
        raise HTTPException(status_code=404, detail="Audio file not found. It may not have been processed yet.")

    return FileResponse(cached_mp3_path, media_type="audio/mpeg")

@app.on_event("startup")
async def startup_event():
    """Initialize the database on application startup."""
    await db.initialize()