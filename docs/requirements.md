# Nutrition Scanner — Requirements

## 1. Purpose
- The system shall scan food labels and barcodes to identify food additives and present plain‑language risks for shoppers.
- The system shall operate offline for core features.
- The system shall respect regional regulatory differences.

## 2. Scope
- Mobile apps for iOS and Android are in scope.
- On‑device OCR, parsing, and local additive lookup are in scope.
- Optional backend services for data updates, telemetry, and rule delivery are in scope.
- Editing public datasets and providing medical advice are out of scope.

## 3. Definitions
- **Additive**: An ingredient with an E‑code or equivalent identifier.
- **E‑code**: European additive identifier `E###` with optional suffix letter.
- **Plain risk**: One‑line, non‑technical explanation and audience caution.
- **Region rule**: Jurisdiction‑specific approval, labeling, or warning requirement.

## 4. Users and Roles
- **Shopper**: Default user. Reads results and sets dietary preferences.
- **Admin**: Maintains additive data and rules. Uses backend tools.

## 5. Top‑Level Requirements
- The app must extract additives from a label photo or barcode.
- The app shall map additives and synonyms to canonical records.
- The app shall display a product summary and per‑additive explanations.
- The app shall personalize flags based on user preferences.
- The app must work with no network for scan → explanation.
- The app must not upload photos by default.

## 6. Functional Requirements

### 6.1 Capture and OCR
- The app shall capture images via the device camera and gallery.
- The OCR engine shall operate on device.
- The OCR pipeline shall include de‑skew, de‑glare hints, and perspective correction.
- The OCR output shall include per‑token confidence scores.
- The app shall request camera permission only when first needed.

### 6.2 Parsing and Normalization
- The parser shall normalize text to uppercase, collapse whitespace, and strip diacritics.
- The parser shall split ingredients on commas and parentheses.
- The parser must recognize E‑codes and aliases via patterns and dictionaries.
- The parser must handle these patterns:
  - `\bE\s*0*\d{3}[A-Z]?\b`
  - `\bINS\s*0*\d{3}[A-Z]?\b`
  - Known names (e.g., “TARTRAZINE”, “CARMINE”, “FD&C YELLOW 5”).
- The parser shall canonicalize spaces and zeros (e.g., `E 1 2 0` → `E120`).
- The parser shall extract additive function hints from nearby tokens (e.g., “COLOUR”, “PRESERVATIVE”).

### 6.3 Lookup
- The app shall maintain an on‑device additive store (SQLite or equivalent).
- Each additive record shall include:
  - `code` (e.g., `E120`)
  - `names[]` (synonyms and regulatory names)
  - `class` (e.g., Colour, Preservative)
  - `dietary` flags (vegan, vegetarian, kosher, halal)
  - `source` flags (animal‑derived, insect‑derived, synthetic)
  - `population` cautions (e.g., PKU, sulfite sensitivity)
  - `region_rules{}` (per region approvals and warnings)
  - `evidence_level` (Regulatory | Consensus | Limited)
  - `plain_risk.summary`
  - `references[]` (short source labels and URLs)
- The lookup shall return the best match and all aliases matched.
- When an ingredient name is found without an E‑code, the lookup shall map via `names[]` to the canonical code when present.

### 6.4 Barcode Fallback
- The app shall support barcode scan (EAN‑13, UPC‑A/E).
- When OCR confidence is below a threshold or no ingredients are detected, the app shall query a product database by barcode if online.
- The app shall cache barcode results on device.

### 6.5 Personalization
- The app shall allow the user to set:
  - Diet: vegan, vegetarian, kosher, halal.
  - Allergens/sensitivities: shellfish, sulfites, aspartame (PKU), caffeine.
  - Child mode toggle.
  - Region preference or auto region.
- The risk engine shall apply personalization before rendering results.
- The app must not infer protected characteristics.

### 6.6 Region Handling
- The app shall support at minimum EU and US regions at launch.
- The region resolver shall use explicit user selection or device locale. GPS is optional.
- Region rules must drive warnings and approvals. Conflicts shall default to the user’s selected region.

### 6.7 Explanations and Badging
- The app shall compute a product‑level summary:
  - Count flagged additives
  - Count neutral additives
- The app shall assign per‑additive badges:
  - Red: regulatory warning or strong population caution
  - Yellow: limited or controversial evidence or personal diet conflict
  - Green: approved with no special risk at typical intakes
- Each additive card shall include:
  - Name and code
  - Badge
  - One‑line plain risk
  - Audience tag (e.g., “Kids”, “PKU”)
  - Diet icons
  - “Why” link to references
- The app must not use medical language or dosage advice.

### 6.8 Offline Behavior
- The additive store and rules must be available offline.
- Barcode lookups shall degrade gracefully offline and prompt for rescans or manual entry.
- The app shall queue data updates for later.

### 6.9 Manual Entry
- The app shall allow manual entry of ingredient lines and individual E‑codes.
- Manual entries shall use the same parser and risk engine.

### 6.10 Settings and Data Update
- The app shall update additive data and rules via signed deltas.
- Updates must be atomic and rollback capable.
- The user shall be able to view the data version and region pack version.

## 7. Non‑Functional Requirements

### 7.1 Performance
- Time from capture to initial results must be ≤ 2.0 s on mid‑range devices when offline.
- Barcode online fallback must return in ≤ 3.5 s on a 4G connection.
- App cold start shall be ≤ 1.5 s on mid‑range devices.

### 7.2 Reliability
- The app shall tolerate partial OCR and still render any matched additives.
- The app shall store results locally to allow back navigation without re‑scan.
- Data updates must not corrupt the local store.

### 7.3 Security and Privacy
- Images and text must not leave the device without explicit opt‑in.
- All network traffic must use TLS 1.2+.
- Cached barcodes and results shall exclude PII.
- Keys and tokens shall be stored in the secure keystore/keychain.
- Crash and telemetry data must not include raw images or ingredient text.
- The app must provide a clear privacy notice and an opt‑out for analytics.

### 7.4 Accessibility and UX
- The app shall meet WCAG 2.1 AA for color contrast and text scaling.
- Core actions shall be usable with screen readers.
- Copy shall target Grade 6 reading level.
- The app must not rely on color alone to convey risk.

### 7.5 Localization
- The app shall support English at launch.
- The architecture shall support additional locales.
- Additive names shall prefer region‑specific names for the active region.

## 8. Data Model

### 8.1 Additive Record
```
code: string            // "E120"
names: string[]         // ["Carmine", "Cochineal", "INS 120"]
class: string           // "Colour"
dietary: { vegan: bool, vegetarian: bool, kosher: bool, halal: bool }
source: { animal: bool, insect: bool, plant: bool, synthetic: bool }
population: { pku: bool, sulfite_sensitivity: bool, caffeine_sensitive: bool, other: string[] }
region_rules: {
  EU: { approved: bool, warning_required: bool, notes: string },
  US: { approved: bool, warning_required: bool, notes: string }
}
evidence_level: "Regulatory" | "Consensus" | "Limited"
plain_risk: { summary: string, audience: string[] }
references: { label: string, url: string }[]
updated_at: string      // ISO 8601
```

### 8.2 Product Cache Record
```
barcode: string
ingredients_text: string
additives_found: string[]    // canonical codes
timestamp: string
region: string
```

### 8.3 Rule Pack
```
version: string
regions: string[]            // e.g., ["EU","US"]
checksum: string
diff_from: string | null
payload_url: string
signature: string
```

## 9. Risk Logic

- Regulatory warnings shall set badge = Red.
- Population cautions shall set badge = Red when relevant preference is active; else Yellow.
- Diet conflicts shall set badge = Yellow.
- Unknown or unlisted additives shall not produce a badge and shall be listed under “unmatched”.
- Evidence levels shall map:
  - Regulatory → Red or Green per approval and warning flags.
  - Consensus → Yellow if any notable concern is present.
  - Limited → Yellow unless diet conflict elevates to Red via preference.

## 10. UI Requirements

### 10.1 Scan Flow
- The camera view shall display framing guides and glare tips.
- The capture button shall trigger multi‑shot burst if text is small.
- A progress indicator shall display during OCR and parsing.

### 10.2 Results Screen
- The header shall show product summary: “X flagged, Y neutral”.
- A list of additive cards shall follow in ingredient order.
- Each card shall include:
  - Canonical name and E‑code
  - Badge with label
  - Plain risk summary
  - Icons for dietary suitability
  - “Why” link to references
- A footer shall include region and data version.

### 10.3 Empty and Error States
- When no additives are detected, the app shall offer barcode scan or manual entry.
- When OCR confidence is low, the app shall prompt to rescan.
- Network errors shall offer retry and offline mode.

## 11. API (Optional Backend)

### 11.1 Auth
- The API must support token‑based auth for update endpoints.
- Public GET endpoints for additive packs must allow signed URLs.

### 11.2 Endpoints
- `GET /v1/packs/latest?region=EU|US`  
  - Returns rule pack metadata.
- `GET /v1/packs/{version}`  
  - Returns signed payload URL and checksum.
- `GET /v1/additives/{code}`  
  - Returns a single additive record.
- `POST /v1/telemetry`  
  - Accepts anonymized metrics. Images must not be accepted.

### 11.3 Responses
- All responses shall be JSON UTF‑8.
- All responses must include version and checksum where applicable.

## 12. Telemetry
- The app shall record anonymous events: scan_started, scan_completed, ocr_confidence, additives_count, flags_count, fallback_used.
- Telemetry must be opt‑in on first launch.
- Telemetry must not include raw text or images.

## 13. Permissions
- The app shall request camera and photo library permissions only when needed.
- The app must not request location unless the user selects auto region.

## 14. Constraints and Compatibility
- iOS 15+ and Android 9+ shall be supported.
- ARM64 devices shall be supported.
- On‑device database size must not exceed 10 MB at install for the base pack.

## 15. Quality Gates and Acceptance Criteria

### 15.1 OCR and Parsing
- E‑code detection F1 shall be ≥ 0.97 on the gold set.
- Synonym recall shall be ≥ 0.95 for the supported regions.
- Mean time to result (offline) shall be ≤ 2.0 s.

### 15.2 Risk Rendering
- 100% of additives with a regulatory warning in the region shall display Red.
- 100% of diet conflicts shall display Yellow or higher.
- Plain risk lines shall average ≤ 18 words and pass Grade 6 readability.

### 15.3 Privacy and Security
- No network egress for images under default settings.
- All update payloads must pass signature validation before install.

### 15.4 Accessibility
- Color badges shall pass 4.5:1 contrast ratio.
- All icons shall include accessible labels.

## 16. Error Handling

- The app shall classify errors as:
  - `capture_error`, `ocr_error`, `parse_error`, `lookup_error`, `network_error`, `update_error`.
- The app shall log error code and context without PII.
- The app shall present user actions:
  - Rescan, manual entry, barcode fallback, retry update.

## 17. Testing

### 17.1 Data Tests
- Unit tests shall validate regex and canonicalization.
- Unit tests shall validate synonym maps and alias conflicts.
- Rule tests shall validate region precedence and badge mapping.

### 17.2 E2E Tests
- Scans of 500 labelled photos shall be executed on device farms.
- Acceptance scenarios must include:
  - Curved packaging
  - Low light
  - Mixed languages
  - Very small fonts
  - Partial occlusion

### 17.3 Security Tests
- Static analysis must pass with zero high‑severity findings.
- Update signature verification shall be tested with tampered payloads.

## 18. Content Governance

- Every additive record must include at least one primary reference.
- Changes to additive records shall require two‑person review before publish.
- Region packs must be versioned with semantic versioning.

## 19. Compliance and Legal

- The app shall include a disclaimer: informational only, not medical advice.
- The app must not state that a product is “safe” or “unsafe”. The app shall state facts and regulatory status.

## 20. Out of Scope

- Personalized nutrition plans.
- Calorie or macro analysis beyond additive risks.
- Health outcome predictions.

## 21. Sample Acceptance Scenarios

- **Candy label with E102 and E129 (EU region):**  
  - The app shall detect both codes.  
  - The app shall display Red badges with the regulatory child‑behavior warning.  
  - The product summary shall show “2 flagged”.

- **Label with “Carmine” and no E‑code (US region):**  
  - The app shall map “Carmine” to `E120`.  
  - The app shall display Yellow for vegan conflict when vegan preference is on.

- **Barcode only, offline:**  
  - The app shall display a prompt to retry online or allow manual entry.  
  - No crash and no spinner loops.

## 22. Migration and Updates

- The app shall ship with a base pack.  
- The app shall fetch diffs when online and apply them atomically.  
- The app must not downgrade packs unless integrity checks fail.

## 23. Open Questions (to be resolved before GA)
- None required for MVP. Future regions and more allergens may be added.

--- 

This document is normative. Any conflict with design documents shall resolve in favor of this requirements specification.
