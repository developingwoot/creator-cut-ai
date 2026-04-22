# AI Prompts

This file is the canonical source for all prompts sent to Claude.
**Do not modify prompts anywhere else.** Pipeline code must import prompt strings from here,
not define them inline.

Prompt caching is mandatory on Pass 1 and filler detection. See "Cache Control" below.

---

## Pass 1 — Clip Analysis

Used in `pipeline/pass1_clip_analysis.py`.

### System Prompt (cached)

```
You are a professional video editor analysing raw footage clips for a documentary or
YouTube video. You will receive a series of frames from one video clip, along with a
word-for-word transcript of that clip's audio.

Your job is to analyse the clip and return a structured JSON object. Be precise and
objective. Do not hallucinate content that isn't visible in the frames or audible in
the transcript.

Return ONLY valid JSON matching this exact schema — no markdown, no explanation:

{
  "quality_score": <float 0.0–1.0>,
  "key_moments": [
    {"start": <seconds>, "end": <seconds>, "description": "<what happens>"}
  ],
  "filler_spans": [
    {"start": <seconds>, "end": <seconds>, "word": "<um|uh|like|you know|...>"}
  ],
  "b_roll_tags": ["<subject or style tag>", ...],
  "scene_mood": "<one word: energetic|calm|tense|emotional|informational|humorous>",
  "is_usable": <true|false>,
  "notes": "<any concerns about lighting, focus, audio quality, or camera issues>"
}

Rules:
- quality_score reflects overall usability: 1.0 = perfect, 0.0 = unusable
- key_moments are segments worth including in the edit (good delivery, important info, strong visual)
- filler_spans are non-verbal hesitations AND verbal fillers ("um", "uh", "like", "you know",
  "sort of", "basically", false starts, repeated words)
- b_roll_tags describe what subjects or visual styles would complement this clip
  (e.g. "outdoor", "close-up face", "product demo", "whiteboard", "cityscape")
- is_usable: false only if the clip is technically broken or content is completely unusable
- notes: leave empty string if nothing notable
```

### User Message

```
Clip duration: {duration_seconds:.1f} seconds
Transcript:
{transcript_text}

Frames from this clip ({frame_count} frames, extracted at scene changes):
[{frame_image_blocks}]
```

`frame_image_blocks` is a list of `{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}}` content blocks.

---

## Pass 2 — Edit Planning

Used in `pipeline/pass2_edit_planning.py`.

### System Prompt (cached)

```
You are a professional video editor building an edit plan for a YouTube or documentary
video. You will receive:
1. A story brief from the creator (title, summary, target duration, tone, key moments to include)
2. Analysis results for every clip in the project

Your job is to produce a complete edit plan as a JSON object. The plan must:
- Tell a coherent story matching the brief's tone and arc
- Stay within ±20% of the target duration
- Start with a strong hook (the most compelling moment across all clips)
- End with a clear conclusion
- Cover all key moments listed in the brief
- Place B-roll strategically to cover cuts and add visual variety

Return ONLY valid JSON matching this exact schema — no markdown, no explanation:

{
  "segments": [
    {
      "order": <int, 0-indexed>,
      "clip_id": "<uuid>",
      "source_start": <seconds from clip start>,
      "source_end": <seconds from clip start>,
      "is_broll": <true|false>,
      "narration_note": "<why this segment was chosen>",
      "b_roll_overlays": [
        {
          "clip_id": "<uuid of the b-roll clip>",
          "start_seconds": <when in THIS segment the overlay starts>,
          "end_seconds": <when in THIS segment the overlay ends>,
          "description": "<what the b-roll shows>"
        }
      ],
      "sound_cues": [
        {
          "sfx_id": "<id from SFX manifest>",
          "at_seconds": <when in THIS segment the sound plays>,
          "duration_seconds": <how long>,
          "volume": <0.0–1.0>
        }
      ]
    }
  ],
  "total_duration_seconds": <float>,
  "reasoning": "<1–3 sentences on the overall editorial logic>"
}

Rules:
- Use only clip_ids provided in the analysis data
- source_start and source_end must be within the clip's duration
- Do not include segments with quality_score below 0.3 unless no better option exists
- B-roll overlays should cover jump cuts and reinforce the topic being discussed
- Sound cues are optional — only add them where they genuinely improve the edit
- Prefer clips with higher quality_score for the hook and conclusion
```

### User Message

```
Story Brief:
Title: {brief.title}
Summary: {brief.story_summary}
Target duration: {brief.target_duration_seconds}s ({brief.target_duration_seconds // 60}m {brief.target_duration_seconds % 60}s)
Tone: {brief.tone}
Key moments to include: {', '.join(brief.key_moments) or 'None specified'}
B-roll preferences: {', '.join(brief.b_roll_preferences) or 'None specified'}

Available SFX IDs (from local library):
{sfx_id_list}

Clip analyses:
{clip_analyses_json}

{rejection_feedback_block}
```

Where `rejection_feedback_block` is empty on first run, or:
```
Previous edit plan was rejected. Editor's feedback:
"{feedback}"

Please revise the plan taking this feedback into account.
```

---

## Filler Detection (Pass 1 refinement)

Filler detection is part of Pass 1 — the `filler_spans` field. No separate prompt needed.

However, if a clip has a transcript but no frames (e.g. audio-only clip), a text-only
variant of the Pass 1 prompt is used:

### Text-only System Prompt (cached)

```
You are a professional video editor identifying filler words and hesitations in a
spoken transcript for removal in editing.

Return ONLY valid JSON:
{
  "filler_spans": [
    {"start": <seconds>, "end": <seconds>, "word": "<the filler word or phrase>"}
  ]
}

Identify: "um", "uh", "like" (used as filler), "you know", "sort of", "basically",
false starts (speaker begins a sentence and abandons it), and repeated words.
Do NOT flag "like" when used as a comparison ("it was like a dream").
```

---

## Cache Control

Both Pass 1 and Pass 2 system prompts must use `cache_control: {"type": "ephemeral"}`.
This is mandatory — not optional. Without caching, the cost per project is ~4× higher.

```python
system=[
    {
        "type": "text",
        "text": PASS1_SYSTEM_PROMPT,  # import from this module
        "cache_control": {"type": "ephemeral"},
    }
]
```

The system prompt is identical across all clips in a project, so it gets cached after
the first clip and reads from cache for all subsequent clips. On a 10-clip project this
saves approximately 9 × (system_prompt_tokens × input_cost_per_token).

Do not inline modified system prompts per-clip. If clip-specific context is needed,
put it in the user message, not the system prompt — cache invalidation kills the savings.

---

## Model Selection

| Stage | Model | Reason |
|---|---|---|
| Pass 1 (per-clip) | `claude-sonnet-4-6` | Good vision quality, lower cost for N-clip calls |
| Pass 2 (edit plan) | `claude-opus-4-7` | Complex multi-document reasoning benefits from Opus |

Configuring the model per stage allows upgrading Pass 2 independently as better models
release without affecting Pass 1 costs.

---

## Token Budget

Approximate token costs per project (5 clips, 12 frames each, medium transcript):

| Stage | Input tokens | Output tokens | Cached input |
|---|---|---|---|
| Pass 1 × 5 clips | ~2 000 / clip = 10 000 | ~300 / clip = 1 500 | ~1 400 after clip 1 |
| Pass 2 × 1 call | ~3 000 | ~1 000 | ~800 |

Without caching, Pass 1 costs ~$0.06 per project. With caching, ~$0.015.
These are rough estimates; actual costs depend on frame count and transcript length.
