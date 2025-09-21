import { LookupMatch, MatchMethod } from '../data/additiveStore';
import { AdditiveRecord, DietaryFlags, PopulationCautionRule, RegionCode, Reference } from '../data/types';

export type RiskBadge = 'GREEN' | 'YELLOW' | 'RED';

export interface SensitivityPrefs {
  pku: boolean;
  sulfites: boolean;
  caffeine: boolean;
  aspartame: boolean;
  shellfish: boolean;
}

export interface UserPreferences {
  region: RegionCode;
  diet: DietaryFlags;
  sensitivities: SensitivityPrefs;
  childMode: boolean;
}

export interface AdditiveRiskItem {
  code: string;
  name: string;
  badge: RiskBadge;
  plainSummary: string;
  matchedAlias: string;
  method: MatchMethod;
  confidence: number;
  hints: string[];
  reasons: string[];
  ruleIds: string[];
  references: Reference[];
  audiences: string[];
  dietary: DietaryFlags;
}

export interface RiskEngineResult {
  region: RegionCode;
  flaggedCount: number;
  cautionCount: number;
  neutralCount: number;
  items: AdditiveRiskItem[];
}

const BADGE_ORDER: Record<RiskBadge, number> = {
  GREEN: 0,
  YELLOW: 1,
  RED: 2
};

const DIET_REFERENCE: Reference = {
  id: 'DIETARY_FLAGS',
  label: 'Dietary flags from pack',
  url: ''
};

function shouldApplyPopulationRule(rule: PopulationCautionRule, prefs: UserPreferences): boolean {
  switch (rule.condition) {
    case 'child':
      return prefs.childMode;
    case 'pku':
      return prefs.sensitivities.pku;
    case 'sulfites':
      return prefs.sensitivities.sulfites;
    case 'caffeine':
      return prefs.sensitivities.caffeine;
    case 'aspartame':
      return prefs.sensitivities.aspartame;
    case 'shellfish':
      return prefs.sensitivities.shellfish;
    default:
      return false;
  }
}

function aggregateReferences(record: AdditiveRecord, referenceIds: string[], set: Set<Reference>): void {
  for (const id of referenceIds) {
    const reference = record.references.find((ref) => ref.id === id);
    if (reference) {
      set.add(reference);
    }
  }
}

function applyDietConflicts(record: AdditiveRecord, prefs: UserPreferences, dietRules: Set<keyof DietaryFlags>, reasons: string[], ruleIds: string[], audiences: Set<string>, references: Set<Reference>): RiskBadge | null {
  let triggered: RiskBadge | null = null;
  for (const diet of Object.keys(prefs.diet) as (keyof DietaryFlags)[]) {
    if (prefs.diet[diet] && !record.dietary[diet] && !dietRules.has(diet)) {
      reasons.push(`Not suitable for ${diet} preference.`);
      ruleIds.push(`dietary-${diet}`);
      audiences.add(diet.charAt(0).toUpperCase() + diet.slice(1));
      triggered = 'YELLOW';
    }
  }

  if (triggered === 'YELLOW') {
    references.add(DIET_REFERENCE);
  }

  return triggered;
}

function evaluateRecord(match: LookupMatch, prefs: UserPreferences): AdditiveRiskItem {
  const { record, token } = match;
  const reasons: string[] = [];
  const ruleIds: string[] = [];
  const audiences = new Set<string>();
  const references = new Set<Reference>();

  let badge: RiskBadge = 'GREEN';

  const applyBadge = (next: RiskBadge) => {
    if (BADGE_ORDER[next] > BADGE_ORDER[badge]) {
      badge = next;
    }
  };

  const regionRules = record.region_rules[prefs.region] ?? [];
  const triggeredDietRules = new Set<keyof DietaryFlags>();

  for (const rule of regionRules) {
    ruleIds.push(rule.id);
    if (rule.audience) {
      for (const audience of rule.audience) {
        audiences.add(audience);
      }
    }
    aggregateReferences(record, rule.referenceIds, references);

    switch (rule.type) {
      case 'regulatory_warning':
        reasons.push(rule.summary);
        applyBadge('RED');
        break;
      case 'population_caution':
        if (shouldApplyPopulationRule(rule, prefs)) {
          reasons.push(rule.summary);
          applyBadge(rule.severity === 'red' ? 'RED' : 'YELLOW');
        }
        break;
      case 'diet_conflict':
        triggeredDietRules.add(rule.diet);
        if (prefs.diet[rule.diet]) {
          reasons.push(rule.summary);
          audiences.add(rule.diet.charAt(0).toUpperCase() + rule.diet.slice(1));
          applyBadge('YELLOW');
        }
        break;
      case 'evidence_annotation':
        reasons.push(rule.summary);
        applyBadge('YELLOW');
        break;
      case 'region_approval':
        reasons.push(rule.summary);
        break;
      default:
        break;
    }
  }

  for (const caution of record.population_cautions) {
    if (shouldApplyPopulationRule(caution, prefs)) {
      ruleIds.push(caution.id);
      reasons.push(caution.summary);
      if (caution.audience) {
        for (const audience of caution.audience) {
          audiences.add(audience);
        }
      }
      aggregateReferences(record, caution.referenceIds, references);
      applyBadge(caution.severity === 'red' ? 'RED' : 'YELLOW');
    }
  }

  const dietBadge = applyDietConflicts(record, prefs, triggeredDietRules, reasons, ruleIds, audiences, references);
  if (dietBadge) {
    applyBadge(dietBadge);
  }

  const reasonsUnique = Array.from(new Set(reasons));
  const referencesUnique = Array.from(references);
  const audiencesUnique = Array.from(audiences);

  return {
    code: record.code,
    name: record.names[0] ?? record.code,
    badge,
    plainSummary: record.plain_summary,
    matchedAlias: match.matchedAlias,
    method: match.method,
    confidence: match.confidence,
    hints: token.hints,
    reasons: reasonsUnique,
    ruleIds: Array.from(new Set(ruleIds)),
    references: referencesUnique,
    audiences: audiencesUnique,
    dietary: record.dietary
  };
}

export function runRiskEngine(matches: LookupMatch[], prefs: UserPreferences): RiskEngineResult {
  const items = matches.map((match) => evaluateRecord(match, prefs));

  let flaggedCount = 0;
  let cautionCount = 0;
  let neutralCount = 0;

  for (const item of items) {
    if (item.badge === 'RED') {
      flaggedCount += 1;
    } else if (item.badge === 'YELLOW') {
      cautionCount += 1;
    } else {
      neutralCount += 1;
    }
  }

  return {
    region: prefs.region,
    flaggedCount,
    cautionCount,
    neutralCount,
    items
  };
}
