import { looksLike, normalize, parseIngredients } from './parser';

describe('normalize', () => {
  it('strips diacritics and normalizes whitespace', () => {
    const input = '  Cáñdy   E 1 2 0  ';
    expect(normalize(input)).toBe('CANDY E 1 2 0');
  });
});

describe('parseIngredients', () => {
  it('detects E-codes and synonyms', () => {
    const text = 'Sugar, Tartrazine (E102), Allura Red E129, Citric Acid (E330)';
    const tokens = parseIngredients(text);
    const codes = tokens.filter((t) => t.canonical).map((t) => t.canonical);
    expect(codes).toEqual(expect.arrayContaining(['E102', 'E129', 'E330']));
  });

  it('extracts function hints', () => {
    const text = 'Preservative: INS 220 (Sodium Sulfite)';
    const tokens = parseIngredients(text);
    expect(tokens[0].hints).toContain('PRESERVATIVE');
  });
});

describe('looksLike', () => {
  it('handles OCR slips gracefully', () => {
    expect(looksLike('E102', 'E1O2')).toBe(true);
    expect(looksLike('TARTRAZINE', 'TARTRAZlNE')).toBe(true);
    expect(looksLike('TARTRAZINE', 'CITRIC')).toBe(false);
  });
});
