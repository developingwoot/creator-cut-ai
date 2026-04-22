# Project Overview

## What Is CreatorCutAI?

CreatorCutAI is a local-first desktop application that turns raw video footage into a
near-finished edited video. The user provides clips and a short story brief; the system
handles analysis, sequencing, filler removal, B-roll placement, and contextual sound
design — without the user touching a timeline.

---

## Problem

YouTube creators and documentary filmmakers spend 4–20 hours editing a single video.
Most of that time is mechanical:

- Scanning footage to find usable takes
- Trimming filler words and dead air
- Sequencing clips into a story arc
- Placing B-roll to cover cuts and add visual variety
- Layering in transition sounds and ambient audio

This work requires skill but not creativity. It is exactly the kind of pattern-matching
that a well-prompted vision model can do well.

---

## Target Users

**Primary:** Independent YouTube creators producing 10–30 minute video essays, vlogs,
or educational content. They have 2–10 raw clips per video, moderate editing skill, and
a clear sense of what story they want to tell.

**Secondary:** Documentary filmmakers in early cut stages — especially for interview-heavy
content where speaker analysis and B-roll placement are the dominant editing tasks.

---

## Core Features (v1)

| Feature | Description |
|---|---|
| Native file picker | Select clips directly from disk — nothing is copied or uploaded |
| Proxy generation | 1280×720 working copies for fast analysis (originals untouched) |
| Local transcription | Whisper runs on device; no audio leaves the machine |
| Per-clip analysis (Pass 1) | Claude analyses frames + transcript to score quality, find key moments, detect filler, and tag B-roll subjects |
| Edit planning (Pass 2) | Claude assembles a full edit plan from all clip analyses + the story brief |
| Human review gate | User must approve the edit plan before assembly starts |
| Filler removal | Contextual cut-detection for "um", "uh", "like", dead air, false starts |
| B-roll overlay | Inserts B-roll clips over A-roll cuts at Claude-suggested timecodes |
| Sound design | Adds transition sounds and ambient audio from the local SFX library |
| Final assembly | FFmpeg renders the approved plan to a single output file |

---

## Non-Goals for v1

- Cloud storage or sync
- User authentication or multi-user support
- Mobile or browser-based access
- Real-time collaboration
- Auto-publishing to YouTube
- Subtitle / caption export
- Color grading

---

## MVP Definition

A v1 ship requires:

1. User can open the app, select clips, enter a brief, and trigger analysis
2. Analysis completes without crashing for a 5-clip, 30-minute project
3. Edit plan is human-readable and can be approved or rejected with feedback
4. Assembly produces a playable MP4 with correct A/B roll and no audio glitches
5. Filler removal cuts are frame-accurate (no audible pop or visual flash)

---

## Roadmap Sketch

| Version | Theme |
|---|---|
| v1 | Local desktop tool, BYOK, full pipeline |
| v2 | Subscription tier, cloud backup, sidecar auto-launch, multi-project dashboard |
| v3 | Collaborative review, custom sound library upload, export to Premiere XML / DaVinci |
