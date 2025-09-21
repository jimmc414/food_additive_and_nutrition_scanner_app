# Architecture

## 1. Goals and constraints
- The system shall scan labels and barcodes offline and render plain risks per additive.
- The system shall operate on iOS and Android with identical outputs.
- The system must keep images on device by default.
- The system shall support EU and US regulatory views at launch.
- The base data pack must be ≤ 10 MB on install.

## 2. High‑level view
```
+-------------------------+           +------------------------------+
|       Mobile app        |  online   | Optional backend (cloud)     |
|  - OCR + Parser         +---------->+ - Pack API (read-only)       |
|  - Risk engine          |           | - ETL + signing              |
|  - Local DB (SQLite)    |           | - Admin console              |
|  - Pack manager         |           | - Telemetry intake (opt-in)  |
+-------------------------+           +------------------------------+
```

## 3. Client architecture

### 3.1 Layers
- Presentation: screens, a11y, state containers.
- Domain: OCR pipeline, parser, risk engine, barcode module, pack manager.
- Data: local SQLite store, LRU caches, settings store.
- Platform: camera, filesystem, secure keystore, network.

### 3.2 Capture and OCR
- Camera: AVFoundation (iOS) and CameraX (Android).
- OCR: iOS Vision Text Recognition and Android ML Kit Text Recognition.
- Pipeline:
  - Auto focus and exposure locks for text.
  - Multi‑shot burst for small fonts with best‑of confidence merge.
  - Preprocessing hints: crop to ingredient panel when detectable, de‑skew, binarize when needed.
  - OCR outputs: token text, bounding box, line order, confidence.
- Constraints:
  - All OCR shall be on device.
  - Per‑token confidence must be surfaced to the parser.

### 3.3 Ingredient detection heuristic
- Region of interest ranking by:
  - Dense comma separation
  - Presence of keywords: ingredients, contains, may contain, en, fr, es variants
  - Longest line count with high OCR confidence
- Non‑ingredients (marketing blurbs) shall be deprioritized by low comma density and large font size outliers.

### 3.4 Parsing and normalization
- Normalization steps shall include:
  - Unicode NFKC
  - Uppercase
  - Whitespace collapse
  - Diacritic stripping for matching, original kept for display
- Tokenization:
  - Split on commas and parentheses
  - Retain window context for function words near tokens
- Matchers:
  - Pattern matcher for E or INS codes with optional zero padding and suffix letter
  - Dictionary matcher for synonyms and US names
  - Fuzzy match for common OCR slips (0↔O, 1↔I, S↔5) with bounded Levenshtein
- Canonicalization:
  - Map any alias to a single canonical code id
  - Preserve all matched aliases for user audit
- Confidence:
  - Combine OCR confidence and match confidence into a per‑additive confidence score.

### 3.5 Barcode module
- Symbologies: EAN‑13, EAN‑8, UPC‑A, UPC‑E.
- Priority:
  - Use OCR path first
  - Trigger barcode flow when OCR confidence below threshold or no additives found
- Network:
  - Query Open Food Facts or configured provider
  - Cache product id and ingredients text with TTI and TTL
- Privacy:
  - Barcode queries shall not include images or precise location.

### 3.6 Local data model
- Additives store:
  - code
  - names[]
  - class
  - dietary flags
  - source flags
  - population cautions
  - region rules {EU, US}
  - evidence level
  - plain risk summary
  - references[]
  - updated_at
- Auxiliary indices:
  - alias→code map
  - trigram index for fuzzy names
  - function word lexicon per language
- Product cache:
  - barcode
  - ingredients_text
  - additives_found[]
  - timestamp
  - region

### 3.7 Risk engine
- Inputs:
  - Canonical additive list with confidences
  - User prefs: diet, sensitivities, child mode, region
  - Region rules for active region
- Evaluation order:
  1) Regulatory warnings for region
  2) Population cautions gated by prefs
  3) Diet conflicts
  4) Evidence level heuristics
- Outputs:
  - Per‑additive badge: Red, Yellow, Green
  - Product summary: flagged count, neutral count
  - Justification tuple: rule id, reference ids
- Determinism:
  - Same inputs must yield identical outputs byte‑for‑byte.
- Explainability:
  - Each badge must include rule id and at least one primary reference.

### 3.8 Personalization
- Stored in secure keystore or encrypted shared prefs.
- Region resolution:
  - Explicit user setting overrides
  - Else device locale
  - GPS is optional and shall be opt‑in
- No inference of protected attributes.

### 3.9 Pack manager
- Components:
  - Version resolver
  - Downloader with resume
  - Verifier (checksum and signature)
  - Installer with rollback
- Update types:
  - Full pack
  - Delta pack from prior version
- Atomicity:
  - Write to temp location, verify, swap pointer, fsync
- Integrity:
  - SHA‑256 checksum verification
  - Ed25519 signature verification
- Failure handling:
  - Keep last known good pack
  - Backoff with jitter on network errors

### 3.10 Storage and caching
- SQLite WAL mode for durability.
- Page size tuned for read‑heavy workloads.
- LRU caches:
  - alias map
  - last N results
  - barcode responses
- Size limits:
  - Total on‑device data for packs and caches ≤ 50 MB by default.

### 3.11 Accessibility and UX hooks
- Dynamic type and screen reader roles on all interactive elements.
- Badges shall include text labels in addition to color.
- Layout shall support left‑to‑right and right‑to‑left.

### 3.12 Performance budgets
- Offline scan to result p95 ≤ 2.0 s on mid‑range devices.
- Peak RAM during OCR ≤ 150 MB.
- Pack install time p95 ≤ 3.0 s for 10 MB packs.

### 3.13 Error taxonomy and propagation
- capture_error, ocr_error, parse_error, lookup_error, network_error, update_error.
- Domain errors shall carry machine code, human title, retry hints.
- UI shall render actionable options: rescan, manual entry, barcode, retry.

## 4. Backend architecture (optional)

### 4.1 Services
- Pack API:
  - GET latest pack metadata by region
  - GET pack by version
- Telemetry intake:
  - Write‑only endpoint for anonymous events
- Admin console:
  - CRUD for additives, aliases, rules, references
  - Role‑based access

### 4.2 Data stores
- Postgres for additive master, aliases, rules, references, audit log.
- Object storage for pack payloads and diffs.
- Redis for ephemeral locks and idempotency keys.

### 4.3 ETL and signing
- Sources:
  - Regulatory lists, monographs, synonym catalogs
- ETL stages:
  - Ingest raw
  - Normalize entities
  - Validate constraints and referential integrity
  - Generate region views
  - Compute alias maps and trigram aids
  - Emit deterministic JSON with stable ordering
- Signing:
  - Compute SHA‑256 checksum
  - Sign with Ed25519 offline key
  - Publish public key in app
- Scheduler:
  - Nightly build pipeline with manual promote to production.

### 4.4 Security
- TLS 1.2+ everywhere.
- OAuth2 service accounts for admin and CI.
- Principle of least privilege IAM.
- WAF rules for APIs.
- Audit logs for all admin writes.

### 4.5 Observability
- Metrics:
  - Pack fetch success rate, latency, size
  - Telemetry ingress rate
- Logs:
  - Access logs with privacy redaction
- Alerts:
  - Pack signing failures
  - API 5xx rate spikes

## 5. Data specifications

### 5.1 Identifiers
- code: canonical id for additive
- alias ids: stable strings for synonyms
- rule ids: stable strings with region prefix
- reference ids: stable strings mapped to citations

### 5.2 Pack structure
- Metadata:
  - version, created_at, regions[], checksum, signature, diff_from
- Payload:
  - additives[]
  - aliases map
  - rules per region
  - references catalog
  - function lexicons per language
- JSON ordering shall be deterministic to ensure stable hashes.

### 5.3 References catalog
- Each reference shall include:
  - label, publisher, year, url, ref_type
- Client shall render label and publisher only. URL opens externally.

## 6. Rules engine details

### 6.1 Fact model
- facts.additives[code] with match evidence and confidence
- facts.user.prefs
- facts.region
- facts.product_context: if child mode is on, if vegan is on

### 6.2 Rule types
- regulatory_warning
- region_approval
- population_caution
- diet_conflict
- evidence_annotation

### 6.3 Conflict resolution
- If any regulatory_warning applies then badge Red.
- Else if any active population_caution applies then badge Red.
- Else if any diet_conflict applies then badge Yellow.
- Else evidence_annotation may set Yellow, else Green.
- Ties shall resolve to the highest severity.

### 6.4 Determinism and auditing
- Input and output snapshots shall be loggable on device for user export.
- Each badge shall cite rule ids and reference ids.

## 7. Internationalization

- Locale packs shall drive:
  - UI strings
  - Function word lexicons
  - Preferred additive names by region
- Fallback chain:
  - Exact locale
  - Language only
  - English

## 8. Privacy

- Default setting:
  - No image upload
  - No ingredient text upload
- Telemetry:
  - Opt‑in
  - Event schema excludes PII and raw text
  - Batched upload with exponential backoff
- Data retention:
  - Device caches time‑boxed with TTL
  - Server telemetry retention 90 days max

## 9. Security

- App binary integrity:
  - Platform‑native code signing
- Network:
  - Certificate pinning optional and configurable per build
- Secrets:
  - Public keys embedded read‑only
  - No private keys in the app
- Updates:
  - Pack signature must verify before install
  - Rollback on verify failure

## 10. Build and release

- CI pipeline shall run:
  - Unit tests, lint, static analysis
  - Dependency vulnerability scan
  - Reproducible pack build and signing
- Artifacts:
  - iOS IPA and Android AAB
  - Pack files and checksums
- Release gates:
  - a11y checks pass
  - performance budgets met
  - security checks no high severity

## 11. Testing

- Gold set of 500 label images with ground truth.
- Measures:
  - E‑code detection F1
  - Synonym recall
  - Time to result
  - Badge accuracy against curated rule fixtures
- Device matrix:
  - iOS 15 to current
  - Android 9 to current
  - Low light, glare, curved surfaces
- Security tests:
  - Tampered pack install must fail
  - Downgrade attempts must fail unless integrity failure

## 12. Resilience and failure modes

- Offline first:
  - Full scan flow must work offline
- Network errors:
  - Barcode fallback shall degrade with clear retry
- Update errors:
  - Keep last good pack
  - User prompt to retry later
- Data corruption:
  - Verify SQLite integrity on crash recovery
  - Rebuild indices if needed

## 13. Operational limits

- Maximum additives per pack at launch: 1000 to 1500.
- Maximum aliases per additive: 50.
- Maximum references per additive: 10.
- OCR line length cap for parser: 512 characters per line.

## 14. ADR summary

- Cross‑platform UI: React Native or Flutter. Decision driver: single codebase and near‑native camera access.
- OCR: on‑device OS frameworks. Decision driver: privacy and latency.
- Local DB: SQLite. Decision driver: mature, small, fast reads.
- Signing: Ed25519. Decision driver: small keys, fast verify on device.
- Backend: FastAPI + Postgres. Decision driver: simple read APIs, strong typing, low overhead.
- Pack format: deterministic JSON. Decision driver: diffable, inspectable.

## 15. Open items

- Future regions: CA, AU, NZ
- Additional sensitivities: benzoates, salicylates
- Optional model to auto‑detect the ingredients panel bounding box

This document defines the technical structure and choices for implementation without code.
