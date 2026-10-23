# Cricket Ka Muqabla

Separate cricket Shorts workflow in a7arjun/Cricket. The Pokemon repository is independent.

Twenty prepared episodes use illustrated player portraits and actions, Hinglish narration, schematic ball paths and sourced cricket facts. The first batch is preserved as approved. What-if outcomes are entertainment, not forecasts. Source attribution and AI context belong in each upload description.

## Delivery

The runner reads one episode from the Google Sheets queue, downloads its checksummed Drive job, assets and ready video, verifies the authenticated YouTube channel, uploads once and records the resulting URL. Uncertain uploads are blocked for review instead of retried. Existing YouTube URLs prevent duplicate uploads.

The requested slots are 10:00 and 22:00 Asia/Kolkata. The batch scheduler checks only the current day and allows at most two episodes. GitHub jobs may start late. This schedules uploads at those times; it does not pre-upload to YouTube's native scheduler. `episodes` remains empty until authorization and a real upload are verified. `planned_episodes` is the approved content order.

## Configuration

Set encrypted repository secrets CRICKET_DRIVE_CLIENT_ID, CRICKET_DRIVE_CLIENT_SECRET, CRICKET_DRIVE_REFRESH_TOKEN, CRICKET_YOUTUBE_CLIENT_ID, CRICKET_YOUTUBE_CLIENT_SECRET and CRICKET_YOUTUBE_REFRESH_TOKEN. Never commit credentials or private assets.

Set variables CRICKET_QUEUE_ID and CRICKET_YOUTUBE_CHANNEL_ID. Browser login and ChatGPT connectors do not supply OAuth secrets to GitHub Actions. Drive credentials need file-read and Sheets-edit access; YouTube credentials need upload and channel-read access for the cricket channel.

Public delivery requires both `--publish-public` (or batch `--execute-public`) and CRICKET_PUBLIC_ENABLED=true. The reviewed job envelopes remain private by default; a job cannot turn on public publishing. Set CRICKET_BATCH_ENABLED=true only after a bounded manifest is configured and a real round trip succeeds. Until then the scheduler is disabled.

Manual private validation remains available in the Cricket private preview workflow. Public mode writes UPLOADING_PUBLIC and then PUBLISHED; the queue status dropdown must allow those values before activation.

## Validation

Run `python -m unittest discover -s tests -v`. Tests cover bounded schedules, duplicates, score consistency, public opt-in and the requested India-time slots. Local tests do not demonstrate live OAuth or successful YouTube publishing.

Prepared videos need no external image or TTS API during delivery. Generating future episodes is a separate authoring step and is not automated by this scheduler.
