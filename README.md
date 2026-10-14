# ChatGPT Feature Scout (first working version)

A small Python project that checks official AI announcement feeds and sends a daily Discord DM with recent items. It is designed for free hosting with GitHub Actions.

## What it does

- Checks RSS/Atom feeds from OpenAI, Anthropic, Google AI Blog, and Hugging Face.
- Filters recent announcements and sends up to 8 links in a Discord DM.
- Remembers links in `seen.json` so the same items are not sent repeatedly.
- Runs daily at 08:00 UTC in GitHub Actions. You can also run it manually.
- Uses Python's standard library only.

**Important limitations:** feeds and their URLs can change; the first run may find no items if the feeds are unavailable or nothing recent matches. Announcements do not mean a feature has rolled out to every account. This bot is separate from ChatGPT and cannot make ChatGPT initiate a conversation.

## Part A — Create a Discord bot

1. Open https://discord.com/developers/applications and sign in.
2. Click **New Application**, name it `Feature Scout`, and create it.
3. In **Bot**, add/reset the bot token and copy it somewhere private temporarily. Never post it in chat or commit it to GitHub.
4. In **OAuth2 → URL Generator**, select the `bot` scope and the `Send Messages` permission. Generate the URL, open it, and add the bot to a server you control.
5. In Discord, enable **Developer Mode** under **User Settings → Advanced**.
6. Right-click your own profile and choose **Copy User ID**.
7. Send a message in the shared server so you know the bot is present. The script opens a DM using Discord's API; the bot and your account must share a server, and your privacy settings must allow the DM.

You do not need Message Content Intent or Administrator permission for this script.

## Part B — Put the project on GitHub

1. Go to https://github.com and create a new repository named `chatgpt-feature-scout`.
2. For the simplest free setup, make the repository **public**. Do not put secrets in the files. The token and user ID will be saved as GitHub Actions secrets.
3. Upload all files in this folder, including `.github/workflows/daily-scout.yml` and `seen.json`. Keep the folder structure exactly as shown.
4. In the repository, open **Settings → Secrets and variables → Actions → New repository secret**.
5. Add these two secrets:
   - `DISCORD_BOT_TOKEN` — the bot token from Discord Developer Portal.
   - `DISCORD_USER_ID` — your Discord user ID.
6. Open **Settings → Actions → General**. Under Workflow permissions, make sure workflows can read and write repository contents (or leave the workflow's `permissions` setting to grant contents write).
7. Open **Actions** and enable workflows if GitHub asks.

## Part C — Test it

1. Open **Actions → Daily Feature Scout → Run workflow**.
2. Wait for the run to finish and open its logs.
3. If successful, check your Discord DMs. If it fails to open a DM, confirm the bot and your account share a server and your privacy settings allow direct messages from server members.
4. If you want to test without sending a message on your computer, set `DRY_RUN=true` in your terminal environment before running `python scout.py`. In GitHub Actions, do not set DRY_RUN if you want a real DM.

## Run locally on Windows (optional)

1. Install Python 3.11 or newer from https://www.python.org/downloads/ and tick **Add Python to PATH** during installation.
2. Extract the ZIP.
3. Open the extracted folder in File Explorer. Click the address bar, type `cmd`, and press Enter.
4. Run:
   ```bat
   set DRY_RUN=true
   python scout.py
   ```
   This prints discoveries without sending a DM. To send a DM locally, set the two environment variables first:
   ```bat
   set DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN
   set DISCORD_USER_ID=YOUR_DISCORD_USER_ID
   python scout.py
   ```
   Replace the placeholders locally; do not paste real secrets into public files or screenshots.

## Common issues

- **401 Unauthorized:** the bot token is incorrect or was reset.
- **Could not open a DM / 403:** make sure you and the bot share a server, and check Discord privacy settings.
- **No items found:** that can be normal. Check feed warnings in the Actions logs. RSS endpoints sometimes change.
- **Scheduled run did not happen:** GitHub scheduled workflows can be delayed, especially on busy runners. The repository must have a default branch and the workflow file on it. GitHub can disable scheduled workflows on inactive public repositories.
- **Duplicate announcements:** `seen.json` is committed after each successful run. If the workflow cannot push commits, check workflow write permissions.

## Privacy and security

- Keep `DISCORD_BOT_TOKEN` in GitHub Secrets only.
- Never send the token to anyone, including ChatGPT.
- If the token is exposed, reset it in the Discord Developer Portal immediately.
- This project uses public RSS feeds and sends only announcement titles, snippets, and links to your own Discord DM.
