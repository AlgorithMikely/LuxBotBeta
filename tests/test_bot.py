import pytest
import asyncio
from database import db


@pytest.fixture
async def setup_database():
    await db.connect()
    yield
    await db.disconnect()


@pytest.mark.asyncio
async def test_database_connection(setup_database):
    result = await db.fetchval('SELECT 1')
    assert result == 1


@pytest.mark.asyncio
async def test_create_submission(setup_database):
    user_id = 123456789
    username = "TestUser"
    artist = "Test Artist"
    song = "Test Song"
    
    public_id = await db.fetchval('''
        INSERT INTO submissions 
        (public_id, user_id, username, artist_name, song_name, queue_line)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING public_id
    ''', 'test123', user_id, username, artist, song, 'Free')
    
    assert public_id == 'test123'
    
    await db.execute('DELETE FROM submissions WHERE public_id = $1', 'test123')


@pytest.mark.asyncio
async def test_tiktok_account_creation(setup_database):
    handle = "test_handle"
    
    handle_id = await db.fetchval('''
        INSERT INTO tiktok_accounts (handle_name, points)
        VALUES ($1, $2)
        RETURNING handle_id
    ''', handle, 100)
    
    assert handle_id is not None
    
    points = await db.fetchval(
        'SELECT points FROM tiktok_accounts WHERE handle_id = $1',
        handle_id
    )
    
    assert points == 100
    
    await db.execute('DELETE FROM tiktok_accounts WHERE handle_id = $1', handle_id)


@pytest.mark.asyncio
async def test_luxury_coins_balance(setup_database):
    user_id = 987654321
    
    await db.execute('''
        INSERT INTO luxury_coins (user_id, balance)
        VALUES ($1, $2)
    ''', user_id, 500)
    
    balance = await db.fetchval(
        'SELECT balance FROM luxury_coins WHERE user_id = $1',
        user_id
    )
    
    assert balance == 500
    
    await db.execute('DELETE FROM luxury_coins WHERE user_id = $1', user_id)
