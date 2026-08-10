export type AnalysisStatus = "pending" | "running" | "done" | "failed";

export type CriterionScore = 0 | 1 | 2 | "N/A";

export type OverallLevel = "низкий" | "средний" | "высокий";

export type BacklogPriority = "высокий" | "средний" | "низкий";

export interface CriterionResult {
  id: string;
  score: CriterionScore;
  justification: string;
  recommendation: string | null;
}

export interface BlockResult {
  block_id: string;
  block_name: string;
  score: number | null;
  what_is_wrong: string;
  why_it_matters: string;
  criteria: CriterionResult[];
}

export interface ProblemItem {
  description: string;
  location: string;
}

export interface BacklogItem {
  task: string;
  zone: string;
  priority: BacklogPriority;
  expected_effect: string;
}

export interface OverallAssessment {
  score: number;
  level: OverallLevel;
  summary: string;
  applicable_count: number;
  na_count: number;
}

export interface AgentResult {
  overall: OverallAssessment;
  blocks: BlockResult[];
  problems: ProblemItem[];
  backlog: BacklogItem[];
}

export interface AnalysisCreateResponse {
  id: string;
  status: AnalysisStatus;
}

export interface AnalysisStatusResponse {
  id: string;
  url: string;
  status: AnalysisStatus;
  result: AgentResult | null;
  error_message: string | null;
}
