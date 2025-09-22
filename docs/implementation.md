# Implementation

This is a complete, standalone implementation guide with code for the Nutrition Scanner MVP. It covers mobile (React Native + native OCR bridges), local data packs, the risk engine, barcode fallback, an optional FastAPI backend, and a Python ETL + signing pipeline.

> Targets: iOS 15+ and Android 9+.  
> Stack choices: React Native (TypeScript), on‑device OCR via iOS Vision and Android ML Kit, SQLite, Ed25519 signing, optional FastAPI backend.

---

## 0) Repository layout

```
nutrition-scanner/
  mobile/
    android/
    ios/
    src/
      app/
      components/
      data/
      ocr/
      risk/
      store/
      utils/
    package.json
    tsconfig.json
    metro.config.js
    react-native.config.js
  etl/
    data/
      additives.csv
      synonyms.csv
      references.csv
      region_rules.csv
    build_pack.py
    sign_pack.py
    verify_pack.py
    requirements.txt
    README.md
  server/
    app/
      main.py
      deps.py
      routers/
        packs.py
        telemetry.py
      models.py
      schema.py
      settings.py
    alembic/
    pyproject.toml
    README.md
  keys/
    public_key.ed25519           # checked in
    private_key.ed25519          # local only, DO NOT COMMIT
  docs/
    requirements.md
    architecture.md
    implementation.md
```

---

## 1) Mobile application

### 1.1 Create project and install deps

```bash
# New RN project
npx react-native@0.74 init NutritionScanner --template react-native-template-typescript
cd NutritionScanner

# Core deps
yarn add react-native-vision-camera react-native-permissions
yarn add react-native-quick-sqlite
yarn add react-native-fs
yarn add axios
yarn add tweetnacl @types/tweetnacl
yarn add fastest-levenshtein
yarn add pako
yarn add @react-native-async-storage/async-storage
yarn add react-native-encrypted-storage

# Barcode scanning
yarn add vision-camera-code-scanner

# iOS pods
cd ios && pod install && cd ..
```

#### iOS permissions (`ios/NutritionScanner/Info.plist`)
```xml
<key>NSCameraUsageDescription</key>
<string>Camera access is required to scan product labels and barcodes.</string>
```

#### Android permissions (`android/app/src/main/AndroidManifest.xml`)
```xml
<uses-permission android:name="android.permission.CAMERA"/>
<uses-feature android:name="android.hardware.camera.any" android:required="false"/>
```

#### Vision Camera configuration
Follow the library setup notes for Xcode build settings and Android ProGuard/R8. Ensure JSI is enabled by default in RN 0.74.

---

### 1.2 Native OCR bridges

We capture a full-resolution still photo, then pass its path to native OCR. We return tokens with text, bounding box, and a derived confidence (real where available, heuristic otherwise).

#### Type definitions (shared)

`mobile/src/ocr/types.ts`
```ts
export type OcrToken = {
  text: string;
  x: number;   // 0..1 normalized
  y: number;   // 0..1 normalized
  w: number;   // 0..1 normalized
  h: number;   // 0..1 normalized
  confidence: number; // 0..1
  lineIndex: number;
};

export type OcrResult = {
  width: number;
  height: number;
  tokens: OcrToken[];
  engine: 'ios_vision' | 'android_mlkit';
};
```

#### iOS: Vision bridge

`ios/OcrModule.swift`
```swift
import Foundation
import Vision
import React

@objc(OcrModule)
class OcrModule: NSObject {
  @objc
  static func requiresMainQueueSetup() -> Bool { return false }

  @objc(recognize:resolver:rejecter:)
  func recognize(imagePath: String,
                 resolver resolve: @escaping RCTPromiseResolveBlock,
                 rejecter reject: @escaping RCTPromiseRejectBlock) {

    let url = URL(fileURLWithPath: imagePath)
    guard let img = CIImage(contentsOf: url) else {
      reject("ocr_error", "Failed to load image", nil); return
    }

    let request = VNRecognizeTextRequest { req, err in
      if let err = err {
        reject("ocr_error", err.localizedDescription, err); return
      }
      var tokens: [[String: Any]] = []
      var lineIdx = 0
      guard let results = req.results as? [VNRecognizedTextObservation] else {
        resolve(["width": 0, "height": 0, "tokens": [], "engine": "ios_vision"]); return
      }
      for obs in results {
        let candidates = obs.topCandidates(1)
        guard let best = candidates.first else { continue }
        let box = obs.boundingBox // normalized
        // Vision doesn't give per-token directly; observations approximate lines or words.
        // Split words manually:
        let words = best.string.split(separator: " ")
        if words.count <= 1 {
          tokens.append([
            "text": best.string,
            "x": box.origin.x, "y": box.origin.y,
            "w": box.size.width, "h": box.size.height,
            "confidence": best.confidence, // 0..1
            "lineIndex": lineIdx
          ])
        } else {
          // crude word boxing by equal splits in X
          let wStep = box.size.width / CGFloat(words.count)
          for (i, word) in words.enumerated() {
            tokens.append([
              "text": String(word),
              "x": box.origin.x + CGFloat(i)*wStep, "y": box.origin.y,
              "w": wStep, "h": box.size.height,
              "confidence": best.confidence,
              "lineIndex": lineIdx
            ])
          }
        }
        lineIdx += 1
      }
      resolve(["width": 1, "height": 1, "tokens": tokens, "engine": "ios_vision"])
    }
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true

    let handler = VNImageRequestHandler(ciImage: img, options: [:])
    do { try handler.perform([request]) }
    catch { reject("ocr_error", error.localizedDescription, error) }
  }
}
```

`ios/OcrModule.m`
```objc
#import <React/RCTBridgeModule.h>
@interface RCT_EXTERN_MODULE(OcrModule, NSObject)
RCT_EXTERN_METHOD(recognize:(NSString *)imagePath
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
@end
```

Add to Xcode project and ensure Swift bridging header is configured.

#### Android: ML Kit bridge

`android/app/src/main/java/com/nutritionscanner/OcrModule.kt`
```kotlin
package com.nutritionscanner

import com.facebook.react.bridge.*
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import android.graphics.BitmapFactory

class OcrModule(reactContext: ReactApplicationContext) : ReactContextBaseJavaModule(reactContext) {
  override fun getName() = "OcrModule"

  @ReactMethod
  fun recognize(imagePath: String, promise: Promise) {
    try {
      val bmp = BitmapFactory.decodeFile(imagePath)
      val image = InputImage.fromBitmap(bmp, 0)
      val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

      recognizer.process(image)
        .addOnSuccessListener { visionText ->
          val tokens = Arguments.createArray()
          var lineIndex = 0
          for (block in visionText.textBlocks) {
            for (line in block.lines) {
              for (element in line.elements) {
                val box = element.boundingBox
                if (box != null) {
                  val token = Arguments.createMap()
                  token.putString("text", element.text)
                  // We cannot get image width/height easily without passing it; use normalized via bitmap size:
                  token.putDouble("x", box.left.toDouble() / bmp.width.toDouble())
                  token.putDouble("y", box.top.toDouble() / bmp.height.toDouble())
                  token.putDouble("w", box.width().toDouble() / bmp.width.toDouble())
                  token.putDouble("h", box.height().toDouble() / bmp.height.toDouble())
                  // ML Kit doesn't expose confidence; derive: longer words + A-Z/0-9 => higher
                  val derived = deriveConfidence(element.text)
                  token.putDouble("confidence", derived)
                  token.putInt("lineIndex", lineIndex)
                  tokens.pushMap(token)
                }
              }
              lineIndex += 1
            }
          }
          val result = Arguments.createMap()
          result.putInt("width", bmp.width)
          result.putInt("height", bmp.height)
          result.putArray("tokens", tokens)
          result.putString("engine", "android_mlkit")
          promise.resolve(result)
        }
        .addOnFailureListener { e -> promise.reject("ocr_error", e) }
    } catch (e: Exception) {
      promise.reject("ocr_error", e)
    }
  }

  private fun deriveConfidence(text: String): Double {
    val trimmed = text.trim()
    if (trimmed.isEmpty()) return 0.3
    val alnum = trimmed.count { it.isLetterOrDigit() }
    val ratio = alnum.toDouble() / trimmed.length.toDouble()
    return 0.5 + 0.5 * ratio // 0.5..1.0 heuristic
  }
}
```

`android/app/src/main/java/com/nutritionscanner/OcrPackage.kt`
```kotlin
package com.nutritionscanner

import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.uimanager.ViewManager
import android.app.Application
import android.content.Context

class OcrPackage : ReactPackage {
  override fun createNativeModules(reactContext: com.facebook.react.bridge.ReactApplicationContext): MutableList<NativeModule> {
    return mutableListOf(OcrModule(reactContext))
  }
  override fun createViewManagers(reactContext: com.facebook.react.bridge.ReactApplicationContext): MutableList<ViewManager<*, *>> {
    return mutableListOf()
  }
}
```

`android/app/src/main/java/com/nutritionscanner/MainApplication.java` (register package)
```java
// inside getPackages()
packages.add(new com.nutritionscanner.OcrPackage());
```

#### JS wrapper

`mobile/src/ocr/index.ts`
```ts
import { NativeModules } from 'react-native';
import type { OcrResult } from './types';

const { OcrModule } = NativeModules;

export async function recognizeImage(imagePath: string): Promise<OcrResult> {
  const res = await OcrModule.recognize(imagePath);
  return res as OcrResult;
}
```

---

### 1.3 Camera capture + barcode

We use VisionCamera for still capture and the code-scanner plugin for barcodes.

`mobile/src/app/ScanScreen.tsx`
```tsx
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { Camera, useCameraDevices } from 'react-native-vision-camera';
import { useScanBarcodes, BarcodeFormat } from 'vision-camera-code-scanner';
import RNFS from 'react-native-fs';
import { recognizeImage } from '../ocr';
import { parseIngredients } from '../data/parser';
import { runRiskEngine } from '../risk/engine';
import { loadPrefs } from '../store/prefs';
import { lookupFromDb } from '../data/lookup';
import { fetchBarcodeIngredients } from '../data/barcode';

export default function ScanScreen({ navigation }: any) {
  const devices = useCameraDevices();
  const device = devices.back;
  const camera = useRef<Camera>(null);
  const [isBusy, setBusy] = useState(false);
  const [barcodeMode, setBarcodeMode] = useState(false);

  const [frameProcessor, barcodes] = useScanBarcodes([BarcodeFormat.EAN_13, BarcodeFormat.UPC_A], {
    checkInverted: true
  });

  useEffect(() => {
    (async () => {
      const status = await Camera.requestCameraPermission();
      if (status !== 'granted') Alert.alert('Camera permission required');
    })();
  }, []);

  useEffect(() => {
    if (!barcodeMode) return;
    const code = barcodes[0]?.displayValue;
    if (code) {
      setBusy(true);
      (async () => {
        try {
          const ingredients = await fetchBarcodeIngredients(code);
          const tokens = parseIngredients(ingredients);
          const additives = await lookupFromDb(tokens);
          const prefs = await loadPrefs();
          const result = runRiskEngine(additives, prefs);
          navigation.navigate('Results', { result, source: 'barcode', code });
        } catch (e: any) {
          Alert.alert('Barcode lookup failed', e.message ?? String(e));
        } finally {
          setBusy(false);
        }
      })();
    }
  }, [barcodes, barcodeMode]);

  const capture = async () => {
    if (!camera.current || isBusy) return;
    setBusy(true);
    try {
      const photo = await camera.current.takePhoto({ qualityPrioritization: 'quality', flash: 'off' });
      const path = `${RNFS.CachesDirectoryPath}/scan-${Date.now()}.jpg`;
      await RNFS.copyFile(photo.path, path);
      const ocr = await recognizeImage(path);
      const recognized = ocr.tokens.map(t => t.text).join(' ');
      const tokens = parseIngredients(recognized);
      if (tokens.length === 0) {
        setBarcodeMode(true); // fallback
        setBusy(false);
        return;
      }
      const additives = await lookupFromDb(tokens);
      const prefs = await loadPrefs();
      const result = runRiskEngine(additives, prefs);
      navigation.navigate('Results', { result, source: 'ocr' });
    } catch (e: any) {
      Alert.alert('Scan failed', e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!device) return <View style={{ flex:1, justifyContent:'center', alignItems:'center' }}><Text>Loading camera…</Text></View>;

  return (
    <View style={{ flex:1 }}>
      <Camera
        ref={camera}
        style={{ flex: 1 }}
        device={device}
        isActive={!isBusy}
        photo={true}
        frameProcessor={barcodeMode ? frameProcessor : undefined}
        frameProcessorFps={barcodeMode ? 5 : undefined}
      />
      <View style={{ position:'absolute', bottom:30, left:0, right:0, alignItems:'center' }}>
        {!isBusy && !barcodeMode && (
          <TouchableOpacity onPress={capture} style={{ backgroundColor:'#000', padding:16, borderRadius:40 }}>
            <Text style={{ color:'#fff' }}>Capture</Text>
          </TouchableOpacity>
        )}
        {barcodeMode && <Text style={{ textAlign:'center', backgroundColor:'#fff', padding:8 }}>Scanning barcode…</Text>}
        {isBusy && <ActivityIndicator size="large" />}
      </View>
    </View>
  );
}
```

---

### 1.4 Ingredient parsing and normalization

`mobile/src/data/parser.ts`
```ts
import { distance as levenshtein } from 'fastest-levenshtein';

const REG_E = /\bE\s*0*(\d{3})([A-Z])?\b/gi;
const REG_INS = /\bINS\s*0*(\d{3})([A-Z])?\b/gi;

export type Token = { raw: string; canonical?: string; type: 'ecode'|'name'|'other'; };

export function normalize(s: string): string {
  return s
    .normalize('NFKC')
    .replace(/\u200B/g, '')
    .toUpperCase()
    .normalize('NFKD').replace(/[\u0300-\u036f]/g, '') // strip diacritics
    .replace(/\s+/g, ' ')
    .trim();
}

export function parseIngredients(text: string): Token[] {
  const norm = normalize(text);
  const parts = norm.split(/[,(\)]/).map(s => s.trim()).filter(Boolean);
  const tokens: Token[] = [];
  for (const p of parts) {
    let m;
    REG_E.lastIndex = 0; REG_INS.lastIndex = 0;
    if ((m = REG_E.exec(p)) || (m = REG_INS.exec(p))) {
      const code = `E${m[1]}${m[2] ?? ''}`;
      tokens.push({ raw: p, canonical: code, type: 'ecode' });
    } else {
      tokens.push({ raw: p, type: 'name' });
    }
  }
  return tokens;
}

// Fuzzy helper for OCR slips like O↔0, I↔1, S↔5
export function looksLike(additiveName: string, candidate: string): boolean {
  const a = normalize(additiveName);
  const b = normalize(candidate)
    .replace(/O/g, '0')
    .replace(/I/g, '1')
    .replace(/S/g, '5');
  const d = levenshtein(a, b);
  return d <= Math.max(1, Math.floor(a.length * 0.15));
}
```

---

### 1.5 Local database and lookup

We ship a prebuilt SQLite with base pack or import a JSON pack into SQLite on first run.

#### Schema

`mobile/src/data/schema.sql`
```sql
CREATE TABLE IF NOT EXISTS additives (
  code TEXT PRIMARY KEY,
  class TEXT NOT NULL,
  evidence_level TEXT NOT NULL,
  plain_summary TEXT NOT NULL,
  dietary_vegan INTEGER NOT NULL,
  dietary_vegetarian INTEGER NOT NULL,
  dietary_kosher INTEGER NOT NULL,
  dietary_halal INTEGER NOT NULL,
  source_animal INTEGER NOT NULL,
  source_insect INTEGER NOT NULL,
  source_plant INTEGER NOT NULL,
  source_synthetic INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS names (
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  PRIMARY KEY (code, name),
  FOREIGN KEY (code) REFERENCES additives(code) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS region_rules (
  code TEXT NOT NULL,
  region TEXT NOT NULL,              -- 'EU' | 'US'
  approved INTEGER NOT NULL,
  warning_required INTEGER NOT NULL,
  notes TEXT,
  PRIMARY KEY (code, region),
  FOREIGN KEY (code) REFERENCES additives(code) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS references_catalog (
  ref_id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  publisher TEXT NOT NULL,
  url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS additive_refs (
  code TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (code, ref_id),
  FOREIGN KEY (code) REFERENCES additives(code) ON DELETE CASCADE,
  FOREIGN KEY (ref_id) REFERENCES references_catalog(ref_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS aliases (
  alias TEXT PRIMARY KEY,   -- normalized name
  code TEXT NOT NULL,
  FOREIGN KEY (code) REFERENCES additives(code) ON DELETE CASCADE
);

-- product cache
CREATE TABLE IF NOT EXISTS product_cache (
  barcode TEXT PRIMARY KEY,
  ingredients_text TEXT NOT NULL,
  additives_found TEXT NOT NULL, -- JSON array of codes
  timestamp INTEGER NOT NULL,
  region TEXT NOT NULL
);

PRAGMA user_version=1;
```

#### DB bootstrap and pack import

`mobile/src/data/db.ts`
```ts
import { open } from 'react-native-quick-sqlite';
import RNFS from 'react-native-fs';
import { inflate } from 'pako';
import nacl from 'tweetnacl';
import { TextDecoder } from 'text-encoding';

export const DB = open({ name: 'additives.db', location: 'default' });

export function execSql(sql: string) {
  DB.execute(sql);
}

export function prepareSchema(schemaSql: string) {
  execSql(schemaSql);
}

type PackMeta = {
  version: string;
  regions: string[];
  checksum: string;      // hex SHA-256 of payload bytes
  signature: string;     // base64 Ed25519 over checksum bytes
  diff_from?: string|null;
};

type PackPayload = {
  additives: any[];
  names: { code: string; name: string }[];
  region_rules: any[];
  references: any[];
  additive_refs: any[];
  aliases: { alias: string; code: string }[];
};

export async function installPack(meta: PackMeta, payloadBytes: Uint8Array, publicKey: Uint8Array) {
  // Verify checksum and signature
  const hashHex = await sha256Hex(payloadBytes);
  if (hashHex !== meta.checksum) throw new Error('Checksum mismatch');
  const sig = base64ToBytes(meta.signature);
  const ok = nacl.sign.detached.verify(hexToBytes(meta.checksum), sig, publicKey);
  if (!ok) throw new Error('Signature verify failed');

  const json = new TextDecoder().decode(payloadBytes);
  const pack = JSON.parse(json) as PackPayload;

  DB.execute('BEGIN');
  try {
    DB.execute('DELETE FROM aliases');
    DB.execute('DELETE FROM additive_refs');
    DB.execute('DELETE FROM references_catalog');
    DB.execute('DELETE FROM region_rules');
    DB.execute('DELETE FROM names');
    DB.execute('DELETE FROM additives');

    const insAdd = DB.prepare(
      'INSERT INTO additives (code,class,evidence_level,plain_summary,dietary_vegan,dietary_vegetarian,dietary_kosher,dietary_halal,source_animal,source_insect,source_plant,source_synthetic,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)'
    );
    for (const a of pack.additives) {
      insAdd.execute([
        a.code, a.class, a.evidence_level, a.plain_summary,
        a.dietary.vegan?1:0, a.dietary.vegetarian?1:0, a.dietary.kosher?1:0, a.dietary.halal?1:0,
        a.source.animal?1:0, a.source.insect?1:0, a.source.plant?1:0, a.source.synthetic?1:0,
        a.updated_at
      ]);
    }
    insAdd.finalize();

    const insName = DB.prepare('INSERT INTO names (code,name) VALUES (?,?)');
    for (const n of pack.names) insName.execute([n.code, n.name]);
    insName.finalize();

    const insRule = DB.prepare('INSERT INTO region_rules (code,region,approved,warning_required,notes) VALUES (?,?,?,?,?)');
    for (const r of pack.region_rules) insRule.execute([r.code, r.region, r.approved?1:0, r.warning_required?1:0, r.notes ?? null]);
    insRule.finalize();

    const insRef = DB.prepare('INSERT INTO references_catalog (ref_id,label,publisher,url) VALUES (?,?,?,?)');
    for (const r of pack.references) insRef.execute([r.ref_id, r.label, r.publisher, r.url]);
    insRef.finalize();

    const insAR = DB.prepare('INSERT INTO additive_refs (code,ref_id) VALUES (?,?)');
    for (const ar of pack.additive_refs) insAR.execute([ar.code, ar.ref_id]);
    insAR.finalize();

    const insAlias = DB.prepare('INSERT INTO aliases (alias,code) VALUES (?,?)');
    for (const al of pack.aliases) insAlias.execute([al.alias, al.code]);
    insAlias.finalize();

    DB.execute('COMMIT');
  } catch (e) {
    DB.execute('ROLLBACK');
    throw e;
  }
}

// utils
function base64ToBytes(b64: string): Uint8Array {
  const bin = global.atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i=0;i<bin.length;i++) arr[i] = bin.charCodeAt(i);
  return arr;
}
function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length/2);
  for (let i=0;i<out.length;i++) out[i] = parseInt(hex.substr(i*2,2),16);
  return out;
}
async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2,'0')).join('');
}
```

> Note: On older RN Android builds, `crypto.subtle` may not be present. If so, add a small SHA‑256 polyfill or compute the checksum in ETL and rely on signature verification only.

#### Lookup functions

`mobile/src/data/lookup.ts`
```ts
import { DB } from './db';
import { normalize, looksLike, Token } from './parser';

export type Additive = {
  code: string;
  names: string[];
  class: string;
  plain_summary: string;
  evidence_level: 'Regulatory'|'Consensus'|'Limited';
  dietary: { vegan:boolean; vegetarian:boolean; kosher:boolean; halal:boolean };
  source: { animal:boolean; insect:boolean; plant:boolean; synthetic:boolean };
  region_rules: Record<string,{ approved:boolean; warning_required:boolean; notes?:string|null }>;
  refs: string[];
};

export async function lookupFromDb(tokens: Token[]): Promise<Additive[]> {
  const codes = new Set<string>();
  // 1) Direct E-codes
  for (const t of tokens) if (t.canonical) codes.add(t.canonical);

  // 2) Names and fuzzy aliases
  for (const t of tokens.filter(x => x.type !== 'ecode')) {
    const norm = normalize(t.raw);
    const row = DB.execute('SELECT code FROM aliases WHERE alias=?', [norm]).rows?._array?.[0];
    if (row?.code) { codes.add(row.code); continue; }
    // Fuzzy: get top 50 aliases and test distance
    const aliases = DB.execute('SELECT alias,code FROM aliases').rows?._array ?? [];
    for (const a of aliases) {
      if (looksLike(a.alias, norm)) { codes.add(a.code); break; }
    }
  }

  if (!codes.size) return [];

  const lst = `'${Array.from(codes).join("','")}'`;
  const addRows = DB.execute(`SELECT * FROM additives WHERE code IN (${lst})`).rows?._array ?? [];
  const out: Additive[] = [];
  for (const a of addRows) {
    const names = DB.execute('SELECT name FROM names WHERE code=?', [a.code]).rows?._array?.map((x:any)=>x.name) ?? [];
    const rr = DB.execute('SELECT region,approved,warning_required,notes FROM region_rules WHERE code=?', [a.code]).rows?._array ?? [];
    const refs = DB.execute('SELECT ref_id FROM additive_refs WHERE code=?', [a.code]).rows?._array?.map((x:any)=>x.ref_id) ?? [];
    const region_rules: any = {};
    for (const r of rr) region_rules[r.region] = { approved: !!r.approved, warning_required: !!r.warning_required, notes: r.notes };
    out.push({
      code: a.code,
      names,
      class: a.class,
      plain_summary: a.plain_summary,
      evidence_level: a.evidence_level,
      dietary: { vegan: !!a.dietary_vegan, vegetarian: !!a.dietary_vegetarian, kosher: !!a.dietary_kosher, halal: !!a.dietary_halal },
      source: { animal: !!a.source_animal, insect: !!a.source_insect, plant: !!a.source_plant, synthetic: !!a.source_synthetic },
      region_rules,
      refs
    });
  }
  return out;
}
```

---

### 1.6 Risk engine

`mobile/src/risk/engine.ts`
```ts
import type { Additive } from '../data/lookup';
import { loadPrefs } from '../store/prefs';

export type Badge = 'RED'|'YELLOW'|'GREEN';

export type RiskResult = {
  product: { flagged: number; neutral: number; unmatched: number };
  items: {
    code: string;
    name: string;
    badge: Badge;
    plain: string;
    audience: string[];
    refs: string[];
    reasons: string[]; // rule ids
  }[];
};

export type Prefs = {
  region: 'EU'|'US';
  diet: { vegan:boolean; vegetarian:boolean; kosher:boolean; halal:boolean };
  sensitivities: { pku:boolean; sulfites:boolean; caffeine:boolean };
  childMode: boolean;
};

export function runRiskEngine(additives: Additive[], prefs: Prefs): RiskResult {
  let flagged = 0, neutral = 0;
  const items = additives.map(a => {
    const rr = a.region_rules[prefs.region];
    const audience: string[] = [];
    const reasons: string[] = [];
    let badge: Badge = 'GREEN';

    // 1) Regulatory warnings
    if (rr?.warning_required) {
      badge = 'RED'; reasons.push(`regulatory_warning:${prefs.region}`);
      if (prefs.childMode) audience.push('Kids');
    }

    // 2) Population cautions
    if (a.names.some(n => n.includes('ASPARTAME')) && prefs.sensitivities.pku) {
      badge = 'RED'; reasons.push('population:pku'); audience.push('PKU');
    }
    if (a.names.some(n => n.includes('SULFITE')) && prefs.sensitivities.sulfites) {
      badge = 'RED'; reasons.push('population:sulfites'); audience.push('Sulfite sensitivity');
    }

    // 3) Diet conflicts
    if (a.source.animal && prefs.diet.vegan) { badge = badge==='RED'?'RED':'YELLOW'; reasons.push('diet:vegan'); audience.push('Vegan'); }
    if (a.source.insect && prefs.diet.vegan) { badge = 'YELLOW'; reasons.push('diet:insect'); audience.push('Vegan'); }

    // 4) Evidence level heuristic
    if (badge==='GREEN' && a.evidence_level === 'Limited') { badge = 'YELLOW'; reasons.push('evidence:limited'); }

    if (badge !== 'GREEN') flagged += 1; else neutral += 1;

    return {
      code: a.code,
      name: a.names[0] ?? a.code,
      badge,
      plain: a.plain_summary,
      audience,
      refs: a.refs,
      reasons
    };
  });

  return {
    product: { flagged, neutral, unmatched: 0 },
    items
  };
}
```

---

### 1.7 Preferences store

`mobile/src/store/prefs.ts`
```ts
import EncryptedStorage from 'react-native-encrypted-storage';

export type Prefs = {
  region: 'EU'|'US';
  diet: { vegan:boolean; vegetarian:boolean; kosher:boolean; halal:boolean };
  sensitivities: { pku:boolean; sulfites:boolean; caffeine:boolean };
  childMode: boolean;
};

const DEFAULT: Prefs = {
  region: 'EU',
  diet: { vegan:false, vegetarian:false, kosher:false, halal:false },
  sensitivities: { pku:false, sulfites:false, caffeine:false },
  childMode: false
};

export async function loadPrefs(): Promise<Prefs> {
  const s = await EncryptedStorage.getItem('prefs');
  if (!s) return DEFAULT;
  try { return JSON.parse(s) as Prefs; } catch { return DEFAULT; }
}

export async function savePrefs(p: Prefs) {
  await EncryptedStorage.setItem('prefs', JSON.stringify(p));
}
```

---

### 1.8 Results screen

`mobile/src/app/ResultsScreen.tsx`
```tsx
import React from 'react';
import { View, Text, FlatList } from 'react-native';
import type { RiskResult } from '../risk/engine';

export default function ResultsScreen({ route }: any) {
  const { result, source } = route.params as { result: RiskResult, source: 'ocr'|'barcode' };
  return (
    <View style={{ flex:1, padding:16 }}>
      <Text style={{ fontSize:18, fontWeight:'600' }}>
        {source === 'ocr' ? 'Label scan' : 'Barcode'} — {result.product.flagged} flagged, {result.product.neutral} neutral
      </Text>
      <FlatList
        data={result.items}
        keyExtractor={i => i.code}
        renderItem={({ item }) => (
          <View style={{ paddingVertical:12, borderBottomWidth:1, borderColor:'#eee' }}>
            <Text style={{ fontSize:16, fontWeight:'600' }}>{item.name} ({item.code})</Text>
            <Text accessibilityLabel={`Risk badge ${item.badge}`} style={{
              alignSelf:'flex-start', paddingHorizontal:8, paddingVertical:2, borderRadius:4,
              backgroundColor: item.badge === 'RED' ? '#c0392b' : item.badge === 'YELLOW' ? '#f1c40f' : '#27ae60',
              color: item.badge === 'YELLOW' ? '#000' : '#fff', marginTop:4, marginBottom:4
            }}>{item.badge}</Text>
            <Text>{item.plain}</Text>
            {item.audience.length > 0 && <Text>Audience: {item.audience.join(', ')}</Text>}
          </View>
        )}
      />
      <Text style={{ marginTop:8, color:'#666' }}>Region and data version available in Settings.</Text>
    </View>
  );
}
```

---

### 1.9 Navigation bootstrap

`mobile/src/app/App.tsx`
```tsx
import React, { useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import ScanScreen from './ScanScreen';
import ResultsScreen from './ResultsScreen';
import { prepareSchema } from '../data/db';
import schemaSql from '../data/schema.sql?raw';

const Stack = createNativeStackNavigator();

export default function App() {
  useEffect(() => { prepareSchema(schemaSql as unknown as string); }, []);
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="Scan" component={ScanScreen} />
        <Stack.Screen name="Results" component={ResultsScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

Update `index.js` to register the `App`.

---

### 1.10 Barcode fallback HTTP + cache

`mobile/src/data/barcode.ts`
```ts
import axios from 'axios';
import { DB } from './db';

const OFF_BASE = 'https://world.openfoodfacts.org/api/v2/product';

export async function fetchBarcodeIngredients(code: string): Promise<string> {
  // cache
  const row = DB.execute('SELECT ingredients_text FROM product_cache WHERE barcode=?', [code]).rows?._array?.[0];
  if (row?.ingredients_text) return row.ingredients_text;

  const url = `${OFF_BASE}/${code}.json?fields=code,ingredients_text`;
  const res = await axios.get(url, { timeout: 3500 });
  const itxt = (res.data?.product?.ingredients_text as string) ?? '';
  if (!itxt) throw new Error('No ingredients found');

  DB.execute(
    'INSERT OR REPLACE INTO product_cache (barcode,ingredients_text,additives_found,timestamp,region) VALUES (?,?,?,?,?)',
    [code, itxt, '[]', Date.now(), 'NA']
  );
  return itxt;
}
```

> If you require offline‑only behavior, skip remote calls and prompt for manual entry instead.

---

## 2) ETL and Pack Signing (Python)

### 2.1 Install

`etl/requirements.txt`
```
pandas==2.2.2
PyNaCl==1.5.0
ujson==5.10.0
```

```bash
cd etl
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2.2 Input CSVs

`etl/data/additives.csv`
```
code,class,evidence_level,plain_summary,dietary_vegan,dietary_vegetarian,dietary_kosher,dietary_halal,source_animal,source_insect,source_plant,source_synthetic,updated_at
E102,Colour,Regulatory,"EU warning: possible effects on attention/activity in children.",1,1,1,1,0,0,0,1,2025-09-01T00:00:00Z
E129,Colour,Regulatory,"EU warning: possible effects on attention/activity in children.",1,1,1,1,0,0,0,1,2025-09-01T00:00:00Z
E120,Colour,Consensus,"Carmine from insects; not suitable for vegans.",0,1,1,1,0,1,0,0,2025-09-01T00:00:00Z
E330,AcidityRegulator,Consensus,"Citric acid used as acidity regulator; no special population warning.",1,1,1,1,0,0,1,1,2025-09-01T00:00:00Z
```

`etl/data/synonyms.csv`
```
code,name
E102,TARTRAZINE
E102,FD&C YELLOW 5
E129,ALLURA RED
E129,FD&C RED 40
E120,CARMINE
E120,COCHINEAL
E330,CITRIC ACID
```

`etl/data/references.csv`
```
ref_id,label,publisher,url
EU1333,EU Reg. 1333/2008 additive list,EUR-Lex,https://eur-lex.europa.eu/
FSA_AZO,FSA guidance on azo dye warnings,UK FSA,https://www.food.gov.uk/
FDA_SAAF,FDA Substances Added to Food,FDA,https://www.fda.gov/
```

`etl/data/region_rules.csv`
```
code,region,approved,warning_required,notes
E102,EU,1,1,EU child behavior warning applies to certain azo dyes
E102,US,1,0,
E129,EU,1,1,EU child behavior warning applies to certain azo dyes
E129,US,1,0,
E120,EU,1,0,Not vegan
E120,US,1,0,Not vegan
E330,EU,1,0,
E330,US,1,0,
```

### 2.3 Build pack

`etl/build_pack.py`
```python
import pandas as pd, json, ujson, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'out'
OUT.mkdir(exist_ok=True, parents=True)

def norm(s: str) -> str:
  return (s or '').strip().upper()

def build(version: str, regions=('EU','US')):
  add = pd.read_csv(DATA/'additives.csv')
  syn = pd.read_csv(DATA/'synonyms.csv')
  refs = pd.read_csv(DATA/'references.csv')
  rules = pd.read_csv(DATA/'region_rules.csv')

  # Additives list
  additives = []
  for _, r in add.iterrows():
    additives.append({
      "code": r.code,
      "class": r['class'],
      "evidence_level": r.evidence_level,
      "plain_summary": r.plain_summary,
      "dietary": {
        "vegan": bool(r.dietary_vegan),
        "vegetarian": bool(r.dietary_vegetarian),
        "kosher": bool(r.dietary_kosher),
        "halal": bool(r.dietary_halal)
      },
      "source": {
        "animal": bool(r.source_animal),
        "insect": bool(r.source_insect),
        "plant": bool(r.source_plant),
        "synthetic": bool(r.source_synthetic)
      },
      "updated_at": r.updated_at
    })

  names = [{"code": r.code, "name": norm(r.name)} for _, r in syn.iterrows()]

  region_rules = []
  for _, r in rules.iterrows():
    if r.region not in regions: continue
    region_rules.append({
      "code": r.code, "region": r.region,
      "approved": bool(r.approved),
      "warning_required": bool(r.warning_required),
      "notes": r.notes if isinstance(r.notes, str) else None
    })

  references = []
  for _, r in refs.iterrows():
    references.append({"ref_id": r.ref_id, "label": r.label, "publisher": r.publisher, "url": r.url})

  additive_refs = [
    {"code": "E102", "ref_id": "EU1333"},
    {"code": "E102", "ref_id": "FSA_AZO"},
    {"code": "E129", "ref_id": "EU1333"},
    {"code": "E129", "ref_id": "FSA_AZO"},
    {"code": "E120", "ref_id": "FDA_SAAF"},
    {"code": "E330", "ref_id": "FDA_SAAF"}
  ]

  aliases = [{"alias": norm(n["name"]), "code": n["code"]} for n in names]

  payload = {
    "additives": sorted(additives, key=lambda x: x["code"]),
    "names": sorted(names, key=lambda x: (x["code"], x["name"])),
    "region_rules": sorted(region_rules, key=lambda x: (x["code"], x["region"])),
    "references": sorted(references, key=lambda x: x["ref_id"]),
    "additive_refs": sorted(additive_refs, key=lambda x: (x["code"], x["ref_id"])),
    "aliases": sorted(aliases, key=lambda x: (x["alias"], x["code"]))
  }

  payload_bytes = ujson.dumps(payload, ensure_ascii=False, escape_forward_slashes=False, indent=None, sort_keys=False).encode('utf-8')
  checksum = hashlib.sha256(payload_bytes).hexdigest()

  meta = {
    "version": version,
    "regions": list(regions),
    "checksum": checksum,
    "signature": "",
    "diff_from": None
  }

  (OUT/'payload.json').write_bytes(payload_bytes)
  (OUT/'meta.json').write_text(json.dumps(meta, indent=2))
  print("Built payload and meta (unsigned).")

if __name__ == "__main__":
  build(version="2025.09.01")
```

### 2.4 Sign pack

`etl/sign_pack.py`
```python
import json, nacl.signing, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out'
KEYS = ROOT.parent / 'keys'

def sign():
  payload = (OUT/'payload.json').read_bytes()
  checksum = hashlib.sha256(payload).hexdigest()
  sk = (KEYS/'private_key.ed25519').read_bytes()
  signer = nacl.signing.SigningKey(sk)
  sig = signer.sign(bytes.fromhex(checksum)).signature
  meta = json.loads((OUT/'meta.json').read_text())
  meta['checksum'] = checksum
  meta['signature'] = sig.hex()  # hex for portability
  (OUT/'meta.json').write_text(json.dumps(meta, indent=2))
  print("Signed meta.json")

if __name__ == "__main__":
  sign()
```

> Generate keys once:
>
> ```bash
> python - <<'PY'
> import nacl.signing, pathlib
> p = pathlib.Path('keys'); p.mkdir(exist_ok=True)
> sk = nacl.signing.SigningKey.generate()
> (p/'private_key.ed25519').write_bytes(bytes(sk))
> (p/'public_key.ed25519').write_bytes(bytes(sk.verify_key))
> print("Keys written to keys/")
> PY
> ```

### 2.5 Verify pack (debug)

`etl/verify_pack.py`
```python
import json, nacl.signing, binascii
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out'
KEYS = ROOT.parent / 'keys'

def verify():
  payload = (OUT/'payload.json').read_bytes()
  meta = json.loads((OUT/'meta.json').read_text())
  checksum_hex = meta['checksum']
  signature_hex = meta['signature']
  pk = (KEYS/'public_key.ed25519').read_bytes()
  vk = nacl.signing.VerifyKey(pk)
  try:
    vk.verify(bytes.fromhex(checksum_hex), bytes.fromhex(signature_hex))
    print("Signature OK")
  except binascii.Error as e:
    print("Bad hex:", e)
  except Exception as e:
    print("Verify failed:", e)

if __name__ == "__main__":
  verify()
```

---

## 3) Optional backend (FastAPI)

### 3.1 Install

`server/pyproject.toml`
```toml
[project]
name = "nutrition-scanner-server"
version = "0.1.0"
dependencies = ["fastapi==0.115.0","uvicorn[standard]==0.30.6","pydantic>=2.0,<3.0"]
```

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 3.2 App code

`server/app/main.py`
```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pathlib import Path
import json

app = FastAPI(title="Nutrition Scanner API")
BASE = Path(__file__).resolve().parents[2] / "etl" / "out"

@app.get("/v1/packs/latest")
def latest(region: str = "EU"):
  # Single pack rollout example
  meta = json.loads((BASE/"meta.json").read_text())
  return JSONResponse(meta)

@app.get("/v1/packs/{version}/payload")
def get_payload(version: str):
  p = BASE/"payload.json"
  if not p.exists(): raise HTTPException(404, "Not found")
  return FileResponse(p)

@app.post("/v1/telemetry")
def telemetry(evt: dict):
  # Drop on floor in MVP. Ensure no PII.
  return {"ok": True}
```

Run: `uvicorn app.main:app --reload`

---

## 4) Pack download and install on device

`mobile/src/data/packs.ts`
```ts
import axios from 'axios';
import { installPack } from './db';
import RNFS from 'react-native-fs';
import { TextEncoder } from 'text-encoding';

const PUBLIC_KEY_HEX = '<<PASTE_HEX_OF_PUBLIC_KEY>>';

export async function updatePacks(baseUrl: string) {
  const meta = (await axios.get(`${baseUrl}/v1/packs/latest`)).data;
  const payloadRes = await axios.get(`${baseUrl}/v1/packs/${meta.version}/payload`, { responseType: 'arraybuffer' });
  const bytes = new Uint8Array(payloadRes.data);
  const pub = hexToBytes(PUBLIC_KEY_HEX);
  await installPack(meta, bytes, pub);
}

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length/2);
  for (let i=0;i<out.length;i++) out[i] = parseInt(hex.substr(i*2,2),16);
  return out;
}
```

Call `updatePacks(BASE_URL)` on first app launch when online, else ship a baseline SQLite created during build.

---

## 5) Unit tests (parser and risk engine)

`mobile/jest.config.js`
```js
module.exports = {
  preset: 'react-native',
  transformIgnorePatterns: ['node_modules/(?!react-native|@react-native|react-native-quick-sqlite)'],
  setupFiles: ['<rootDir>/jest.setup.js']
}
```

`mobile/src/data/parser.test.ts`
```ts
import { parseIngredients, normalize } from './parser';

test('detects E-codes and names', () => {
  const t = parseIngredients('Sugar, Tartrazine (E102), Allura Red E129, Citric Acid (E330)');
  const codes = t.filter(x => x.canonical).map(x => x.canonical);
  expect(codes).toEqual(expect.arrayContaining(['E102','E129','E330']));
});
```

`mobile/src/risk/engine.test.ts`
```ts
import { runRiskEngine } from './engine';

test('EU azo dyes are RED', () => {
  const adds = [{
    code:'E102', names:['TARTRAZINE'],
    class:'Colour', plain_summary:'EU warning...', evidence_level:'Regulatory',
    dietary:{vegan:true,vegetarian:true,kosher:true,halal:true},
    source:{animal:false,insect:false,plant:false,synthetic:true},
    region_rules:{EU:{approved:true,warning_required:true},US:{approved:true,warning_required:false}},
    refs:['EU1333']
  }];
  const prefs = { region:'EU', diet:{vegan:false,vegetarian:false,kosher:false,halal:false}, sensitivities:{pku:false,sulfites:false,caffeine:false}, childMode:true };
  const r = runRiskEngine(adds as any, prefs as any);
  expect(r.items[0].badge).toBe('RED');
});
```

Run: `yarn jest`

---

## 6) Accessibility

- All badge colors accompanied by text labels (`RED`, `YELLOW`, `GREEN`).
- VoiceOver/TalkBack labels via `accessibilityLabel` in ResultsScreen.
- Text respects system font scaling. Avoid fixed heights.

---

## 7) Performance budgets

- Use still capture, not real‑time OCR per frame.
- Use `frameProcessor` only for barcode fallback at 5 fps.
- Keep pack JSON ≤ 10 MB. Prefer SQLite prebuilt or compress payload with gzip in transport.

---

## 8) Security and privacy

- Images never uploaded.
- Pack signature verified before install.
- Preferences stored encrypted via `react-native-encrypted-storage`.
- Telemetry opt‑in. Never include raw text or images.

---

## 9) Build and release

- iOS: `yarn ios` then archive via Xcode.
- Android: `yarn android` then `./gradlew bundleRelease`.
- Ensure Info.plist/Manifest include camera permissions only. No location.

---

## 10) Sample end‑to‑end scenario

1. ETL: `python etl/build_pack.py && python etl/sign_pack.py && python etl/verify_pack.py`.
2. Server: `uvicorn app.main:app --reload`.
3. Mobile first run:
   - Prepare schema.
   - `updatePacks(BASE_URL)` loads meta and payload, verifies Ed25519, installs SQLite rows.
   - User scans label. OCR returns tokens. Parser extracts `E102`, `E129`, `E330` and maps `CARMINE` if present.
   - Lookup returns additive records. Risk engine marks E102/E129 as RED in EU. Summary shows “2 flagged, 1 neutral”.

---

## 11) Troubleshooting

- **iOS OCR empty:** Ensure the image path exists and Vision permission is set. Validate file handling under `react-native-vision-camera`.
- **Android missing confidence:** Heuristic derivation is expected. Badge logic relies on lookup + rules, not raw OCR confidence.
- **DB locked errors:** Use single DB instance (`react-native-quick-sqlite`). Avoid long transactions on UI thread.

---

## 12) Appendix: Minimal prebuilt SQLite (optional)

You can ship `additives.db` preloaded. Run a one‑off script (Node or Python) that executes `schema.sql` and inserts from `payload.json`. Place the DB under `mobile/ios/` and `mobile/android/app/src/main/assets/` as required by your SQLite library, then copy to app data dir on first launch.

---

## 13) Appendix: Pack meta format

```json
{
  "version": "2025.09.01",
  "regions": ["EU","US"],
  "checksum": "<hex sha256 of payload bytes>",
  "signature": "<hex ed25519(sig(checksum_bytes))>",
  "diff_from": null
}
```

---

You now have all components to implement the MVP: camera + OCR bridges, parser, local DB and pack installer, risk engine, barcode fallback, ETL + signing, and an optional backend serving signed packs.
