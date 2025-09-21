import path from 'path';

import { parseIngredients } from './parser';
import { AdditiveStore } from './additiveStore';

describe('AdditiveStore', () => {
  const fixturePath = path.join(__dirname, '__fixtures__', 'pack.json');
  const store = AdditiveStore.fromFile(fixturePath);

  it('loads version information', () => {
    expect(store.version).toBe('2025.09.01');
  });

  it('matches E-codes directly', () => {
    const tokens = parseIngredients('Contains E102 and E330');
    const result = store.lookup(tokens);
    const codes = result.matches.map((m) => m.record.code).sort();
    expect(codes).toEqual(['E102', 'E330']);
  });

  it('matches aliases when no E-code present', () => {
    const tokens = parseIngredients('Ingredients: sugar, Carmine, water');
    const result = store.lookup(tokens);
    expect(result.matches[0].record.code).toBe('E120');
    expect(result.matches[0].method).toBe('alias');
  });

  it('supports fuzzy matching when enabled', () => {
    const tokens = parseIngredients('Contains TARTRAZlNE');
    const result = store.lookup(tokens, { allowFuzzy: true });
    expect(result.matches[0].record.code).toBe('E102');
    expect(result.matches[0].method).toBe('fuzzy');
  });
});
