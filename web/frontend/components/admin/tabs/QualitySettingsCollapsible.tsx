'use client';

import React from 'react';
import { ChevronDown, SlidersHorizontal } from 'lucide-react';
import { type AdminLocale, t } from '@/lib/adminI18n';

export type QualitySettingsState = {
  max_pipeline_cost_usd: number;
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
  max_pipeline_cost_usd: 0,
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
  locale: AdminLocale;
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

export function QualitySettingsCollapsible({ locale, open, onToggle, quality, onChange, disabled }: Props) {
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
            <div className="text-sm font-semibold text-white">{t(locale, 'settings.quality.title')}</div>
            <p className="text-xs text-gray-500">
              {t(locale, 'settings.quality.subtitle')}{' '}
              <span className="text-gray-400">{t(locale, 'settings.quality.subtitleSave')}</span>
              {locale === 'ru' ? ' ниже.' : locale === 'es' ? ' abajo.' : ' below.'}
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
            {t(locale, 'settings.quality.intro')}
          </p>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{t(locale, 'settings.quality.section.repair')}</h4>
            <div className="space-y-3">
              <NumberRow
                label={t(locale, 'settings.quality.maxPipelineCost.label')}
                description={t(locale, 'settings.quality.maxPipelineCost.desc')}
                value={quality.max_pipeline_cost_usd}
                min={0}
                max={100000}
                step={0.5}
                onChange={(v) => onChange('max_pipeline_cost_usd', v)}
                disabled={disabled}
              />
              <NumberRow
                label={t(locale, 'settings.quality.maxRepair.label')}
                description={t(locale, 'settings.quality.maxRepair.desc')}
                value={quality.max_pipeline_repair_rounds}
                min={1}
                max={100}
                onChange={(v) => onChange('max_pipeline_repair_rounds', v)}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
              {t(locale, 'settings.quality.section.demo')}
            </h4>
            <div className="space-y-3">
              <NumberRow
                label={t(locale, 'settings.quality.demoMin.label')}
                description={t(locale, 'settings.quality.demoMin.desc')}
                value={quality.demo_quality_min_score}
                min={0}
                max={100}
                onChange={(v) => onChange('demo_quality_min_score', Math.round(v))}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.strictDemo.label')}
                description={t(locale, 'settings.quality.strictDemo.desc')}
                checked={quality.strict_demo_gates}
                onChange={(v) => onChange('strict_demo_gates', v)}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{t(locale, 'settings.quality.section.visual')}</h4>
            <div className="space-y-3">
              <ToggleRow
                label={t(locale, 'settings.quality.visualRun.label')}
                description={t(locale, 'settings.quality.visualRun.desc')}
                checked={quality.visual_quality_gate}
                onChange={(v) => onChange('visual_quality_gate', v)}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.visualStrict.label')}
                description={t(locale, 'settings.quality.visualStrict.desc')}
                checked={quality.visual_quality_strict}
                onChange={(v) => onChange('visual_quality_strict', v)}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.visualApp.label')}
                description={t(locale, 'settings.quality.visualApp.desc')}
                checked={quality.visual_quality_app_checks}
                onChange={(v) => onChange('visual_quality_app_checks', v)}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{t(locale, 'settings.quality.section.browser')}</h4>
            <div className="space-y-3">
              <ToggleRow
                label={t(locale, 'settings.quality.browserE2e.label')}
                description={t(locale, 'settings.quality.browserE2e.desc')}
                checked={quality.browser_e2e_enabled}
                onChange={(v) => onChange('browser_e2e_enabled', v)}
                disabled={disabled}
              />
              <NumberRow
                label={t(locale, 'settings.quality.browserPages.label')}
                description={t(locale, 'settings.quality.browserPages.desc')}
                value={quality.browser_max_pages}
                min={1}
                max={500}
                onChange={(v) => onChange('browser_max_pages', Math.round(v))}
                disabled={disabled}
              />
              <NumberRow
                label={t(locale, 'settings.quality.browserDepth.label')}
                description={t(locale, 'settings.quality.browserDepth.desc')}
                value={quality.browser_max_depth}
                min={1}
                max={30}
                onChange={(v) => onChange('browser_max_depth', Math.round(v))}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{t(locale, 'settings.quality.section.storefront')}</h4>
            <div className="space-y-3">
              <ToggleRow
                label={t(locale, 'settings.quality.marketGate.label')}
                description={t(locale, 'settings.quality.marketGate.desc')}
                checked={quality.marketplace_quality_gate}
                onChange={(v) => onChange('marketplace_quality_gate', v)}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.fullQa.label')}
                description={t(locale, 'settings.quality.fullQa.desc')}
                checked={quality.marketplace_require_full_qa}
                onChange={(v) => onChange('marketplace_require_full_qa', v)}
                disabled={disabled}
              />
              <NumberRow
                label={t(locale, 'settings.quality.specCoverage.label')}
                description={t(locale, 'settings.quality.specCoverage.desc')}
                value={quality.marketplace_min_spec_coverage}
                min={0}
                max={100}
                onChange={(v) => onChange('marketplace_min_spec_coverage', Math.round(v))}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.designNoveltyReq.label')}
                description={t(locale, 'settings.quality.designNoveltyReq.desc')}
                checked={quality.marketplace_require_design_novelty}
                onChange={(v) => onChange('marketplace_require_design_novelty', v)}
                disabled={disabled}
              />
              <NumberRow
                label={t(locale, 'settings.quality.designNoveltyMin.label')}
                description={t(locale, 'settings.quality.designNoveltyMin.desc')}
                value={quality.marketplace_min_design_novelty}
                min={0}
                max={1}
                step={0.01}
                onChange={(v) => onChange('marketplace_min_design_novelty', v)}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.qaRealism.label')}
                description={t(locale, 'settings.quality.qaRealism.desc')}
                checked={quality.marketplace_require_qa_realism}
                onChange={(v) => onChange('marketplace_require_qa_realism', v)}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.releaseScoreReq.label')}
                description={t(locale, 'settings.quality.releaseScoreReq.desc')}
                checked={quality.marketplace_require_release_score}
                onChange={(v) => onChange('marketplace_require_release_score', v)}
                disabled={disabled}
              />
              <NumberRow
                label={t(locale, 'settings.quality.releaseScoreMin.label')}
                description={t(locale, 'settings.quality.releaseScoreMin.desc')}
                value={quality.marketplace_min_release_score}
                min={0}
                max={100}
                onChange={(v) => onChange('marketplace_min_release_score', Math.round(v))}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.placeholderName.label')}
                description={t(locale, 'settings.quality.placeholderName.desc')}
                checked={quality.marketplace_require_non_placeholder_name}
                onChange={(v) => onChange('marketplace_require_non_placeholder_name', v)}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.methodology.label')}
                description={t(locale, 'settings.quality.methodology.desc')}
                checked={quality.marketplace_require_methodology}
                onChange={(v) => onChange('marketplace_require_methodology', v)}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.constitutionListing.label')}
                description={t(locale, 'settings.quality.constitutionListing.desc')}
                checked={quality.marketplace_require_quality_constitution}
                onChange={(v) => onChange('marketplace_require_quality_constitution', v)}
                disabled={disabled}
              />
              <ToggleRow
                label={t(locale, 'settings.quality.releaseCockpit.label')}
                description={t(locale, 'settings.quality.releaseCockpit.desc')}
                checked={quality.marketplace_require_release_cockpit}
                onChange={(v) => onChange('marketplace_require_release_cockpit', v)}
                disabled={disabled}
              />
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{t(locale, 'settings.quality.section.constitution')}</h4>
            <ToggleRow
              label={t(locale, 'settings.quality.constitutionPipeline.label')}
              description={t(locale, 'settings.quality.constitutionPipeline.desc')}
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
