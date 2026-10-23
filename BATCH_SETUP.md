# Activation status

Repository: a7arjun/Cricket. Verified Studio channel: Cricket Ka Muqabla, UC41D3FpQrTMWb9o7qKanWug.

Twenty previews are ready in the private Drive queue. No YouTube upload has been confirmed. Studio identity verification and unattended OAuth credentials remain pending. No active release timestamps are set.

Requested cadence: 10:00 and 22:00 Asia/Kolkata. The user has authorized the first public video and subsequent twice-daily releases. No deletions are intended.

1. Complete the pending Google identity prompt and verify the channel.
2. Upload CK002 once and record its actual YouTube URL before scheduling the rest.
3. Configure OAuth secrets and verify Drive/Sheet/YouTube access from GitHub Actions. Do not reuse Pokemon channel credentials.
4. Add UPLOADING_PUBLIC and PUBLISHED to the queue dropdown; preserve all existing values and rows.
5. Populate a bounded public manifest for remaining episodes, excluding any already recorded upload. Set CRICKET_PUBLIC_ENABLED and CRICKET_BATCH_ENABLED to true only after verification.
6. Verify actual publication, saved receipt and Sheet URL. Do not claim the schedule is live before these checks succeed.

The scheduler delivers prepared episodes; it does not create new scripts or images. Do not alter batch-one outcomes when configuring delivery.
