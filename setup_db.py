import asyncio
import os
import sys

from database import Database, QueueLine

async def setup_test_submission():
    """Create a test submission for verification."""
    db = Database()
    await db.initialize()

    # Define test data
    test_data = {
        'user_id': 12345,
        'username': 'TestUser',
        'artist_name': 'Test Artist',
        'song_name': 'Test Song',
        'queue_line': QueueLine.FREE.value
    }

    # Clean up previous test data if it exists
    all_subs = await db.get_queue_submissions(QueueLine.CALLS_PLAYED.value)
    for sub in all_subs:
        if sub['username'] == 'TestUser':
            await db.remove_submission(sub['id'])
            if os.path.exists(f"cache/{sub['id']}.mp3"):
                os.remove(f"cache/{sub['id']}.mp3")


    # Add a new submission to the Free line
    submission_id = await db.add_submission(
        user_id=test_data['user_id'],
        username=test_data['username'],
        artist_name=test_data['artist_name'],
        song_name=test_data['song_name'],
        link_or_file=f'https://cdn.discordapp.com/attachments/123/456/test.mp3',
        queue_line=QueueLine.FREE.value
    )

    # Move it to Calls Played
    await db.move_submission(submission_id, QueueLine.CALLS_PLAYED.value)

    # Create a dummy audio file for this submission ID
    mp3_path = f"cache/{submission_id}.mp3"
    if not os.path.exists(mp3_path):
        os.system(f"ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo -t 10 -q:a 9 -acodec libmp3lame {mp3_path} >/dev/null 2>&1")

    print(f"✅ Test submission #{submission_id} created and moved to Calls Played.")
    print(f"VERIFICATION_SUBMISSION_ID={submission_id}")


if __name__ == "__main__":
    asyncio.run(setup_test_submission())