/**
 * Response types mirroring the Hermes API (api/main.py, shared/models.py,
 * shared/read_models.py). This file is the ONLY place response shapes are declared.
 * The UI renders these values; it never recomputes scores, contributions or ranks.
 */

export type Role = "employee" | "manager" | "admin";

export type DataClassification = "synthetic" | "real" | null;

export type Session = { sub: string; roles: Role[]; coded_identity: string | null; data_classification: DataClassification };

export type ApiErrorBody = { detail?: unknown; error?: string };

export type SkillSummaryRow = {
  skill_id: string;
  name: string;
  description: string;
  domain_id: string;
  domain_name: string;
  relations: string[];
};

export type RoleProfile = {
  role_id: string;
  role_name: string;
  required_skills: Record<string, number>;
  critical_skills: string[];
  min_coverage_ratio: number;
};

export type DomainStat = {
  domain_id: string;
  name: string;
  skill_count: number;
  skill_records: number;
  identities_with_evidence: number;
  coverage_ratio: number | null;
  mean_level: number | null;
  mean_confidence: number | null;
  mean_freshness: number | null;
};

export type Overview = {
  people: number;
  identities_with_evidence: number;
  skill_coverage_ratio: number | null;
  demonstrated_coverage: { pilot_size: number; with_demonstrated: number; coverage_pct: number };
  governed_skills: number;
  skill_records: number;
  role_profiles: number;
  requests_by_status: Record<string, number>;
  domains: DomainStat[];
  recent_activity: { seq: number; event_type: string; created_at: string }[];
  scoring_config_version: string;
  latest_computation_run_id: string | null;
  audit_chain_verified: boolean;
  data_classification: DataClassification;
};

export type WorkforceSkill = {
  skill_id: string;
  skill_name: string;
  domain_id: string;
  proficiency: number;
  confidence: number;
  freshness: number;
  volume_score: number;
};

export type WorkforceIdentity = {
  coded_identity: string;
  skill_count: number;
  domains: string[];
  primary_domain: string | null;
  mean_confidence: number | null;
  mean_freshness: number | null;
  max_level: number | null;
  skills: WorkforceSkill[];
};

export type Workforce = { identities: WorkforceIdentity[]; domains: { domain_id: string; name: string }[] };

export type SkillDetail = {
  skill_id: string;
  name: string;
  description: string;
  domain_id: string;
  domain_name: string;
  decay_class: string | null;
  effective_half_life_days: number | null;
  proficiency_levels: { level: number; label: string; definition: string }[];
  workforce_size: number;
  identities_with_evidence: number;
  coverage_ratio: number | null;
  level_distribution: Record<string, number>;
  mean_level: number | null;
  mean_confidence: number | null;
  mean_freshness: number | null;
  holders: { coded_identity: string; proficiency: number; confidence: number; freshness: number; volume_score: number }[];
  related_skills: { skill_id: string; name: string; identities_with_evidence: number }[];
};

export type Dashboard = {
  coverage: { pilot_size: number; with_demonstrated: number; coverage_pct: number };
  avg_freshness_by_skill: Record<string, number>;
  skill_distribution: {
    coded_identity: string;
    skill_id: string;
    proficiency: number;
    confidence: number;
    freshness: number;
    volume_score: number;
  }[];
};

/** Per-skill calculation trace (shared/models.py SkillContribution). */
export type SkillContribution = {
  skill_id: string;
  status: "matched" | "adjacent" | "missing";
  required_level: number | null;
  actual_level: number | null;
  level_ratio: number | null;
  confidence: number | null;
  volume_score: number | null;
  freshness: number | null;
  decay_class: string | null;
  half_life_days: number | null;
  adjacency_discount: number;
  adjacency_source_skill: string | null;
  contribution: number | null;
  evidence_ids: string[];
  source_refs: string[];
};

/** Candidate-level envelope (shared/models.py CalculationDetail). */
export type CalculationDetail = {
  required_skill_count: number;
  matched_skill_count: number;
  coverage_ratio: number;
  min_coverage_ratio: number;
  contribution_sum: number;
  mean_contribution: number;
  allocation: number;
  allocation_weight: number;
  allocation_multiplier: number;
  fitness_score: number;
  excluded: boolean;
  exclusion_reason: string | null;
  scoring_config_version: string;
  computation_run_id: string;
  formula: string;
};

export type RankedCandidate = {
  coded_identity: string;
  fitness_score: number;
  rank: number;
  per_skill_reasoning: Record<string, string>;
  reasoning_detail: Record<string, SkillContribution>;
  calculation: CalculationDetail | null;
  evidence_ids: string[];
};

export type ExcludedCandidate = { coded_identity: string; reason: string };

export type FitnessResult = {
  request_id: string;
  candidates: RankedCandidate[];
  scoring_config_version: string;
  computed_at: string;
  computation_run_id: string;
  excluded_candidates: ExcludedCandidate[];
};

export type RequestSummary = {
  request_id: string;
  owner: string;
  status: "open" | "accepted" | "rejected" | "overridden";
  created_at: string | null;
  requirements: {
    required_skills?: Record<string, number>;
    critical_skills?: string[];
    min_coverage_ratio?: number | null;
    shortlist_size?: number;
  };
  candidate_count: number;
  excluded_count: number;
  decision: {
    status: string | null;
    approved_by: string | null;
    decided_at: string | null;
    chosen_coded_identity: string | null;
    engine_rank_of_choice: number | null;
  };
  scoring_config_version: string | null;
  computation_run_id: string | null;
};

export type RequestDetail = RequestSummary & { result: FitnessResult };

export type RankBody = {
  request_id: string;
  required_skills: Record<string, number>;
  critical_skills?: string[];
  min_coverage_ratio?: number;
  shortlist_size?: number;
  /** When set, the server enforces the stored role's critical skills and coverage floor. */
  role_id?: string;
};

export type DecisionStatus = "accepted" | "rejected" | "overridden";

/** Owner and approver are NEVER part of this body — the server derives them. */
export type DecisionBody = {
  status: DecisionStatus;
  chosen_coded_identity?: string;
  rejection_reason?: string;
  override_note?: string;
};

export type ResolvedIdentity = { coded_identity: string; display_name: string; rank: string; fitness_score: string };

export type GapItem = {
  skill_id: string;
  required_level: number;
  current_level: number | null;
  demand_impact: number;
  reasoning: string;
  evidence_ids: string[];
};

export type GapResult = { coded_identity: string; role_id: string; gaps: GapItem[]; scoring_config_version: string };

export type MeResult = {
  coded_identity: string;
  skills: {
    skill_id: string;
    proficiency: number;
    confidence: number;
    freshness: number;
    volume_score: number;
    evidence_ids: string[];
    computation_run_id: string;
    scoring_config_version: string;
  }[];
  evidence: {
    evidence_id: string;
    skill_id: string;
    evidence_type: string;
    source_ref: string;
    occurred_at: string;
  }[];
};

/** GET /api/data-quality — aggregate pipeline state. Never names, raw rows or client labels. */
export type DataQuality = {
  data_classification: DataClassification;
  canonical_skills: number;
  ingestion: null | {
    run_id: string;
    source_name: string;
    ingested_at: string;
    sheets: number | null;
    people_detected: number | null;
    cells_processed: number | null;
    cells_accepted: number | null;
    cells_rejected: number | null;
    accepted_skill_cells: number | null;
    accepted_account_cells: number | null;
    rejections_by_reason: Record<string, number>;
    labels: {
      skill_labels: number | null;
      mapped: number | null;
      pending: number | null;
      rejected: { client_account?: number; soft_skill?: number; culture_fit?: number };
      mapped_trace: { label: string; skill_id: string; mapped_by: string; match_confidence: number }[];
    };
    excluded_field_occurrences: Record<string, number>;
    certificates: {
      cells?: number;
      people?: number;
      distinct_labels?: number;
      classification?: Record<string, number>;
    };
  };
  database: Record<string, number>;
  baseline_level_distribution: Record<string, number>;
  certificates: { staged: number; exact_mapped: number; pending: number; with_earned_at: number; promoted: number };
  pipeline: { imported: number; validated: number | null; mapped: number | null; pending: number | null; scored: number };
};

/** GET /api/identity/directory — synthetic overlay only. Never added to workforce/dashboard. */
export type DirectoryPerson = { coded_identity: string; display_name: string };
export type IdentityDirectory = { people: DirectoryPerson[] };

/** GET /api/team/skill-review/{coded_identity} */
export type SkillReviewRow = {
  skill_id: string;
  proficiency: number;
  confidence: number;
  freshness: number;
  volume_score: number;
  sources: string[];
};

export type OpenContest = {
  contest_id: string;
  coded_identity: string;
  skill_id: string | null;
  reason: string;
  status: string;
  created_at: string;
};

export type SkillReview = {
  coded_identity: string;
  matrix: SkillReviewRow[];
  contests: OpenContest[];
};

export type SurveyCell = {
  coded_identity: string;
  skill_id: string;
  raw_label: string;
  level: number;
  source_sheet: string;
};

export type SurveyMatrix = {
  kind: "survey_2025";
  used_for_fitness: boolean;
  label: string;
  cells: SurveyCell[];
};

export type TaxonomyPendingRow = {
  alias_label: string;
  skill_id: string;
  mapped_by: string;
  proposed_skill_id: string;
};

export type TaxonomyPending = { pending: TaxonomyPendingRow[] };

export type ExcelSunset = {
  survey_year_frozen: number;
  next_workbook_year_forbidden: number;
  next_workbook_allowed: boolean;
  ready_to_retire_excel: boolean;
  criteria: {
    survey_frozen: boolean;
    pilot_coverage_pct: number;
    pilot_coverage_met: boolean;
    baseline_agreement_overlaps: number;
    baseline_agreement_met: boolean;
    staffing_decisions: number;
    staffing_decision_met: boolean;
  };
};

