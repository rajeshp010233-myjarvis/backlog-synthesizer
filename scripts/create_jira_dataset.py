"""
Creates the QuantumShield Entertainment golden dataset in Jira and Confluence.
Usage: python scripts/create_jira_dataset.py
"""
import os
import json
import time
import requests
from requests.auth import HTTPBasicAuth

JIRA_URL  = "https://rajeshp010233.atlassian.net"
WIKI_URL  = "https://rajeshp010233-1781968412072.atlassian.net"
EMAIL     = "rajeshp010233@gmail.com"
TOKEN     = os.environ["ATLASSIAN_TOKEN"]
PROJECT   = "QE"

auth    = HTTPBasicAuth(EMAIL, TOKEN)
j_hdrs  = {"Accept": "application/json", "Content-Type": "application/json"}
w_hdrs  = {"Accept": "application/json", "Content-Type": "application/json"}


# ── helpers ────────────────────────────────────────────────────────────────────

def adf(text: str) -> dict:
    """Wrap plain text as Atlassian Document Format body."""
    return {
        "type": "doc", "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]
    }


def create_issue(summary: str, issue_type: str, description: str,
                 priority: str = "Medium", labels: list[str] | None = None,
                 parent_key: str | None = None) -> str:
    fields: dict = {
        "project":   {"key": PROJECT},
        "issuetype": {"name": issue_type},
        "summary":   summary,
        "description": adf(description),
        "priority":  {"name": priority},
        "labels":    labels or [],
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}

    resp = requests.post(
        f"{JIRA_URL}/rest/api/3/issue",
        auth=auth, headers=j_hdrs,
        json={"fields": fields},
    )
    if resp.status_code not in (200, 201):
        print(f"  ERROR creating {summary[:50]}: {resp.text[:200]}")
        return ""
    key = resp.json()["key"]
    print(f"  Created {key}: {summary[:70]}")
    time.sleep(0.3)
    return key


def create_confluence_page(title: str, body_html: str, parent_id: str | None = None) -> str:
    payload: dict = {
        "type": "page",
        "title": title,
        "space": {"key": PROJECT},
        "body": {
            "storage": {"value": body_html, "representation": "storage"}
        },
    }
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]

    resp = requests.post(
        f"{WIKI_URL}/wiki/rest/api/content",
        auth=auth, headers=w_hdrs,
        json=payload,
    )
    if resp.status_code not in (200, 201):
        print(f"  ERROR creating page '{title}': {resp.text[:200]}")
        return ""
    pid = resp.json()["id"]
    print(f"  Created page {pid}: {title}")
    return pid


# ══════════════════════════════════════════════════════════════════════════════
# JIRA ISSUES
# ══════════════════════════════════════════════════════════════════════════════

print("\n=== Creating Epics ===")

e_drm = create_issue(
    summary="DRM Infrastructure Uplift — Widevine L1 and FairPlay",
    issue_type="Epic",
    description=(
        "Upgrade content protection from Widevine L3 to L1 hardware-backed DRM to unlock "
        "studio premium catalogue licensing. Covers backend key server, device attestation, "
        "mobile SDK certification, and HA key server deployment across two AWS regions. "
        "Blocking Warner and Paramount 4K HDR licensing deals."
    ),
    priority="Highest",
    labels=["drm", "security", "platform", "p0"],
)

e_recs = create_issue(
    summary="Hybrid Recommendation Engine and Long-Tail Content Discovery",
    issue_type="Epic",
    description=(
        "Replace pure collaborative filtering with a hybrid model combining content-based "
        "metadata features (genre, mood, theme tags) and collaborative signals. "
        "Addresses cold-start problem for long-tail catalogue. Bottom 40% of catalogue "
        "currently receives under 0.1% of total watch time. Subscribers who discover "
        "niche content have the lowest churn rate in the platform."
    ),
    priority="High",
    labels=["recommendations", "ml", "personalisation", "data-platform"],
)

e_ads = create_issue(
    summary="Ad-Supported Tier — Server-Side Ad Insertion (SSAI) Pipeline",
    issue_type="Epic",
    description=(
        "Build SSAI pipeline for Q3 ad-supported tier launch. Replace client-side IMA SDK "
        "pre-roll with seamless server-side mid-roll insertion. Evaluate AWS Elemental "
        "MediaTailor vs Yospace. Privacy constraint: contextual signals only (genre, "
        "geography, time of day) — no PII or user-level identifiers to ad networks per GDPR/CCPA."
    ),
    priority="High",
    labels=["ads", "ssai", "monetisation", "q3"],
)

e_platform = create_issue(
    summary="Platform Stability, Observability and Security Hardening",
    issue_type="Epic",
    description=(
        "Harden the platform for Q3 partner API expansion (5 new partners onboarding). "
        "Covers: API rate limiting and circuit breakers, distributed tracing via "
        "OpenTelemetry, service-to-service short-lived token rotation via HashiCorp Vault "
        "(SEC-04 compliance), and CMAF packaging migration (45% storage reduction)."
    ),
    priority="High",
    labels=["platform", "stability", "observability", "security"],
)

e_ux = create_issue(
    summary="User Experience — Player, Profiles and Content Discovery",
    issue_type="Epic",
    description=(
        "Address top user research findings from 18-subscriber sessions. Key pain points: "
        "subtitle preference loss on every title (11/18 users), no Continue Watching "
        "dismissal (6/18), kids profile PIN bypass, poor search for natural language "
        "queries, and watchlist organisation for power users."
    ),
    priority="High",
    labels=["ux", "player", "profiles", "accessibility"],
)

print("\n=== Creating Stories under DRM Epic ===")

create_issue(
    summary="Integrate Google Play Integrity API for Android device attestation",
    issue_type="Story",
    description=(
        "Implement Android device attestation using Google Play Integrity API to verify "
        "hardware TEE support before issuing Widevine L1 licenses. Device must pass "
        "MEETS_DEVICE_INTEGRITY verdict. Failed attestation must fall back to L3 with "
        "a user-facing message explaining 4K is unavailable on their device."
    ),
    priority="Highest",
    labels=["drm", "android", "attestation"],
    parent_key=e_drm,
)

create_issue(
    summary="Upgrade key server to support Google License Proxy Auth (LPA) protocol with HA",
    issue_type="Story",
    description=(
        "The existing DRMtoday-based key server must be updated to handle LPA protocol "
        "required for Widevine L1. Additionally, key server must be deployed in "
        "active-active configuration across two AWS regions (us-east-1 and eu-west-1) "
        "before L1 launch. Key server downtime means no content playback — HA is a "
        "launch prerequisite. All license requests must be audit-logged (ISO 27001)."
    ),
    priority="Highest",
    labels=["drm", "backend", "key-server", "high-availability"],
    parent_key=e_drm,
)

create_issue(
    summary="Apple FairPlay KSM certification and iOS L1 integration",
    issue_type="Task",
    description=(
        "Submit Apple Key Server Module integration for FairPlay L1 certification. "
        "Apple review takes 4-6 weeks — submit by end of sprint 1 to avoid blocking "
        "4K launch. Includes updating the iOS SDK to use AVContentKeySession for "
        "hardware-backed decryption and implementing Apple DeviceCheck for device attestation."
    ),
    priority="Highest",
    labels=["drm", "ios", "fairplay", "certification"],
    parent_key=e_drm,
)

create_issue(
    summary="Display device DRM capability and 4K support in account settings",
    issue_type="Story",
    description=(
        "Users encounter a generic error when their device lacks hardware DRM for 4K. "
        "Show each registered device's capability tier (4K HDR, 1080p, SD) in "
        "Account > Registered Devices. On playback failure due to DRM mismatch, "
        "show a specific error explaining why and which registered devices do support 4K."
    ),
    priority="Medium",
    labels=["drm", "ux", "devices", "error-messaging"],
    parent_key=e_drm,
)

create_issue(
    summary="Rewrite Android download chunk manager to support range requests for DRM segments",
    issue_type="Bug",
    description=(
        "Offline download on Android fails to resume after network interruption, "
        "corrupting approximately 30% of partial downloads. Root cause: download chunk "
        "manager re-fetches from segment start instead of using HTTP range requests on "
        "DRM-encrypted HLS segments. Fix must handle offline license re-provisioning "
        "after resume if the license expired during the interruption."
    ),
    priority="High",
    labels=["downloads", "android", "bug", "drm", "offline"],
    parent_key=e_drm,
)

print("\n=== Creating Stories under Recommendations Epic ===")

create_issue(
    summary="AI metadata enrichment pipeline — genre, mood and theme tagging",
    issue_type="Story",
    description=(
        "Build batch enrichment pipeline using Claude API to generate standardised genre, "
        "mood, and thematic keyword tags from title synopsis, cast/crew data, and reviews. "
        "Initial run: 60,000 titles (~120M tokens via Batch API). Ongoing: 100-200 new "
        "titles/month in the content ingestion pipeline. Minimum 85% precision against "
        "human-curated ground truth before tags are used in recommendations."
    ),
    priority="High",
    labels=["metadata", "ai", "recommendations", "content"],
    parent_key=e_recs,
)

create_issue(
    summary="Migrate event feature pipeline from 4-hour Spark batch to Flink streaming (<5 min latency)",
    issue_type="Story",
    description=(
        "Current 4-hour batch Spark pipeline on EMR makes personalisation signals stale. "
        "Migrate user event processing (play, pause, seek, search, watchlist add) to "
        "Apache Flink on MSK for streaming feature computation with under 5 minute latency. "
        "Run dual-write alongside batch pipeline during validation. "
        "Estimated 30-40% infrastructure cost increase — business case required."
    ),
    priority="Medium",
    labels=["data-platform", "flink", "streaming", "recommendations"],
    parent_key=e_recs,
)

create_issue(
    summary="Editorial curation tool for content programming team",
    issue_type="Feature",
    description=(
        "Content curators currently have no channel into the product — they send requests "
        "via Slack with no tracking or visibility. Build an internal tool allowing curators "
        "to create named collections (e.g. 'Hidden Gems', 'Award Season Picks'), schedule "
        "them on home screen rows with start/end dates, and view performance analytics "
        "(impressions, CTR, play rate, avg watch time per collection)."
    ),
    priority="Medium",
    labels=["cms", "editorial", "recommendations", "home-screen"],
    parent_key=e_recs,
)

print("\n=== Creating Stories under SSAI Epic ===")

create_issue(
    summary="Privacy-safe contextual ad signal aggregation layer",
    issue_type="Story",
    description=(
        "Build a signal aggregation service that strips PII before passing signals to "
        "ad decisioning. Permitted signals: content genre, content rating, episode type, "
        "time of day, geography (country-level from IP only). "
        "Prohibited: user ID, viewing history, profile data, device ID. "
        "GDPR/CCPA compliance — verified by legal sign-off before Q3 launch."
    ),
    priority="High",
    labels=["ads", "privacy", "gdpr", "ccpa", "ssai"],
    parent_key=e_ads,
)

create_issue(
    summary="SSAI vendor evaluation and integration — MediaTailor vs Yospace",
    issue_type="Task",
    description=(
        "Evaluate AWS Elemental MediaTailor and Yospace for SSAI. Assessment criteria: "
        "HLS and DASH compatibility, latency impact on stream start, ad marker (SCTE-35) "
        "handling, VAST/VMAP support, cost per impression, and failover behaviour when "
        "ad fill rate is 0%. Produce recommendation with POC by end of sprint 2."
    ),
    priority="High",
    labels=["ads", "ssai", "vendor-evaluation"],
    parent_key=e_ads,
)

print("\n=== Creating Stories under Platform Stability Epic ===")

create_issue(
    summary="API gateway rate limiting and circuit breakers for partner API",
    issue_type="Story",
    description=(
        "Implement per-consumer-key rate limiting with graduated throttling on the partner "
        "API gateway. Add circuit breakers to prevent cascading timeouts from misbehaving "
        "integrations. Context: one existing partner caused a 45-minute degradation event "
        "with malformed batch requests. 5 new partners onboarding in Q3. "
        "SLA target: 99.9% streaming API uptime."
    ),
    priority="High",
    labels=["api", "stability", "rate-limiting", "circuit-breaker"],
    parent_key=e_platform,
)

create_issue(
    summary="Service-to-service token rotation via HashiCorp Vault (SEC-04 compliance)",
    issue_type="Story",
    description=(
        "CRITICAL SECURITY: Services are sharing 24-hour tokens via Slack messages in "
        "violation of security policy SEC-04. Migrate all service accounts to short-lived "
        "machine tokens (15-minute lifetime) automatically rotated by HashiCorp Vault. "
        "Existing shared tokens must be revoked. Auth gateway must reject long-lived tokens "
        "and alert the security team. Treat as immediate security fix, not Q3 roadmap."
    ),
    priority="Highest",
    labels=["security", "auth", "vault", "sec-04", "p0"],
    parent_key=e_platform,
)

create_issue(
    summary="OpenTelemetry distributed tracing across all microservices",
    issue_type="Story",
    description=(
        "Instrument all services with OpenTelemetry SDK. Consolidate 5 separate Kibana "
        "dashboards into a single trace view in Grafana Tempo. When a user reports "
        "playback failure, ops must be able to reconstruct the full request path across "
        "auth service, license server, CDN, and player in a single view. "
        "Required for incident response SLA compliance."
    ),
    priority="Medium",
    labels=["observability", "tracing", "opentelemetry", "platform"],
    parent_key=e_platform,
)

print("\n=== Creating Stories under UX Epic ===")

create_issue(
    summary="Subtitle and audio language preference persistence at profile level",
    issue_type="Story",
    description=(
        "ACCESSIBILITY P0: 11 of 18 research users affected. Subtitle language, audio "
        "language, and subtitle styling (background, font size, colour) currently reset "
        "to defaults on every new title. Save preferences to the user profile. "
        "A D/HH user cancelled their subscription over this issue. "
        "One-off mid-episode overrides should not update the global preference unless "
        "the user explicitly saves the change."
    ),
    priority="Highest",
    labels=["accessibility", "subtitles", "profile", "player", "p0"],
    parent_key=e_ux,
)

create_issue(
    summary="Remove from Continue Watching and Not For Me dismissal action",
    issue_type="Story",
    description=(
        "6 of 18 research users frustrated they cannot remove titles from Continue Watching. "
        "Add a context menu with three actions: Resume, Remove from Continue Watching, "
        "and Not For Me. Remove deletes the watch position. Not For Me removes from "
        "Continue Watching AND sends a negative recommendation signal. "
        "Fix Continue Watching ordering to strict recency (algorithm weighting experiment "
        "was never rolled back — revert to timestamp ordering)."
    ),
    priority="High",
    labels=["ux", "continue-watching", "home-screen", "recommendations"],
    parent_key=e_ux,
)

create_issue(
    summary="PIN-protected profile switching and kids screen time limits",
    issue_type="Story",
    description=(
        "Kids profiles can currently be exited without a PIN — children can switch to "
        "adult profiles and access unrestricted content. Require PIN on switching from "
        "a kids profile to a protected adult profile. Add visible Kids indicator in "
        "header when in a restricted profile. Add configurable screen time limits "
        "(daily cap) on kids profiles with parent PIN override."
    ),
    priority="High",
    labels=["profiles", "parental-controls", "kids", "security"],
    parent_key=e_ux,
)

create_issue(
    summary="Watchlist collection management — folders, sort and search",
    issue_type="Story",
    description=(
        "Users with 50+ watchlist titles describe it as unusable — no folders, no sort by "
        "genre or year, no search within watchlist. Multiple users are hacking the profile "
        "system (creating profiles named by genre) to work around this. "
        "Build collection management: named folders, sort by genre/year/date added, "
        "search within watchlist, title-to-collection picker on add."
    ),
    priority="Medium",
    labels=["ux", "watchlist", "collections", "browse"],
    parent_key=e_ux,
)

create_issue(
    summary="ABR quality preference setting and mobile data cap with tier selection",
    issue_type="Story",
    description=(
        "7 of 18 users frustrated by aggressive quality drops during temporary bandwidth "
        "dips and slow 20-30 second recovery. Add a player quality preference toggle: "
        "Prefer Quality (allow brief buffer stall) vs Prefer Smooth (allow lower quality). "
        "Separately, replace the binary data-saver toggle with a mobile data quality cap "
        "picker: 240p / 480p / 720p / Unlimited. ABR operates within the cap."
    ),
    priority="Medium",
    labels=["player", "abr", "ux", "mobile", "quality"],
    parent_key=e_ux,
)

create_issue(
    summary="Semantic and mood-based search enrichment",
    issue_type="Story",
    description=(
        "Current search is keyword exact-match against title, cast, and director only. "
        "Users searching 'space exploration documentary' or 'sad movies for rainy days' "
        "get zero results. Enrich search index with AI-generated description summaries, "
        "mood tags, and thematic keywords from the metadata enrichment pipeline. "
        "Stretch goal: semantic vector search for natural language queries."
    ),
    priority="Medium",
    labels=["search", "ux", "semantic", "metadata", "ai"],
    parent_key=e_ux,
)

print("\n=== All Jira issues created successfully ===")
