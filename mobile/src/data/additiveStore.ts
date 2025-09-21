import fs from 'fs';
import path from 'path';

import { looksLike, normalize, Token } from './parser';
import { AdditivePack, AdditiveRecord, RegionCode } from './types';

export type MatchMethod = 'code' | 'alias' | 'fuzzy';

export interface LookupMatch {
  record: AdditiveRecord;
  matchedAlias: string;
  method: MatchMethod;
  token: Token;
  confidence: number;
}

export interface LookupResult {
  matches: LookupMatch[];
  unresolved: Token[];
}

export interface LookupOptions {
  allowFuzzy?: boolean;
}

export class AdditiveStore {
  private readonly pack: AdditivePack;
  private readonly codeIndex: Map<string, AdditiveRecord> = new Map();
  private readonly aliasIndex: Map<string, string> = new Map();

  private constructor(pack: AdditivePack) {
    this.pack = pack;
    for (const additive of pack.additives) {
      this.codeIndex.set(additive.code, additive);
      for (const name of additive.names) {
        this.aliasIndex.set(normalize(name), additive.code);
      }
    }

    for (const [alias, code] of Object.entries(pack.alias_index)) {
      const normalizedAlias = normalize(alias);
      if (!this.aliasIndex.has(normalizedAlias)) {
        this.aliasIndex.set(normalizedAlias, code);
      }
    }
  }

  static fromFile(filePath: string): AdditiveStore {
    const payload = fs.readFileSync(filePath, 'utf-8');
    const pack = JSON.parse(payload) as AdditivePack;
    return new AdditiveStore(pack);
  }

  static fromPack(pack: AdditivePack): AdditiveStore {
    return new AdditiveStore(pack);
  }

  get version(): string {
    return this.pack.version;
  }

  listRegions(): RegionCode[] {
    const regions = new Set<RegionCode>();
    for (const additive of this.pack.additives) {
      for (const key of Object.keys(additive.region_rules)) {
        regions.add(key as RegionCode);
      }
    }
    return Array.from(regions);
  }

  findByCode(code: string): AdditiveRecord | undefined {
    return this.codeIndex.get(normalize(code));
  }

  matchToken(token: Token, options: LookupOptions = {}): LookupMatch | undefined {
    if (token.canonical) {
      const record = this.codeIndex.get(token.canonical);
      if (record) {
        return {
          record,
          matchedAlias: token.canonical,
          method: 'code',
          token,
          confidence: Math.min(1, token.confidence + 0.05)
        };
      }
    }

    const normalizedRaw = normalize(token.raw);
    const exactCode = this.aliasIndex.get(normalizedRaw);
    if (exactCode) {
      const record = this.codeIndex.get(exactCode);
      if (record) {
        return {
          record,
          matchedAlias: normalizedRaw,
          method: 'alias',
          token,
          confidence: Math.min(1, token.confidence + 0.1)
        };
      }
    }

    if (options.allowFuzzy) {
      for (const [alias, code] of this.aliasIndex.entries()) {
        if (looksLike(alias, normalizedRaw)) {
          const record = this.codeIndex.get(code);
          if (record) {
            return {
              record,
              matchedAlias: alias,
              method: 'fuzzy',
              token,
              confidence: Math.min(1, token.confidence * 0.8)
            };
          }
        }
      }
    }

    return undefined;
  }

  lookup(tokens: Token[], options: LookupOptions = {}): LookupResult {
    const matchesMap = new Map<string, LookupMatch>();
    const unresolved: Token[] = [];

    for (const token of tokens) {
      const match = this.matchToken(token, options);
      if (match) {
        const existing = matchesMap.get(match.record.code);
        if (!existing || existing.confidence < match.confidence) {
          matchesMap.set(match.record.code, match);
        }
      } else if (token.type !== 'other') {
        unresolved.push(token);
      }
    }

    return { matches: Array.from(matchesMap.values()), unresolved };
  }
}

export function loadPackFromRoot(rootDir: string): AdditiveStore {
  const filePath = path.join(rootDir, 'etl', 'output', 'payload.json');
  return AdditiveStore.fromFile(filePath);
}
