# LCN Market Television — isolated TEST encoder

This repository contains only television-test rendering code and TV-safe quote snapshots. It does not contain the LCN backend, database credentials, Discord tokens, orders, balances, or financial records.

GitHub Actions turns `tv-render/feed.json` into a one-minute HLS video batch with six 10-second quote/headline states, then uploads the six MPEG-TS segments to the separate public HLS Site using a short-lived GitHub OIDC token. A completed batch is published atomically only after all six segments arrive. PMMS playback uses `https://lcn-market-television-hls.sturdyrain.chatgpt.site/hls/lcn-market-test.m3u8` after the first batch is published.

`feed.json` starts with mock data. Real LCN quote snapshots may be written only by the separate, Docker-local, read-only TV bridge after end-to-end mock playback is confirmed. The GitHub runner performs all video encoding; the local bridge does not use FFmpeg or OBS.

This is TEST mode, not an order-entry screen or live-trading authority. The original working PMMS URL remains separate.
