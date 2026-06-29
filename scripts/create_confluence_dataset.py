"""
Creates QuantumShield Entertainment architecture wiki pages in Confluence.
"""
import os
import time
import requests
from requests.auth import HTTPBasicAuth

WIKI_URL = "https://rajeshp010233-1781968412072.atlassian.net"
EMAIL    = "rajeshp010233@gmail.com"
TOKEN    = os.environ["ATLASSIAN_TOKEN"]
SPACE    = "QE"
PARENT   = "262331"   # "QuantumShield Entertainment" homepage

auth   = HTTPBasicAuth(EMAIL, TOKEN)
hdrs   = {"Accept": "application/json", "Content-Type": "application/json"}


def create_page(title: str, body: str, parent_id: str = PARENT) -> str:
    resp = requests.post(
        f"{WIKI_URL}/wiki/rest/api/content",
        auth=auth, headers=hdrs,
        json={
            "type": "page",
            "title": title,
            "space": {"key": SPACE},
            "ancestors": [{"id": parent_id}],
            "body": {"storage": {"value": body, "representation": "storage"}},
        },
    )
    if resp.status_code not in (200, 201):
        print(f"  ERROR '{title}': {resp.text[:300]}")
        return ""
    pid = resp.json()["id"]
    print(f"  Created [{pid}] {title}")
    time.sleep(0.5)
    return pid


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Platform Architecture Overview
# ══════════════════════════════════════════════════════════════════════════════

arch_overview = """
<h1>QuantumShield Entertainment — Platform Architecture Overview</h1>
<p><strong>Last Updated:</strong> 2026-06-20 &nbsp;|&nbsp; <strong>Owner:</strong> Platform Engineering</p>

<h2>1. Streaming &amp; Delivery Architecture</h2>
<h3>1.1 CDN Strategy</h3>
<ul>
  <li>Primary CDN: <strong>Akamai</strong> (global). Failover CDN: <strong>Fastly</strong>.</li>
  <li>DNS-based routing currently in use for CDN switching (5–10 min propagation).</li>
  <li>Target: Migrate to Anycast routing with real-time health checks per region.</li>
  <li>Content packaged in HLS (Apple) and DASH (Android, Web, Smart TV).</li>
  <li><strong>Target:</strong> Migrate to CMAF (Common Media Application Format) — single fragmented MP4 for all clients, ~45% storage reduction (12 PB → ~6.5 PB).</li>
  <li>Live stream latency target: <strong>&lt;5 seconds</strong> via CMAF chunked transfer (current: 30–45 s with HLS).</li>
</ul>
<h3>1.2 Transcoding Pipeline</h3>
<ul>
  <li>VOD: AWS Elemental MediaConvert. Live: AWS Elemental MediaLive.</li>
  <li>Output profiles: 240p, 480p, 720p, 1080p, 2160p (4K HDR10 and Dolby Vision).</li>
  <li>All content: AES-128 encryption as baseline. Premium 4K HDR: hardware-backed DRM required.</li>
</ul>
<h3>1.3 Storage</h3>
<ul>
  <li>Origin: AWS S3 (us-east-1 primary, eu-west-1 secondary).</li>
  <li>Total stored content: ~12 petabytes.</li>
  <li>Metadata DB: PostgreSQL 15 (Amazon RDS, Multi-AZ).</li>
</ul>

<h2>2. Key Architecture Decisions (Pending)</h2>
<table>
  <tbody>
    <tr><th>Decision</th><th>Options</th><th>Status</th></tr>
    <tr><td>Forensic watermarking with L1 DRM</td><td>Per-subscriber origin (no CDN cache for premium) vs AB-watermarking (2x storage, CDN cache preserved)</td><td>⏳ In Review</td></tr>
    <tr><td>SSAI vendor</td><td>AWS Elemental MediaTailor vs Yospace</td><td>⏳ POC in Sprint 2</td></tr>
    <tr><td>Streaming feature pipeline</td><td>Apache Flink on MSK vs Spark Streaming</td><td>⏳ Evaluating</td></tr>
  </tbody>
</table>
"""

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — DRM & Content Security
# ══════════════════════════════════════════════════════════════════════════════

drm_page = """
<h1>DRM &amp; Content Security Architecture</h1>
<p><strong>Owner:</strong> Tariq Nasser (Security Architect) &nbsp;|&nbsp; <strong>Last Updated:</strong> 2026-06-20</p>
<ac:structured-macro ac:name="info">
  <ac:rich-text-body><p>Changes to DRM or watermarking architecture require Security Architect sign-off before implementation.</p></ac:rich-text-body>
</ac:structured-macro>

<h2>Current DRM Setup</h2>
<table>
  <tbody>
    <tr><th>Platform</th><th>DRM</th><th>Max Resolution</th></tr>
    <tr><td>Android, Web</td><td>Widevine L3 (software)</td><td>1080p</td></tr>
    <tr><td>iOS, macOS</td><td>FairPlay Streaming</td><td>1080p</td></tr>
    <tr><td>Windows, Xbox</td><td>PlayReady</td><td>1080p</td></tr>
  </tbody>
</table>

<h2>L1 DRM Target State</h2>
<ul>
  <li>Widevine L1 requires hardware TEE. Device attestation via <strong>Google Play Integrity API</strong> (Android) and <strong>Apple DeviceCheck</strong> (iOS).</li>
  <li>Key server must support <strong>Google License Proxy Auth (LPA)</strong> protocol.</li>
  <li>FairPlay L1 requires <strong>Apple KSM certification</strong> (4–6 week Apple review).</li>
  <li>L1 unlocks: 4K HDR10, Dolby Vision, Dolby Atmos.</li>
</ul>

<h2>Key Server Constraints</h2>
<ul>
  <li>Must run <strong>active-active across ≥ 2 AWS regions</strong> before L1 launch (key server downtime = no playback).</li>
  <li>All license requests must be <strong>audit-logged</strong> (ISO 27001 requirement).</li>
  <li>License anomaly detection required for credential sharing / piracy detection.</li>
  <li>Token lifetimes: Premium tier <strong>max 72 hours</strong>, Standard tier <strong>max 24 hours</strong>.</li>
</ul>

<h2>Forensic Watermarking</h2>
<p>Provider: <strong>Nagra NexGuard</strong>. Current: post-CDN origin injection. With L1 DRM, watermark must be embedded pre-delivery (device TEE decrypts, can't inject after).</p>
<table>
  <tbody>
    <tr><th>Approach</th><th>CDN Cache</th><th>Storage Impact</th><th>Status</th></tr>
    <tr><td>Per-subscriber origin watermarking</td><td>Cache miss for premium content</td><td>No extra storage</td><td>Option A</td></tr>
    <tr><td>AB-watermarking</td><td>CDN cache preserved</td><td>~2x premium content storage</td><td>Option B (preferred)</td></tr>
  </tbody>
</table>
<p><strong>Decision required before DRM uplift sprint 3.</strong></p>
"""

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — Data Platform & ML
# ══════════════════════════════════════════════════════════════════════════════

data_page = """
<h1>Data Platform &amp; ML Architecture</h1>
<p><strong>Owner:</strong> Femi Adeyemi (Staff Engineer – Data) &nbsp;|&nbsp; <strong>Last Updated:</strong> 2026-06-20</p>

<h2>Event Streaming Pipeline</h2>
<table>
  <tbody>
    <tr><th>Component</th><th>Current</th><th>Target</th></tr>
    <tr><td>Ingestion</td><td>Kinesis → Kafka (MSK)</td><td>Same</td></tr>
    <tr><td>Processing</td><td>Spark batch on EMR (4-hour cadence)</td><td>Apache Flink on MSK (&lt;5 min latency)</td></tr>
    <tr><td>Feature Store</td><td>Feast (offline) + Redis (online)</td><td>Same, with streaming writes</td></tr>
  </tbody>
</table>

<h2>Recommendation Engine</h2>
<ul>
  <li><strong>Current:</strong> AWS Personalize (collaborative filtering only).</li>
  <li><strong>Target:</strong> Hybrid — content-based features (metadata, mood, themes) + collaborative signals.</li>
  <li>Cold-start strategy: use content metadata features until ≥ 50 user interactions available for a title.</li>
  <li>Content metadata enrichment: <strong>AI pipeline (Claude API)</strong> — synopsis + reviews → genre, mood, theme tags.</li>
  <li><strong>Constraint:</strong> ≥ 85% precision against human-curated ground truth before tags used in production recommendations.</li>
</ul>

<h2>Data Governance Constraints</h2>
<ac:structured-macro ac:name="warning">
  <ac:rich-text-body>
    <ul>
      <li>User viewing data is classified as <strong>PII</strong> under company data policy.</li>
      <li><strong>MUST NOT</strong> be passed to third-party ad networks without explicit user consent (GDPR, CCPA).</li>
      <li>Permitted ad signals: content genre, content type, time of day, geography (country-level IP only).</li>
      <li>Data retention: viewing history retained 24 months, then anonymised.</li>
    </ul>
  </ac:rich-text-body>
</ac:structured-macro>
"""

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — Auth & Platform Security
# ══════════════════════════════════════════════════════════════════════════════

auth_page = """
<h1>Authentication, Identity &amp; Platform Security</h1>
<p><strong>Owner:</strong> Sam Osei (Principal Engineer) &amp; Tariq Nasser (Security Architect)</p>

<h2>Authentication Stack</h2>
<ul>
  <li>OAuth 2.0 / OIDC with internal IdP: <strong>Keycloak v22</strong>.</li>
  <li>Consumer access tokens: 24-hour lifetime (target: reduced to &lt;1 hour for service-to-service).</li>
  <li>Refresh tokens: 30 days.</li>
  <li>MFA: Optional for consumers, <strong>REQUIRED</strong> for internal admin users.</li>
</ul>

<h2>Service-to-Service Auth — CRITICAL CONSTRAINT</h2>
<ac:structured-macro ac:name="warning">
  <ac:rich-text-body>
    <p><strong>Security Policy SEC-04:</strong> Long-lived shared tokens are PROHIBITED for service accounts. Services found sharing tokens via Slack or any manual channel must be treated as a security incident.</p>
    <p><strong>Required architecture:</strong> HashiCorp Vault for machine identity. Token lifetime: <strong>15 minutes maximum</strong>. Automated rotation — no human intervention.</p>
  </ac:rich-text-body>
</ac:structured-macro>

<h2>Profile System</h2>
<table>
  <tbody>
    <tr><th>Profile Type</th><th>Content Access</th><th>PIN Required to Switch Away</th><th>Screen Time Limits</th></tr>
    <tr><td>Admin</td><td>All content</td><td>Yes (when switching to/from)</td><td>No</td></tr>
    <tr><td>Standard</td><td>All content</td><td>Optional</td><td>No</td></tr>
    <tr><td>Kids</td><td>Kids-rated only</td><td><strong>Yes — REQUIRED (not yet implemented)</strong></td><td>Configurable (not yet implemented)</td></tr>
  </tbody>
</table>

<h2>API Gateway — Platform Stability</h2>
<ul>
  <li>Rate limiting: <strong>Not yet implemented</strong>. Required before Q3 partner expansion (5 new partners).</li>
  <li>Circuit breakers: Required. One partner caused 45-min degradation event in May 2026.</li>
  <li>Observability: OpenTelemetry instrumentation across all microservices, Grafana Tempo for single-pane trace view.</li>
  <li>API versioning: External API versioned (/v1/, /v2/). Breaking changes require 90-day deprecation notice to partners.</li>
</ul>
"""

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — Product Backlog Priorities
# ══════════════════════════════════════════════════════════════════════════════

backlog_page = """
<h1>Product Backlog — Current Priorities</h1>
<p><strong>Last Updated:</strong> 2026-06-20 &nbsp;|&nbsp; <strong>Source:</strong> Strategy, User Research, and Engineering Review meetings — June 2026</p>

<h2>P0 — Immediate (Blocking Revenue or Security)</h2>
<table>
  <tbody>
    <tr><th>Item</th><th>Jira</th><th>Why P0</th></tr>
    <tr><td>DRM Uplift — Widevine L1 / FairPlay</td><td>QE-2</td><td>Blocks Warner and Paramount 4K licensing deals</td></tr>
    <tr><td>Service-to-service token rotation (SEC-04)</td><td>QE-18</td><td>Active security violation — shared tokens on Slack</td></tr>
    <tr><td>Subtitle / audio preference persistence</td><td>QE-20</td><td>Accessibility P0; subscriber cancelled over this</td></tr>
  </tbody>
</table>

<h2>P1 — High Priority (This Quarter)</h2>
<table>
  <tbody>
    <tr><th>Item</th><th>Jira</th><th>Owner</th></tr>
    <tr><td>Android download resume (30% corruption rate)</td><td>QE-11</td><td>Mobile Platform</td></tr>
    <tr><td>Continue Watching dismissal + ordering fix</td><td>QE-21</td><td>Consumer Product</td></tr>
    <tr><td>PIN-protected kids profile switching + screen time</td><td>QE-22</td><td>Consumer Product</td></tr>
    <tr><td>API rate limiting and circuit breakers</td><td>QE-17</td><td>Platform Engineering</td></tr>
    <tr><td>Privacy-safe ad signal aggregation layer</td><td>QE-15</td><td>Ad Tech</td></tr>
  </tbody>
</table>

<h2>P2 — Medium Priority (Next Quarter)</h2>
<table>
  <tbody>
    <tr><th>Item</th><th>Jira</th><th>Dependencies</th></tr>
    <tr><td>AI metadata enrichment pipeline</td><td>QE-12</td><td>None — can start now</td></tr>
    <tr><td>Hybrid recommendation engine</td><td>QE-3</td><td>QE-12 (metadata), QE-13 (Flink pipeline)</td></tr>
    <tr><td>Editorial curation tool</td><td>QE-14</td><td>QE-12 (metadata tags)</td></tr>
    <tr><td>SSAI pipeline launch</td><td>QE-4</td><td>QE-15 (ad signals), QE-16 (vendor selection)</td></tr>
    <tr><td>OpenTelemetry distributed tracing</td><td>QE-19</td><td>None</td></tr>
    <tr><td>Watchlist collections</td><td>QE-23</td><td>None</td></tr>
    <tr><td>ABR quality preference + data cap</td><td>QE-24</td><td>None</td></tr>
    <tr><td>Semantic / mood-based search</td><td>QE-25</td><td>QE-12 (metadata enrichment)</td></tr>
  </tbody>
</table>

<h2>Key Dependencies Map</h2>
<p>QE-12 (AI Metadata Enrichment) → QE-3 (Recommendations), QE-14 (Editorial Tool), QE-25 (Semantic Search)</p>
<p>QE-2 (DRM Uplift) → QE-11 (Download Manager), QE-10 (Device Capability UX)</p>
<p>QE-15 (Ad Signals) + QE-16 (SSAI Vendor) → QE-4 Epic (SSAI Launch)</p>
"""

# ══════════════════════════════════════════════════════════════════════════════
# CREATE ALL PAGES
# ══════════════════════════════════════════════════════════════════════════════

print("\n=== Creating Confluence Pages ===")
p_arch   = create_page("Platform Architecture Overview",          arch_overview)
p_drm    = create_page("DRM and Content Security Architecture",   drm_page)
p_data   = create_page("Data Platform and ML Architecture",       data_page)
p_auth   = create_page("Authentication, Identity and Security",   auth_page)
p_bl     = create_page("Product Backlog — Current Priorities",    backlog_page)

print("\n=== All Confluence pages created ===")
print(f"  Architecture Overview : {WIKI_URL}/wiki/spaces/QE/pages/{p_arch}")
print(f"  DRM & Security        : {WIKI_URL}/wiki/spaces/QE/pages/{p_drm}")
print(f"  Data Platform & ML    : {WIKI_URL}/wiki/spaces/QE/pages/{p_data}")
print(f"  Auth & Security       : {WIKI_URL}/wiki/spaces/QE/pages/{p_auth}")
print(f"  Backlog Priorities    : {WIKI_URL}/wiki/spaces/QE/pages/{p_bl}")
