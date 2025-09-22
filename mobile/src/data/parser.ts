import { distance as levenshtein } from 'fastest-levenshtein';

export type TokenType = 'ecode' | 'name' | 'other';

export interface Token {
  raw: string;
  canonical?: string;
  type: TokenType;
  hints: string[];
  confidence: number;
}

const FUNCTION_WORDS = [
  'COLOUR',
  'COLOR',
  'PRESERVATIVE',
  'ANTIOXIDANT',
  'STABILISER',
  'STABILIZER',
  'THICKENER',
  'EMULSIFIER',
  'ACIDITY REGULATOR',
  'FLAVOUR',
  'FLAVOR',
  'SWEETENER',
  'RAISING AGENT'
];

const LEADING_KEYWORD_PATTERNS = [
  /^(?:INGREDIENTS?|CONTAINS|MAY CONTAIN)[: ]+/,
  /^CONTAINS[: ]+/,
  /^INGREDIENTS?[: ]+/
];

export const REG_E = /\bE\s*0*(\d{3})([A-Z])?\b/gi;
export const REG_INS = /\bINS\s*0*(\d{3})([A-Z])?\b/gi;

export function normalize(input: string): string {
  return input
    .normalize('NFKC')
    .replace(/\u200B/g, '')
    .toUpperCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036F]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractFunctionHints(normalizedToken: string): string[] {
  const hints = new Set<string>();
  for (const word of FUNCTION_WORDS) {
    if (normalizedToken.includes(word)) {
      hints.add(word);
    }
  }
  return Array.from(hints);
}

export function parseIngredients(text: string): Token[] {
  if (!text.trim()) {
    return [];
  }

  const normalized = normalize(text);
  const segments = normalized
    .split(/[(),\\]/)
    .map((segment) => segment.trim())
    .map((segment) => {
      let cleaned = segment;
      for (const pattern of LEADING_KEYWORD_PATTERNS) {
        cleaned = cleaned.replace(pattern, '').trim();
      }
      return cleaned;
    })
    .filter(Boolean);

  const tokens: Token[] = [];

  for (const segment of segments) {
    const hints = extractFunctionHints(segment);
    let matched = false;

    let match: RegExpExecArray | null;
    REG_E.lastIndex = 0;
    while ((match = REG_E.exec(segment)) !== null) {
      const [, digits, suffix] = match;
      const canonical = `E${digits}${suffix ?? ''}`;
      tokens.push({
        raw: segment,
        canonical,
        type: 'ecode',
        hints,
        confidence: 0.95
      });
      matched = true;
    }

    REG_INS.lastIndex = 0;
    while ((match = REG_INS.exec(segment)) !== null) {
      const [, digits, suffix] = match;
      const canonical = `E${digits}${suffix ?? ''}`;
      tokens.push({
        raw: segment,
        canonical,
        type: 'ecode',
        hints,
        confidence: 0.9
      });
      matched = true;
    }

    if (!matched) {
      tokens.push({
        raw: segment,
        type: 'name',
        hints,
        confidence: 0.6
      });
    }
  }

  return tokens;
}

// Helper for OCR slips like 0↔O, 1↔I, S↔5
export function looksLike(additiveName: string, candidate: string): boolean {
  const base = normalize(additiveName);
  const adjusted = normalize(candidate)
    .replace(/O/g, '0')
    .replace(/I/g, '1')
    .replace(/S/g, '5');

  const distance = levenshtein(base, adjusted);
  return distance <= Math.max(1, Math.floor(base.length * 0.15));
}
