# PetitionsRadar — Quality Bar

What "good" looks like for this project. The autonomous worker must meet these standards before merging any task.

## Code Quality

### Python (Backend)
- **Type hints** on all function signatures
- **Docstrings** on all public functions (Google style)
- **Pydantic models** for all API request/response schemas
- **Error handling** — all external calls (scraping, network) wrapped in try/except with logging
- **No bare except** — always catch specific exceptions
- **Async where possible** — scraping and API endpoints use async/await
- **Config via environment** — no hardcoded URLs, ports, DB credentials

### TypeScript/React (Frontend)
- **Functional components + hooks** only, no class components
- **Typed props** with TypeScript interfaces
- **No any** — use unknown + type narrowing if type is uncertain
- **Responsive by default** — all components work 360px → 1920px
- **Lighthouse mobile > 85** — performance, accessibility, best practices, SEO
- **PWA installable** — manifest.json, service worker, offline shell

### Tests
- **Backend:** pytest, ≥ 80% coverage on API routes and scraper modules
- **Frontend:** vitest for unit tests, Playwright for E2E smoke tests
- **Every PR includes tests** for new functionality
- **Tests must pass before merge** — no exceptions

### API Design
- **RESTful** — clear resource paths (/api/petitions, /api/petitions/{id}, /api/petitions/{id}/share)
- **JSON responses** with consistent envelope: `{ "data": [...], "meta": { "total": N, "page": P } }`
- **Proper HTTP status codes** — 200, 201, 400, 404, 500
- **Rate limiting** on scrape-triggering endpoints
- **Pagination** on all list endpoints (default 20, max 50)

## UX Quality

### Mobile-First
- **Touch targets ≥ 44px** — Apple HIG minimum
- **Thumb zone** — primary actions (swipe, sign button) in bottom third of screen
- **No horizontal scroll** on any viewport ≥ 360px
- **Fast perceived load** — skeleton screens, not spinners

### Petition Card
Must show:
- Title (truncated to 2 lines, tap to expand)
- Source platform badge (color-coded: Bundestag = black/gold, openPetition = green, etc.)
- Signature progress bar (current / goal)
- Deadline countdown (if applicable)
- "Sign on [Platform]" button → opens source_url in new tab
- Share icon → opens share sheet

### Share Image Generation
- **1080×1920px** — Instagram Story format
- Contains: petition title, progress bar, source platform, QR code linking to source_url
- **Readable in 3 seconds** — high contrast, large text
- **No PetitionsRadar watermark larger than 5%** of image — this is about the cause, not us

### Accessibility
- **WCAG 2.1 AA** — semantic HTML, ARIA where needed, keyboard navigable
- **Color contrast ≥ 4.5:1** for text
- **Screen reader tested** — at least one test with NVDA or VoiceOver

## Deployment Quality

- **systemd service** with auto-restart (Restart=always, RestartSec=5)
- **Health check endpoint** at /api/health returning 200 + JSON status
- **Structured logging** — JSON logs to stdout, captured by journald
- **Zero-downtime restart** not required for MVP, but restart must complete < 5s
- **Accessible on localhost + LAN + VPN** (ZeroTier IP)

## Legal

- **Impressum** page with contact info (§5 TMG)
- **Datenschutzerklärung** covering: what we scrape, what we store, push notification data, no personal data beyond push subscription
- **No tracking** — no Google Analytics, no Meta Pixel, no third-party trackers
- **Open source** — MIT license, public repo

## Git Discipline

- **One commit per task** (squash merge)
- **Conventional commit messages** — `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- **No direct commits to main** — always feature branch → PR → squash merge
- **Branch naming:** `task/{id}-{slug}` (e.g., `task/a1b2c3d4-petition-card-component`)
