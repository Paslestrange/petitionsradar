# PetitionsRadar — PO Decisions

## Target Market

**Germany-first.** All petition sources are German platforms:
1. **epetitionen.bundestag.de** — Bundestag e-petitions (official federal)
2. **openPetition.de** — largest German petition platform
3. **Change.org/de** — international but strong German presence
4. **weact.campact.de** — progressive advocacy campaigns
5. **petitionsportal.de** — state parliament (Landtag) petitions

## MVP Definition

### Must Have (v1)
- Petition discovery feed with swipeable cards
- Petition detail view (title, description, source, signature count, deadline, link to sign)
- Filter by topic (Klima, Soziales, Bildung, etc.) and platform
- Search by keyword
- Share button → generates Instagram Story image (1080×1920) with QR code
- Responsive PWA, installable on mobile
- Backend API serving petition metadata from database
- Scraper that collects petition metadata from public listing pages (no auth, no signature submission)
- Scheduled scraping (hourly) to keep metadata fresh

### Should Have (v1.1)
- Push notification subscription (web push)
- Milestone alerts (petition hits 10k, 50k, 100k)
- Deadline reminders (24h before closing)
- Geo-aware petition recommendations (by postcode)
- Follow/bookmark petitions

### Could Have (v2)
- User accounts (optional, for cross-device sync)
- Trending algorithm (velocity of signatures, not just total count)
- Petition of the day / curated homepage
- Multi-language (English for international solidarity sharing)
- Native app wrapper (Capacitor)

### Won't Have (explicitly)
- Signature collection or proxying
- User-generated petitions (we are discovery only, not a petition platform)
- Political opinion / endorsement — we surface all petitions neutrally
- Comment sections or forums (avoid moderation burden)

## Priorities

1. **Discovery UX first** — if the feed doesn't feel good on mobile, nothing else matters
2. **Data freshness** — petition counts and deadlines must be accurate (hourly scraping)
3. **Share generation** — the viral loop (discover → share to Stories → friend signs) is the core growth mechanism
4. **Neutrality** — no editorial bias in petition surfacing. All petitions from all sources treated equally
5. **Performance** — mobile-first means < 3s load on 4G, < 200ms API responses
6. **Legal cleanliness** — no scraping behind auth walls, no storing personal data, clear Impressum and Datenschutz

## Design Decisions

### Petition Data Model
```
Petition:
  id: UUID
  source: enum [bundestag, openpetition, change_org, weact, petitionsportal]
  source_url: string (official URL for signing)
  external_id: string (ID on source platform)
  title: string
  description: text
  topic: enum [klima, soziales, bildung, gesundheit, ...
]  # standardized topics
  signature_count: integer (latest scraped)
  signature_goal: integer (if known)
  status: enum [open, closed, successful, failed]
  created_date: date
  deadline: date (nullable)
  last_scraped: timestamp
  image_url: string (nullable, for card thumbnail)
```

### Tech Stack Decision
- **React + Vite PWA** over Next.js — lighter, faster, PWA-native. No SSR needed for an app-like experience.
- **FastAPI** over Django — async scraping + API in one process, lighter footprint
- **PostgreSQL** over SQLite — concurrent scraping + API reads, future-proof
- **Playwright** for scraping — handles JS-rendered platforms (openPetition, Change.org use client-side rendering)

### Legal Posture
- Impressum and Datenschutz required from day 1 (§5 TMG, §13 TMG, DSGVO)
- Scraping only public listing pages, no authentication bypass
- No personal data stored beyond optional push notification subscription (browser endpoint + push key)
- Clear "Sign on official site" labeling on every petition card — no impersonation of official platforms
- Open source (MIT) to build trust

## Open Questions (for PO)

- [ ] Should we show closed/failed petitions for historical context, or only open ones?
- [ ] How to handle petitions without a clear deadline (some openPetition campaigns are open-ended)?
- [ ] Should we integrate the Bundestag DIP API (dip.bundestag.de) for structured petition data if available?
- [ ] Do we need a manual review step before newly scraped petitions appear, or is full auto-accept acceptable?
