# Contributing to PetitionsRadar

Thanks for your interest in contributing! PetitionsRadar is a mobile-first petition discovery app that helps young Germans find, share, and act on petitions across multiple platforms. This guide covers how to contribute code, report issues, and extend the app.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Backend Development](#backend-development)
- [Frontend Development](#frontend-development)
- [Adding a Petition Source](#adding-a-petition-source)
- [Code Style](#code-style)
- [Testing](#testing)
- [PR Workflow](#pr-workflow)
- [Issue Templates](#issue-templates)
- [Legal Requirements](#legal-requirements)
- [Code of Conduct](#code-of-conduct)

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- PostgreSQL 15+
- Redis 7+
- Expo CLI (`npm install -g expo-cli`)
- Playwright (for scraping)

### Backend Setup

```bash
git clone https://github.com/<your-username>/petitionsradar.git
cd petitionsradar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure environment variables (copy `.env.example` to `.env` and fill in):

```bash
cp .env.example .env
```

Start the backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd mobile
npm install
npx expo start
```

Scan the QR code with Expo Go on your phone, or press `i` / `a` for iOS/Android simulators.

### Database Setup

```bash
# Create the database
createdb petitionsradar

# Run migrations
alembic upgrade head

# Seed initial data (optional)
python scripts/seed.py
```

Verify everything works:

```bash
# Backend health check
curl http://localhost:8000/api/health

# Run backend tests
pytest tests/

# Run frontend tests
cd mobile && npm test
```

---

## Project Structure

```
petitionsradar/
├── app/                    # FastAPI backend
│   ├── api/                # API route handlers
│   ├── models/             # SQLAlchemy ORM models
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # Business logic layer
│   ├── scrapers/           # Petition source scrapers
│   └── main.py             # FastAPI app entrypoint
├── mobile/                 # React Native + Expo app
│   ├── app/                # expo-router file-based routes
│   ├── components/         # Reusable UI components
│   ├── hooks/              # Custom React hooks
│   ├── services/           # API client, push notifications
│   └── types/              # TypeScript type definitions
├── tests/                  # Backend tests (pytest)
│   ├── test_api/           # API endpoint tests
│   ├── test_scrapers/      # Scraper tests
│   └── test_services/      # Service layer tests
├── scripts/                # Utility scripts
├── docs/                   # Documentation
│   └── QUALITY_BAR.md      # Quality standards this project enforces
├── alembic/                # Database migrations
├── GOAL.md                 # Project vision and success criteria
├── PO_DECISIONS.md         # Product decisions and priorities
└── CONTRIBUTING.md         # This file
```

---

## Backend Development

### Python Standards

All backend code must meet these requirements (see `docs/QUALITY_BAR.md` for full spec):

- **Type hints** on all function signatures
- **Docstrings** on all public functions (Google style)
- **Pydantic models** for all API request/response schemas — no raw dicts
- **Error handling** — all external calls (scraping, network) wrapped in try/except with logging
- **No bare except** — always catch specific exceptions (`except requests.HTTPError`, not `except Exception`)
- **Async where possible** — scraping and API endpoints use async/await
- **Config via environment** — no hardcoded URLs, ports, or DB credentials. Use `pydantic-settings` or `os.environ`

### API Design

The backend serves a RESTful JSON API:

```
GET    /api/petitions              # List petitions (paginated)
GET    /api/petitions/{id}         # Get single petition
POST   /api/petitions/{id}/share   # Generate share image
GET    /api/health                 # Health check (returns 200 + JSON)
```

All list endpoints must:
- Return the envelope: `{ "data": [...], "meta": { "total": N, "page": P, "per_page": 20 } }`
- Support pagination (default 20, max 50 items per page)
- Use proper HTTP status codes (200, 201, 400, 404, 500)
- Apply rate limiting on scrape-triggerating endpoints

### Example: API Endpoint

```python
# app/api/petitions.py
from fastapi import APIRouter, Depends, Query
from app.schemas.petition import PetitionResponse, PaginatedResponse
from app.services.petition_service import PetitionService

router = APIRouter(prefix="/api/petitions", tags=["petitions"])

@router.get("", response_model=PaginatedResponse[PetitionResponse])
async def list_petitions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    topic: str | None = None,
    source: str | None = None,
    service: PetitionService = Depends(),
) -> PaginatedResponse[PetitionResponse]:
    """List petitions with optional filters.

    Args:
        page: Page number (1-indexed).
        per_page: Items per page (max 50).
        topic: Filter by topic slug (e.g. "klima", "bildung").
        source: Filter by source platform (e.g. "bundestag").
        service: Injected petition service.

    Returns:
        Paginated list of petitions matching filters.
    """
    return await service.list_petitions(
        page=page, per_page=per_page, topic=topic, source=source
    )
```

---

## Frontend Development

### React Native Standards

All frontend code must meet these requirements:

- **Functional components + hooks only** — no class components
- **Typed props** with TypeScript interfaces — no `any` types; use `unknown` + type narrowing
- **expo-router** for navigation (file-based routing under `mobile/app/`)
- **FlatList** for petition feeds — never `ScrollView` with mapped children
- **Reanimated** for animations — use worklets, not JS-driven animations
- **Platform-specific code** via `Platform.select()` for iOS/Android differences
- **SafeAreaView** on all screens — respect notches and status bars
- **Touch targets ≥ 44px** — Apple HIG / Material Design minimum

### Petition Card Component

The core UI component. Must display:

| Element | Details |
|---------|---------|
| Title | Truncated to 2 lines, tap to expand |
| Source badge | Color-coded platform indicator |
| Progress bar | Current signatures / goal |
| Deadline | Countdown (if applicable) |
| Sign button | Opens `source_url` in system browser |
| Share icon | Opens native share sheet |

### Example: Component

```tsx
// mobile/components/PetitionCard.tsx
import { View, Text, Pressable, Linking, Platform } from 'react-native';
import { Share } from 'expo-sharing';
import type { Petition } from '../types/petition';

interface PetitionCardProps {
  petition: Petition;
  onSign?: (petition: Petition) => void;
}

export function PetitionCard({ petition, onSign }: PetitionCardProps) {
  const handleSign = () => {
    Linking.openURL(petition.source_url);
    onSign?.(petition);
  };

  return (
    <View style={styles.card}>
      <Text numberOfLines={2} style={styles.title}>
        {petition.title}
      </Text>
      <SourceBadge source={petition.source} />
      <ProgressBar current={petition.signature_count} goal={petition.signature_goal} />
      {petition.deadline && <DeadlineCountdown deadline={petition.deadline} />}
      <Pressable onPress={handleSign} style={styles.signButton}>
        <Text>Sign on {petition.source}</Text>
      </Pressable>
    </View>
  );
}
```

### Accessibility

- **WCAG 2.1 AA** — semantic roles, `accessibilityLabel` on all touchable elements
- **Color contrast ≥ 4.5:1** for all text
- **Dynamic Type** — respect iOS Dynamic Type and Android font scaling
- Test with VoiceOver (iOS) and TalkBack (Android)

---

## Adding a Petition Source

PetitionsRadar aggregates from German petition platforms. To add a new source:

### Step-by-step

1. **Verify the platform** is a German petition site with public listings (no auth required)
2. **Create the scraper** at `app/scrapers/<platform_name>.py`
3. **Subclass `BaseScraper`** and implement `fetch_petitions()` and `is_available()`
4. **Register it** in `app/scrapers/__init__.py`
5. **Add tests** at `tests/test_scrapers/test_<platform_name>.py`
6. **Update the enum** in `app/models/petition.py` to include the new source

### BaseScraper Interface

```python
# app/scrapers/base.py
from abc import ABC, abstractmethod
from app.models.petition import Petition

class BaseScraper(ABC):
    name: str = "my_platform"
    base_url: str = ""

    @abstractmethod
    async def fetch_petitions(self) -> list[Petition]:
        """Scrape public petition listings and return structured data.

        Must:
        - Only access public pages (no authentication bypass)
        - Respect rate limits (min 5s between requests)
        - Handle network errors gracefully with logging
        - Return a flat list of Petition objects
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """Return True if the platform is reachable right now."""
```

### Rules

- **No authentication bypass** — only scrape publicly accessible listing pages
- **Rate limit** — minimum 5 seconds between requests to the same domain
- **No signature submission** — we are a discovery layer, not a petition platform
- **Store only metadata** — title, description, signature count, deadline, source URL
- **No personal data** — never store user information from petition pages

---

## Code Style

### Backend (Python)

```bash
# Format
black app/ tests/

# Lint
ruff check app/ tests/
ruff format --check app/ tests/

# Type check
mypy app/
```

### Frontend (TypeScript)

```bash
cd mobile

# Format
npx prettier --write .

# Lint
npx eslint .

# Type check
npx tsc --noEmit
```

### Before Every PR

Run the full check suite:

```bash
# Backend
black --check app/ tests/
ruff check app/ tests/
mypy app/
pytest tests/ -v

# Frontend
cd mobile && npm run lint && npm test
```

---

## Testing

### Backend Tests (pytest)

- **Coverage ≥ 80%** on API routes and scraper modules
- One test file per module: `tests/test_<module>.py`
- Test the interface contract: endpoints return correct envelope, scrapers return valid `Petition` objects
- Use fixtures for database setup — never rely on test ordering
- Mock external HTTP calls (scrapers) with `pytest-httpx` or `respx`

```python
# tests/test_api/test_petitions.py
import pytest
from httpx import AsyncClient

@pytest.mark.anyio
async def test_list_petitions_returns_envelope(client: AsyncClient) -> None:
    """GET /api/petitions returns the standard paginated envelope."""
    response = await client.get("/api/petitions")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "meta" in data
    assert "total" in data["meta"]
    assert "page" in data["meta"]
```

### Frontend Tests

- **vitest** for unit tests (hooks, services, utilities)
- **Jest + React Native Testing Library** for component tests
- Every new component needs at least one render test and one interaction test

```tsx
// mobile/components/__tests__/PetitionCard.test.tsx
import { render, fireEvent } from '@testing-library/react-native';
import { PetitionCard } from '../PetitionCard';
import { mockPetition } from '../../test-utils/mocks';

describe('PetitionCard', () => {
  it('renders petition title', () => {
    const { getByText } = render(<PetitionCard petition={mockPetition} />);
    expect(getByText(mockPetition.title)).toBeTruthy();
  });

  it('opens source URL on sign button press', () => {
    const { getByText } = render(<PetitionCard petition={mockPetition} />);
    fireEvent.press(getByText(/Sign on/));
    // Verify Linking.openURL was called with source_url
  });
});
```

---

## PR Workflow

1. **Fork** the repository on GitHub
2. **Create a branch** from `main`:
   ```bash
   git checkout -b task/<id>-<slug>
   ```
3. **Make your changes.** Follow the code style above.
4. **Write tests.** Every new feature needs tests.
5. **Run the full suite** — all checks must pass:
   ```bash
   pytest tests/ -v
   cd mobile && npm test
   ```
6. **Commit** with a clear conventional commit message:
   ```bash
   git commit -m "feat: add openPetition scraper"
   ```
7. **Push and open a PR** against `main`. Include:
   - What changed and why
   - Screenshots for UI changes
   - Test results

### Branch Naming

- `task/<id>-<slug>` — kanban-driven development (preferred)
- `feature/<name>` — new features (e.g. `feature/push-notifications`)
- `fix/<description>` — bug fixes (e.g. `fix/deadline-timezone`)
- `docs/<description>` — documentation only

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Use For |
|--------|---------|
| `feat:` | New features (scraper, UI component, API endpoint) |
| `fix:` | Bug fixes |
| `docs:` | Documentation changes |
| `test:` | Test additions or fixes |
| `refactor:` | Code restructuring without behavior change |
| `chore:` | Dependency updates, config changes |

### Merge Policy

- **Squash merge** — one commit per PR into `main`
- **No direct commits to main** — always via PR
- **All checks must pass** before merge (CI, lint, tests)
- **At least one review** required for non-trivial changes

---

## Issue Templates

### Bug Report
- What happened vs. what you expected
- Steps to reproduce (include device, OS version, app version)
- Screenshots if visual
- Backend logs if relevant

### Feature Request
- What problem this solves
- Proposed approach (optional)
- Alternatives considered
- Does this align with the discovery-layer-only mission?

### New Petition Source
- Platform name and URL
- Is the petition listing publicly accessible (no auth)?
- What metadata is available (title, signatures, deadline, etc.)?
- Why this source matters for German petition discovery

---

## Legal Requirements

Every contribution must respect these legal constraints:

1. **No tracking** — no Google Analytics, no Meta Pixel, no third-party trackers. Period.
2. **No personal data storage** beyond push notification subscription (browser endpoint + key)
3. **Scraping only public pages** — no authentication bypass, no CAPTCHA circumvention
4. **Impressum** — every public-facing page must have contact info (§5 TMG)
5. **Datenschutzerklärung** — privacy policy covering scraping, push data, no tracking
6. **MIT License** — all code is open source under MIT

If your change touches data handling, push notifications, or external requests, flag it for legal review.

---

## Code of Conduct

Be respectful. Assume good intent. Give constructive feedback.

We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Report issues to the maintainers.

---

## Questions?

Open a GitHub Discussion or reach out in an issue. We're happy to help you get your first scraper or component working.
