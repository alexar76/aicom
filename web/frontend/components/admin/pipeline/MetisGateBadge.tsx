'use client';

import { Badge } from '@/components/ui/Badge';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';
import { resolveMetisGateBadge, type MetisGatePayload } from '@/lib/metisGateBadge';

type MetisGateBadgeProps = {
  locale: AdminLocale;
  metisGate?: MetisGatePayload | null;
  className?: string;
};

export function MetisGateBadge({ locale, metisGate, className }: MetisGateBadgeProps) {
  const presentation = resolveMetisGateBadge(metisGate);
  const title =
    presentation.titleParts.length > 0
      ? tVars(locale, 'pipeline.metis.tooltip', {
          details: presentation.titleParts.join(' · '),
        })
      : t(locale, presentation.labelKey);

  const label = t(locale, presentation.labelKey);

  return (
    <span title={title} aria-label={label}>
      <Badge variant={presentation.variant} className={className}>
        {label}
      </Badge>
    </span>
  );
}
