export type RegionCode = 'EU' | 'US';

export interface DietaryFlags {
  vegan: boolean;
  vegetarian: boolean;
  kosher: boolean;
  halal: boolean;
}

export interface SourceFlags {
  animal: boolean;
  insect: boolean;
  plant: boolean;
  synthetic: boolean;
}

export type PopulationCondition =
  | 'child'
  | 'pku'
  | 'sulfites'
  | 'caffeine'
  | 'aspartame'
  | 'shellfish';

export interface Reference {
  id: string;
  label: string;
  url: string;
}

export interface BaseRule {
  id: string;
  summary: string;
  audience?: string[];
  referenceIds: string[];
}

export interface RegulatoryWarningRule extends BaseRule {
  type: 'regulatory_warning';
}

export interface RegionApprovalRule extends BaseRule {
  type: 'region_approval';
  approved: boolean;
}

export interface PopulationCautionRule extends BaseRule {
  type: 'population_caution';
  condition: PopulationCondition;
  severity: 'red' | 'yellow';
}

export interface DietConflictRule extends BaseRule {
  type: 'diet_conflict';
  diet: keyof DietaryFlags;
}

export interface EvidenceAnnotationRule extends BaseRule {
  type: 'evidence_annotation';
  severity: 'yellow';
}

export type RegionRule =
  | RegulatoryWarningRule
  | RegionApprovalRule
  | PopulationCautionRule
  | DietConflictRule
  | EvidenceAnnotationRule;

export interface AdditiveRecord {
  code: string;
  names: string[];
  class: string;
  evidence_level: 'Regulatory' | 'Consensus' | 'Limited';
  plain_summary: string;
  dietary: DietaryFlags;
  source: SourceFlags;
  population_cautions: PopulationCautionRule[];
  region_rules: Partial<Record<RegionCode, RegionRule[]>>;
  references: Reference[];
}

export interface AdditivePack {
  version: string;
  checksum: string;
  generated_at: string;
  additives: AdditiveRecord[];
  alias_index: Record<string, string>;
}
