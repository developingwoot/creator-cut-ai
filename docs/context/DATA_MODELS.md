# Data Models

All Pydantic and SQLModel schemas for CreatorCutAI.
Generated from / validated against the actual `backend/models/` implementation.

---

## Database Tables

### `projects`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT (UUID) | Primary key, generated at creation |
| `name` | TEXT | User-provided project name |
| `status` | TEXT (enum) | See `ProjectStatus` |
| `brief` | JSON | Serialised `StoryBrief` dict, nullable |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC, updated on every write |
| `error_message` | TEXT | Last pipeline error, nullable |

**ProjectStatus values:** `created`, `uploading`, `analyzing`, `planning`, `ready_to_review`, `assembling`, `complete`, `failed`

### `clips`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT (UUID) | Primary key |
| `project_id` | TEXT (FK → projects.id) | Indexed |
| `filename` | TEXT | Original filename |
| `original_path` | TEXT | Absolute path to original file |
| `proxy_path` | TEXT | Absolute path to proxy file, nullable |
| `duration_seconds` | REAL | From ffprobe, nullable |
| `file_size_bytes` | INTEGER | nullable |
| `codec` | TEXT | From ffprobe, nullable |
| `resolution` | TEXT | E.g. `"1920x1080"`, nullable |
| `fps` | REAL | From ffprobe, nullable |
| `order` | INTEGER | Display/processing order within project |
| `status` | TEXT (enum) | See `ClipStatus` |
| `transcript` | JSON | `{segments: [{start, end, text}]}`, nullable |
| `analysis` | JSON | Pass 1 result dict, nullable |
| `error_message` | TEXT | nullable |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC |

**ClipStatus values:** `uploaded`, `proxying`, `transcribing`, `analyzing`, `analyzed`, `failed`

### `edit_plans`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT (UUID) | Primary key |
| `project_id` | TEXT (FK → projects.id) | Indexed |
| `status` | TEXT (enum) | See `EditPlanStatus` |
| `segments` | JSON | List of `EditSegment` dicts |
| `total_duration_seconds` | REAL | nullable |
| `reasoning` | TEXT | Claude's edit rationale, nullable |
| `created_at` | DATETIME | UTC |
| `approved_at` | DATETIME | Set when user approves, nullable |

**EditPlanStatus values:** `draft`, `approved`, `rejected`

---

## Pydantic-Only Models (not database tables)

### `StoryBrief`

```python
class StoryBrief(BaseModel):
    title: str                          # non-blank
    story_summary: str                  # non-blank
    target_duration_seconds: int        # > 0
    tone: str                           # non-blank, e.g. "cinematic", "upbeat"
    key_moments: list[str] = []         # key scenes to include
    b_roll_preferences: list[str] = []  # preferred b-roll subjects/styles
```

Stored as a JSON column in `projects.brief`. Use `StoryBrief(**project.brief)` to
deserialise. Always validate before saving; `ProjectUpdate` re-validates the brief field.

### `EditSegment`

```python
class EditSegment(BaseModel):
    order: int
    clip_id: str
    source_start: float    # seconds from clip start
    source_end: float      # must be > source_start
    is_broll: bool = False
    narration_note: str = ""
    b_roll_overlays: list[BRollPlacement] = []
    sound_cues: list[SoundDesignCue] = []
```

### `BRollPlacement`

```python
class BRollPlacement(BaseModel):
    clip_id: str           # which clip provides the b-roll
    start_seconds: float   # when in the timeline the overlay starts
    end_seconds: float
    description: str       # what's happening in this b-roll shot
```

### `SoundDesignCue`

```python
class SoundDesignCue(BaseModel):
    sfx_id: str            # ID from assets/sfx/manifest.json
    at_seconds: float      # when in the timeline to play
    duration_seconds: float
    volume: float = 1.0    # 0.0–1.0
```

---

## API Request/Response Models

### `ProjectCreate`
```python
class ProjectCreate(BaseModel):
    name: str          # non-blank
    brief: StoryBrief | None = None
```

### `ProjectRead`
```python
class ProjectRead(BaseModel):
    id: str
    name: str
    status: ProjectStatus
    brief: dict | None
    created_at: datetime
    updated_at: datetime
    error_message: str | None
```

### `ProjectUpdate`
```python
class ProjectUpdate(BaseModel):
    name: str | None = None
    brief: StoryBrief | None = None
    status: ProjectStatus | None = None
    error_message: str | None = None
```

### `ClipRead`
```python
class ClipRead(BaseModel):
    id: str
    project_id: str
    filename: str
    duration_seconds: float | None
    file_size_bytes: int | None
    codec: str | None
    resolution: str | None
    fps: float | None
    order: int
    status: ClipStatus
    transcript: dict | None
    analysis: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
```

### `EditPlanRead`
```python
class EditPlanRead(BaseModel):
    id: str
    project_id: str
    status: EditPlanStatus
    segments: list | None      # list of EditSegment dicts
    total_duration_seconds: float | None
    reasoning: str | None
    created_at: datetime
    approved_at: datetime | None
```

### `EditPlanApprove`
```python
class EditPlanApprove(BaseModel):
    approved: bool
    feedback: str | None = None   # used if rejected, to regenerate
```

---

## Pass 1 Analysis Output (stored in `clips.analysis`)

Claude returns this JSON for each clip. Structure is validated with `InvalidClaudeResponseError` if malformed.

```json
{
  "quality_score": 0.85,
  "key_moments": [
    {"start": 12.5, "end": 18.2, "description": "Subject explains the core concept clearly"}
  ],
  "filler_spans": [
    {"start": 4.1, "end": 4.6, "word": "um"},
    {"start": 22.0, "end": 22.4, "word": "like"}
  ],
  "b_roll_tags": ["outdoor", "wide shot", "golden hour"],
  "scene_mood": "energetic",
  "is_usable": true,
  "notes": "Good lighting, slight camera shake at 0:45"
}
```

## Pass 2 Edit Plan Output (stored in `edit_plans.segments`)

```json
{
  "segments": [
    {
      "order": 0,
      "clip_id": "uuid-of-clip",
      "source_start": 12.5,
      "source_end": 18.2,
      "is_broll": false,
      "narration_note": "Opening hook — strong statement",
      "b_roll_overlays": [],
      "sound_cues": []
    }
  ],
  "total_duration_seconds": 487.3,
  "reasoning": "Started with the strongest hook from clip 3..."
}
```
