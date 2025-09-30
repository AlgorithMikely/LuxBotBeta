import asyncio
from playwright.async_api import async_playwright, expect

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # The submission ID from the setup script
        submission_id = 5

        # Navigate to the player page
        url = f"http://127.0.0.1:8000/play/{submission_id}"
        await page.goto(url, wait_until="domcontentloaded")

        audio_player = page.locator("#audio-player")

        # The key test: Wait for the audio player to become visible.
        # The CSS `audio:not([controls]) { display: none; }` means the player
        # only becomes visible after our JavaScript adds the 'controls' attribute.
        # This is a robust way to test that our buffering logic worked.
        await expect(audio_player).to_be_visible(timeout=15000)

        # As a final check, ensure the 'loading' message is now hidden.
        loading_status = page.locator("#loading-status")
        await expect(loading_status).to_be_hidden()

        # Check that the song and artist information is correct.
        await expect(page.get_by_role("heading", name="Test Song")).to_be_visible()
        await expect(page.get_by_text("by Test Artist")).to_be_visible()

        # Take a screenshot of the final, loaded state.
        screenshot_path = "verification.png"
        await page.screenshot(path=screenshot_path)
        print(f"📸 Screenshot saved to {screenshot_path}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())