# PetitionsRadar — Project Goal

## Vision

A mobile-first web app that helps young Germans discover, share, and act on petitions across multiple platforms. The app is purely a **discovery and mobilization layer** — it never proxies signatures. Users tap through to the official petition page (Bundestag, openPetition, Change.org, etc.) to actually sign.

## Problem

Young people (18–35) engage politically but consume information via apps, not desktop websites. German petition platforms are:
- Desktop-first, legacy UX (especially epetitionen.bundestag.de)
- Fragmented across multiple sites with no unified discovery
- Not optimized for social sharing formats (Instagram Stories, TikTok, WhatsApp)
- Missing push notifications for milestones and deadlines

## Solution

PetitionsRadar aggregates petition **links and metadata** from multiple sources into a single mobile-first interface with:
1. **Swipeable discovery** — Tinder/Threads-style cards for browsing active petitions
2. **Smart filters** — by topic, region, platform, deadline urgency, signature progress
3. **Geo-aware alerts** — push notifications when a petition affects your postcode
4. **Shareable milestones** — generate Instagram Story / TikTok frames with petition title, progress bar, QR code
5. **Progress tracking** — follow petitions, get notified at 10k / 50k / 100k milestones
6. **Deadline reminders** — push before closing dates

## Success Criteria

- **MVP live** on a public URL with at least 50 aggregated petitions from 3+ sources
- **Mobile-first UX** — Lighthouse mobile score > 85 on all metrics
- **Petition cards** render with title, description, source platform, signature count, deadline, share button
- **Share generation** produces a downloadable image optimized for Instagram Story (1080×1920)
- **Search and filter** by topic and platform works with < 200ms response
- **Push notification** infrastructure for milestone alerts (web push API)
- **Zero signature proxying** — every "sign" button opens the official source URL

## Non-Goals

- We do NOT collect signatures or personal data beyond what's needed for push notifications
- We do NOT replace any petition platform — we are a discovery layer only
- We do NOT host petition content — we link to official sources

## Target Audience

- **Primary:** Germans aged 18–35 who are politically engaged but passive petition consumers
- **Secondary:** Activists and organizations who want to amplify their petitions to younger demographics

## Tech Direction

- **Mobile apps:** React Native + Expo (single TypeScript codebase → iOS + Android)
  - Expo EAS for OTA updates and store builds
  - Native push notifications (Expo Notifications API)
  - Share sheet via `expo-sharing` + `react-native-view-shot` for Instagram/TikTok image generation
  - WebView for opening official petition signing pages
- **Backend:** Python FastAPI (metadata aggregation, scheduled scraping of public pages, push notification management)
- **Data:** PostgreSQL for petition metadata, Redis for caching scraped content
- **Scraping:** Respectful, rate-limited metadata extraction from public petition listing pages — no authentication, no signature submission
- **Hosting:** Single VPS, systemd service, accessible via localhost + LAN + VPN (ZeroTier)
