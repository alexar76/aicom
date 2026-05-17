/** Structured failure report from Admin Pipeline API (`failure_report` field). */

export type PipelineFailureReport = {
  headline: string;
  product_state: string;
  cause_plain: string;
  failed_agent?: string | null;
  failed_stage?: string;
  failure_reason?: string | null;
  technical_errors: string[];
  repair_round?: number | null;
  pm_spec_requeue_count?: number | null;
  suggested_recovery: {
    agent_type: string;
    target_state: string;
  };
  operator_hint: string;
  /** Queue/restart false FAILED — not a real agent failure at failed_stage. */
  false_failed?: boolean;
};
