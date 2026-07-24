'use client';

import { useEffect, useState } from 'react';
import { Palette } from 'lucide-react';
import { fetchLandingStylePresets, type LandingStylePreset } from '@/lib/landingStylePresets';

type Props = {
  value: string;
  onChange: (presetId: string) => void;
  autoLabel: string;
  label: string;
  hint?: string;
  className?: string;
  selectClassName?: string;
  disabled?: boolean;
};

export function LandingStylePresetPicker({
  value,
  onChange,
  autoLabel,
  label,
  hint,
  className = '',
  selectClassName = 'input-glass',
  disabled = false,
}: Props) {
  const [presets, setPresets] = useState<LandingStylePreset[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchLandingStylePresets()
      .then((items) => {
        if (!cancelled) setPresets(items);
      })
      .catch(() => {
        if (!cancelled) setLoadError('Presets unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className={className}>
      <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-300">
        <Palette className="h-4 w-4 text-fuchsia-400" />
        {label}
      </label>
      <select
        value={value}
        disabled={disabled || !!loadError}
        onChange={(e) => onChange(e.target.value)}
        className={selectClassName}
      >
        <option value="">{autoLabel}</option>
        {presets.map((p) => (
          <option key={p.id} value={p.id}>
            {p.title}
          </option>
        ))}
      </select>
      {hint ? <p className="mt-2 text-xs text-gray-500 leading-relaxed">{hint}</p> : null}
      {loadError ? <p className="mt-1 text-xs text-amber-400/90">{loadError}</p> : null}
    </div>
  );
}
