# Testing

## Strategy

Every pipeline module must be independently testable with a fixture clip. This means
no global state, no hardcoded paths, and every stage taking `project_id` as input and
deriving all paths from `storage/local.py`.

Tests are split into three categories:

| Marker | Speed | When to run | Requires |
|---|---|---|---|
| (no marker) | < 1s | Always — on every save | Nothing |
| `@pytest.mark.integration` | 1–10s | Before commit | FFmpeg on PATH, SQLite |
| `@pytest.mark.e2e` | 30s+ | Before release | FFmpeg, real fixture clips, Anthropic API key |

Run unit + integration tests:
```bash
cd backend && pytest tests/ -m "not e2e"
```

Run all including e2e:
```bash
cd backend && pytest tests/
```

---

## Test Layout

```
backend/tests/
├── conftest.py               ← fixtures: tmp_base_dir, db session, sample clips
├── fixtures/
│   ├── short_clip.mp4        ← 5-second synthetic clip (generated, committed)
│   ├── transcript_sample.json ← pre-made Whisper output for short_clip.mp4
│   └── clip_analysis_sample.json ← pre-made Pass 1 output for tests
├── test_config.py
├── test_storage_local.py
├── test_models.py
├── test_routes_projects.py
├── test_routes_upload.py
├── test_pipeline_proxy.py         @integration
├── test_pipeline_whisper.py       @integration
├── test_pipeline_pass1.py         @integration (mocks Claude API)
├── test_pipeline_pass2.py         @integration (mocks Claude API)
├── test_pipeline_filler.py        @integration
├── test_pipeline_assembly.py      @integration
└── test_e2e_full_pipeline.py      @e2e (real API key, real clip)
```

---

## Key Fixtures (`conftest.py`)

```python
@pytest.fixture
def tmp_base_dir(tmp_path):
    """Isolated base_dir for each test — no cross-test state."""
    return tmp_path / ".creatorcut"

@pytest.fixture
def db_session(tmp_base_dir):
    """In-memory SQLite session."""
    from storage.database import get_engine, create_tables
    from storage.local import db_path
    engine = get_engine(db_path(tmp_base_dir))
    create_tables(db_path(tmp_base_dir))
    with Session(engine) as session:
        yield session

@pytest.fixture
def sample_project(db_session):
    project = Project(name="Test Project")
    db_session.add(project)
    db_session.commit()
    return project
```

---

## What to Test Per Module

### `config.py` / `storage/local.py`

- `KeyManager` resolves env var first, then config file; raises `APIKeyMissingError` when none found
- `assert_safe_filename` raises `PathTraversalError` on `../` and `%2F`
- `ensure_project_dirs` creates all expected subdirectories

### Routes (`routes/projects.py`, `routes/upload.py`)

Use FastAPI's `TestClient`. Test:
- Happy path for each endpoint
- 404 on unknown project/clip IDs
- 409 when registering clips on a project in wrong status
- 422 on unsupported file extension
- 422 when file path does not exist (register route)

### Pipeline modules

Each pipeline module should have:
- A happy-path test using the fixture clip
- A test for the failure case (e.g. corrupted proxy input → `FFmpegError`)
- Claude API calls mocked with `unittest.mock.patch` — never make real API calls in `integration` tests

### E2E

One test that runs the full pipeline on `fixtures/short_clip.mp4` with a real API key.
Asserts the output MP4 exists, has non-zero size, and duration is within 20% of target.

---

## Fixture Clip Generation

The `fixtures/short_clip.mp4` should be a minimal synthetic clip — a few seconds of a
colour bar or talking-head stand-in. Generate it once with FFmpeg and commit it:

```bash
ffmpeg -f lavfi -i "color=c=blue:s=1280x720:d=5" \
       -f lavfi -i "sine=frequency=440:duration=5" \
       -c:v libx264 -c:a aac \
       backend/tests/fixtures/short_clip.mp4
```

This avoids committing large real footage while still exercising FFmpeg paths.

---

## CI Notes (future)

When CI is set up, run `pytest tests/ -m "not e2e"` only. E2E tests require a real
Anthropic API key and should be triggered manually before releases, not on every PR.
