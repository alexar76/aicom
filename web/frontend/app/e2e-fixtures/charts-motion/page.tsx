'use client';

import { motion } from 'framer-motion';
import { PipelineProductVitalsCharts } from '@/components/admin/pipeline/PipelineProductVitalsCharts';

/** Playwright fixture — React 19 + recharts + framer-motion smoke surface. */
const MOCK_PRODUCT = {
  id: 'e2e-fixture',
  state: 'COMPLETED',
  economics: {
    llm_agent_breakdown: {
      analyst: { cost_usd: 1.25 },
      developer: { cost_usd: 0.85 },
      qa: { cost_usd: 0.4 },
    },
    cost_cap_usd: 5,
    total_cost_usd: 2.5,
    quality_score: 0.88,
  },
  task_counts: { total: 12, completed: 11, running: 0, failed: 0 },
  spec: { product_name: 'E2E Fixture Product' },
};

export default function ChartsMotionE2EPage() {
  return (
    <main className="min-h-screen bg-[#0a0f1a] p-6 text-white">
      <motion.h1
        data-testid="motion-hero"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="text-xl font-semibold mb-4"
      >
        React 19 charts + motion fixture
      </motion.h1>
      <div data-testid="vitals-charts" className="min-h-[420px] w-full max-w-3xl">
        <PipelineProductVitalsCharts product={MOCK_PRODUCT} locale="en" />
      </div>
    </main>
  );
}
