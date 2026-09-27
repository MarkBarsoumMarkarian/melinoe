export type Severity = "blocker" | "high" | "medium" | "low" | "info";

export interface Patient {
  id: string;
  diagnosis?: string;
  sex?: string;
  age_at_diagnosis?: number;
  metadata: Record<string, unknown>;
}

export interface Specimen {
  id: string;
  patient_id: string;
  tissue_type: string;
  disease_status?: string;
}

export interface Assay {
  id: string;
  specimen_id: string;
  modality: string;
  platform?: string;
  batch?: string;
  data_path: string;
  file_sha256?: string;
}

export interface Endpoint {
  id: string;
  patient_id: string;
  endpoint_type: string;
  time?: number;
  event?: boolean;
  time_unit?: string;
}

export interface ProjectManifest {
  project_id: string;
  title: string;
  disease_context: string;
  description?: string;
  data_sensitivity: string;
  objective: {
    question: string;
    analysis_type: string;
    primary_outcome?: string;
    unit_of_analysis: string;
    validation_strategy: string;
    intended_claim_level: string;
  };
  patients: Patient[];
  specimens: Specimen[];
  assays: Assay[];
  endpoints: Endpoint[];
  splits: Array<{ patient_id: string; role: string; cohort?: string }>;
  settings: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface Finding {
  code: string;
  title: string;
  severity: Severity;
  message: string;
  evidence: string[];
  remediation: string;
  affected_entities: string[];
}

export interface AuditReport {
  project_id: string;
  engine_version: string;
  generated_at: string;
  summary: {
    score: number;
    status: string;
    finding_counts: Record<Severity, number>;
    patient_count: number;
    specimen_count: number;
    assay_count: number;
    modality_count: number;
  };
  findings: Finding[];
  rule_codes_executed: string[];
}

export interface ProjectPolicy {
  sensitivity: string;
  encryption_required: boolean;
  network: "deny" | "knowledge_only" | "allow";
  export: "capsule_only" | "deidentified_only" | "allow";
  source_data_in_capsules: boolean;
  direct_identifiers_allowed: boolean;
  locked_test_labels_hidden_during_training: boolean;
  rationale: string[];
}

export interface ToolCapability {
  available: boolean;
  path?: string;
  version?: string;
  operational?: boolean;
  detail?: string;
}

export interface SystemProfile {
  os: string;
  kernel: string;
  compute: {
    architecture: string;
    cpu_model: string;
    logical_cpus: number;
    memory_bytes: number;
    disk_free_bytes: number;
    gpu?: string;
    gpu_memory_bytes?: number;
    recommended_tier: string;
  };
  capabilities: Record<string, ToolCapability>;
  offline_execution_ready: boolean;
  encrypted_vault_ready: boolean;
}

export interface WorkflowValidationSummary {
  benchmark_id: string;
  evidence_path: string;
  independent_cohorts: number;
  patients: number;
  events: number;
  last_validated: string;
  status: string;
  claim_boundary: string;
}

export interface WorkflowSpec {
  id: string;
  version: string;
  title: string;
  summary: string;
  maturity: "design_contract" | "validated";
  validation?: WorkflowValidationSummary;
}

export interface WorkflowValidationReceipt {
  workflow_id: string;
  workflow_version: string;
  benchmark_id: string;
  validation_status: string;
  validated_at: string;
  execution_engine: string;
  patients: number;
  events: number;
  cohorts: number;
  metrics: Array<{ name: string; observed: number; passed: boolean }>;
  claim_boundary: string;
}
