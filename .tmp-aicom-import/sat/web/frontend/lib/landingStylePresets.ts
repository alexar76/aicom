/** Shared landing style preset types + fetch helper. */

export type LandingStylePreset = {
  id: string;
  title: string;
};

export type LandingPresetsResponse = {
  presets: LandingStylePreset[];
  count: number;
};

let cachedPresets: LandingStylePreset[] | null = null;

export async function fetchLandingStylePresets(): Promise<LandingStylePreset[]> {
  if (cachedPresets) return cachedPresets;
  const res = await fetch('/api/public/landing-presets', { cache: 'force-cache' });
  if (!res.ok) throw new Error('Could not load style presets');
  const data = (await res.json()) as LandingPresetsResponse;
  cachedPresets = Array.isArray(data.presets) ? data.presets : [];
  return cachedPresets;
}
