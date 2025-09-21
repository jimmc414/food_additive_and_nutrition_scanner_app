import path from 'path';

import { AdditiveStore } from '../data/additiveStore';
import { parseIngredients } from '../data/parser';
import { runRiskEngine, UserPreferences } from './engine';

const fixturePath = path.join(__dirname, '..', 'data', '__fixtures__', 'pack.json');
const store = AdditiveStore.fromFile(fixturePath);

function basePrefs(region: 'EU' | 'US'): UserPreferences {
  return {
    region,
    diet: { vegan: false, vegetarian: false, kosher: false, halal: false },
    sensitivities: { pku: false, sulfites: false, caffeine: false, aspartame: false, shellfish: false },
    childMode: false
  };
}

describe('runRiskEngine', () => {
  it('flags EU azo dyes as RED when child mode active', () => {
    const tokens = parseIngredients('Tartrazine (E102)');
    const matches = store.lookup(tokens).matches;
    const prefs = basePrefs('EU');
    prefs.childMode = true;
    const result = runRiskEngine(matches, prefs);
    expect(result.items[0].badge).toBe('RED');
    expect(result.flaggedCount).toBe(1);
  });

  it('marks diet conflicts as yellow for vegan preference', () => {
    const tokens = parseIngredients('Ingredients: Carmine');
    const matches = store.lookup(tokens).matches;
    const prefs = basePrefs('US');
    prefs.diet.vegan = true;
    const result = runRiskEngine(matches, prefs);
    expect(result.items[0].badge).toBe('YELLOW');
    expect(result.items[0].reasons.some((r) => r.includes('Not suitable'))).toBe(true);
  });

  it('produces product summary counts', () => {
    const tokens = parseIngredients('Sugar, Tartrazine (E102), Carmine, Citric Acid (E330)');
    const matches = store.lookup(tokens, { allowFuzzy: true }).matches;
    const prefs = basePrefs('EU');
    prefs.childMode = true;
    prefs.diet.vegan = true;
    const result = runRiskEngine(matches, prefs);
    expect(result.flaggedCount).toBe(1);
    expect(result.cautionCount).toBe(2); // Carmine vegan conflict + citric evidence annotation
    expect(result.neutralCount).toBe(0);
  });
});
