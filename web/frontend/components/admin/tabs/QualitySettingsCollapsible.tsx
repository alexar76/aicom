'use client';

import React from 'react';
import { ChevronDown, SlidersHorizontal } from 'lucide-react';

export type QualitySettingsState = {
  max_pipeline_repair_rounds: number;
  demo_quality_min_score: number;
  strict_demo_gates: boolean;
  visual_quality_gate: boolean;
  visual_quality_strict: boolean;
  visual_quality_app_checks: boolean;
  browser_e2e_enabled: boolean;
  browser_max_pages: number;
  browser_max_depth: number;
  marketplace_quality_gate: boolean;
  marketplace_require_full_qa: boolean;
  marketplace_min_spec_coverage: number;
  marketplace_require_design_novelty: boolean;
  marketplace_min_design_novelty: number;
  marketplace_require_qa_realism: boolean;
  marketplace_require_release_score: boolean;
  marketplace_min_release_score: number;
  marketplace_require_non_placeholder_name: boolean;
  marketplace_require_methodology: boolean;
  marketplace_require_quality_constitution: boolean;
  marketplace_require_release_cockpit: boolean;
  quality_constitution_pipeline_enabled: boolean;
};

export const DEFAULT_QUALITY_SETTINGS: QualitySettingsState = {
  max_pipeline_repair_rounds: 25,
  demo_quality_min_score: 55,
  strict_demo_gates: true,
  visual_quality_gate: true,
  visual_quality_strict: false,
  visual_quality_app_checks: true,
  browser_e2e_enabled: true,
  browser_max_pages: 100,
  browser_max_depth: 10,
  marketplace_quality_gate: true,
  marketplace_require_full_qa: false,
  marketplace_min_spec_coverage: 15,
  marketplace_require_design_novelty: true,
  marketplace_min_design_novelty: 0.18,
  marketplace_require_qa_realism: true,
  marketplace_require_release_score: true,
  marketplace_min_release_score: 70,
  marketplace_require_non_placeholder_name: true,
  marketplace_require_methodology: true,
  marketplace_require_quality_constitution: false,
  marketplace_require_release_cockpit: false,
  quality_constitution_pipeline_enabled: true,
};

type Props = {
  open: boolean;
  onToggle: () => void;
  quality: QualitySettingsState;
  onChange: <K extends keyof QualitySettingsState>(key: K, value: QualitySettingsState[K]) => void;
  disabled: boolean;
};

function ToggleRow(props: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled: boolean;
}) {
  const { label, description, checked, onChange, disabled } = props;
  return (
    <label className="flex cursor-pointer flex-col gap-2 rounded-lg bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-white">{label}</div>
        <p className="mt-0.5 text-xs leading-relaxed text-gray-400">{description}</p>
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-12 shrink-0 rounded-full transition-colors ${
          checked ? 'bg-indigo-500' : 'bg-white/20'
        } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
      >
        <span
          className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-0'
          }`}
        />
      </button>
    </label>
  );
}

function NumberRow(props: {
  label: string;
  description: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  disabled: boolean;
}) {
  const { label, description, value, min, max, step = 1, onChange, disabled } = props;
  return (
    <div className="rounded-lg bg-white/5 p-3">
      <label className="text-sm font-medium text-white">{label}</label>
      <p className="mt-0.5 text-xs leading-relaxed text-gray-400">{description}</p>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        value={Number.isFinite(value) ? value : min}
        onChange={(e) => {
          const n = parseFloat(e.target.value);
          if (!Number.isFinite(n)) return;
          onChange(Math.min(max, Math.max(min, n)));
        }}
        className="mt-2 w-full max-w-xs rounded-lg border border-white/10 bg-white/10 px-3 py-1.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none disabled:opacity-50"
      />
    </div>
  );
}

export function QualitySettingsCollapsible({ open, onToggle, quality, onChange, disabled }: Props) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03]">
      <button
        type="button"
        onClick={onToggle}
        disabled={disabled}
        className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <SlidersHorizontal className="h-5 w-5 shrink-0 text-violet-300" aria-hidden />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-white">Pipeline &amp; product quality</div>
            <p className="text-xs text-gray-500">
              Tune how strict QA, browser checks, and storefront listing are. Saved with{' '}
              <span className="text-gray-400">Save settings</span> below.
            </p>
          </div>
        </div>
        <ChevronDown
          className={`h-5 w-5 shrink-0 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>
      {open && (
        <div className="space-y-5 border-t border-white/10 px-4 pb-4 pt-3">
          <p className="text-xs leading-relaxed text-gray-500">
            Values are stored in platform config under <code className="text-[10px] text-gray-400">quality:</code>.
            If your deployment sets matching <code className="text-[10px] text-gray-400">AIFACTORY_*</code> environment
            variables, those still win for operators who need a hard override in Docker.
          </p>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Repair budget</h4>
            <div className="space-y-3">
              <NumberRow
                label="Max quality repair rounds"
                description="How many times the pipeline can send a product back to Development after QA or marketplace checks fail before the product is marked failed. Higher is more forgiving; lower fails faster."
                value={quality.max_pipeline_repair_rounds}
                min={1}
                max={100}
                onChange={(v) => onChange('max_pipeline_repair_rounds', v)}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Demo &amp; static QA</h4>
            <div className="space-y-3">
              <NumberRow
                label="Minimum demo quality score"
                description="Score (0–100) from the static demo audit. Below this, QA does not let the product advance toward security."
                value={quality.demo_quality_min_score}
                min={0}
                max={100}
                onChange={(v) => onChange('demo_quality_min_score', Math.round(v))}
                disabled={disabled}
              />
              <ToggleRow
                label="Strict demo gates"
                description="When on, additional HTML/link issues (e.g. broken internal links, very thin pages) fail QA even if the headline score is above the minimum."
                checked={quality.strict_demo_gates}
                onChange={(v) => onChange('strict_demo_gates', v)}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Visual heuristics</h4>
            <div className="space-y-3">
              <ToggleRow
                label="Run visual checks"
                description="Static heuristics on HTML/CSS (tokens, skeleton states, basic a11y hints). Usually leave on."
                checked={quality.visual_quality_gate}
                onChange={(v) => onChange('visual_quality_gate', v)}
                disabled={disabled}
              />
              <ToggleRow
                label="Strict visual mode"
                description="When on, a defined set of visual issue codes fails the gate outright (stricter than headline score alone). Use when you want zero tolerance for missing viewport/lang, thin design tokens, etc."
                checked={quality.visual_quality_strict}
                onChange={(v) => onChange('visual_quality_strict', v)}
                disabled={disabled}
              />
              <ToggleRow
                label="App-like surface checks"
                description="For dashboard / full-software style specs, require skeleton, empty, and error UI patterns. Turn off only for pure marketing landings if false positives annoy you."
                checked={quality.visual_quality_app_checks}
                onChange={(v) => onChange('visual_quality_app_checks', v)}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Browser QA (Playwright)</h4>
            <div className="space-y-3">
              <ToggleRow
                label="Run browser E2E during QA"
                description="Headless Chromium crawl of the generated site. Disabling speeds QA up but skips realistic navigation checks."
                checked={quality.browser_e2e_enabled}
                onChange={(v) => onChange('browser_e2e_enabled', v)}
                disabled={disabled}
              />
              <NumberRow
                label="Max pages per crawl"
                description="Safety cap on how many distinct URLs the deep crawl visits. Raise for large sites; lower for faster CI."
                value={quality.browser_max_pages}
                min={1}
                max={500}
                onChange={(v) => onChange('browser_max_pages', Math.round(v))}
                disabled={disabled}
              />
              <NumberRow
                label="Max crawl depth"
                description="Maximum link depth from the start page. Deeper finds more issues but takes longer."
                value={quality.browser_max_depth}
                min={1}
                max={30}
                onChange={(v) => onChange('browser_max_depth', Math.round(v))}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Public storefront listing</h4>
            <div className="space-y-3">
              <ToggleRow
                label="Enable listing quality gate"
                description="When off, every completed product can appear on the public grid (debug only). When on, products must pass the rules below."
                checked={quality.marketplace_quality_gate}
                onChange={(v) => onChange('marketplace_quality_gate', v)}
                disabled={disabled}
              />
              <ToggleRow
                label="Require full QA telemetry"
                description="Require saved browser/QA telemetry with all gates passed before a product may be listed."
                checked={quality.marketplace_require_full_qa}
                onChange={(v) => onChange('marketplace_require_full_qa', v)}
                disabled={disabled}
              />
              <NumberRow
                label="Minimum spec keyword coverage (%)"
                description="When the spec defines measurable keywords, listing requires at least this coverage. Set to 0 to disable this check."
                value={quality.marketplace_min_spec_coverage}
                min={0}
                max={100}
                onChange={(v) => onChange('marketplace_min_spec_coverage', Math.round(v))}
                disabled={disabled}
              />
              <ToggleRow
                label="Require architecture novelty"
                description="When an architecture novelty score exists, it must meet the minimum below."
                checked={quality.marketplace_require_design_novelty}
                onChange={(v) => onChange('marketplace_require_design_novelty', v)}
                disabled={disabled}
              />
              <NumberRow
                label="Minimum design novelty score"
                description="Threshold for architecture novelty (0–1). Only used when a score is present and the requirement above is on."
                value={quality.marketplace_min_design_novelty}
                min={0}
                max={1}
                step={0.01}
                onChange={(v) => onChange('marketplace_min_design_novelty', v)}
                disabled={disabled}
              />
              <ToggleRow
                label="Block high-severity QA realism findings"
                description="When on, backend realism issues reported by QA can block storefront listing."
                checked={quality.marketplace_require_qa_realism}
                onChange={(v) => onChange('marketplace_require_qa_realism', v)}
                disabled={disabled}
              />
              <ToggleRow
                label="Require release score from QA"
                description="When the QA report includes a release score, it must meet the minimum below."
                checked={quality.marketplace_require_release_score}
                onChange={(v) => onChange('marketplace_require_release_score', v)}
                disabled={disabled}
              />
              <NumberRow
                label="Minimum release score"
                description="0–100; used only when a release score exists and the requirement above is enabled."
                value={quality.marketplace_min_release_score}
                min={0}
                max={100}
                onChange={(v) => onChange('marketplace_min_release_score', Math.round(v))}
                disabled={disabled}
              />
              <ToggleRow
                label="Reject placeholder product names"
                description="Blocks obviously generic or spam titles from being listed."
                checked={quality.marketplace_require_non_placeholder_name}
                onChange={(v) => onChange('marketplace_require_non_placeholder_name', v)}
                disabled={disabled}
              />
              <ToggleRow
                label="Require methodology review"
                description="Listing may require methodology pack / review signals to be satisfied."
                checked={quality.marketplace_require_methodology}
                onChange={(v) => onChange('marketplace_require_methodology', v)}
                disabled={disabled}
              />
              <ToggleRow
                label="Require quality constitution (listing)"
                description="Runs the quality constitution gate before allowing listing (stricter orgs)."
                checked={quality.marketplace_require_quality_constitution}
                onChange={(v) => onChange('marketplace_require_quality_constitution', v)}
                disabled={disabled}
              />
              <ToggleRow
                label="Require release cockpit “go”"
                description="When on, the release cockpit must report go before listing."
                checked={quality.marketplace_require_release_cockpit}
                onChange={(v) => onChange('marketplace_require_release_cockpit', v)}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Pipeline constitution</h4>
            <ToggleRow
              label="Quality constitution during pipeline"
              description="When on, runtime guards may attach constitution-based issues before certain stages complete. Disable only for debugging."
              checked={quality.quality_constitution_pipeline_enabled}
              onChange={(v) => onChange('quality_constitution_pipeline_enabled', v)}
              disabled={disabled}
            />
          </div>
        </div>
      )}
    </div>
  );
}
