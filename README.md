# Local Network Remote Monitor — Agent Only

This repo contains only the agent side.
The manager dashboard stays on your computer and is not in this repo.

## Agent behavior
- Starts on login (normal Startup entry)
- If closed, stays stopped until next restart
- Either side can stop or remove it
- Auto-checks GitHub every 60 seconds and instantly installs updates (no prompts)
- If offline when an update is published, it installs the update the next time it has internet
- Always forces the newest version (downgrades are overwritten on next check)
- Local network only, view + full control with adaptive quality (720p/30 up to 4K/60)

## Files
- `agent.py` — the agent
- `start.bat` — installer (only file needed on target computers)
- `requirements.txt`
- `version.txt` — current version (bump this to trigger updates)

## Setup on target computers
1. Make sure the repo is public (or the raw URLs are reachable)
2. Run `start.bat`
3. Agent starts on next login and keeps itself updated

## Manager
Keep `manager.py` only on your machine. It is not part of this repo.
