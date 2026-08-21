'use client';

import type { ReactNode } from 'react';
import type { SettingsSectionId } from './settingsNavConfig';

export function SettingsSection({
  id,
  children,
}: {
  id: SettingsSectionId;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-28 lg:scroll-mt-8">
      {children}
    </section>
  );
}
