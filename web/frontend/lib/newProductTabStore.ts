import { create } from 'zustand';
import type { ContentLocaleChoice } from '@/lib/contentLanguages';
import type { ProductCreationTemplate } from '@/lib/productCreationTemplates';
import type { ResolvedFailure } from '@/lib/actionableErrors';

export type DeliveryChoice = 'full_software' | 'marketing_landing' | 'desktop_app' | 'infer';
export type ProductMode = 'prototype' | 'production';

export type CloudTemplateRow = {
  id: string;
  name: string;
  delivery_profile: string;
  production_mode: boolean;
  instructions: string;
};

type NewProductTabState = {
  step: number;
  idea: string;
  instructions: string;
  deliveryChoice: DeliveryChoice;
  categoryChoice: string;
  mode: ProductMode;
  contentLocale: ContentLocaleChoice;
  stylePresetId: string;
  landingFastPath: boolean;
  submitting: boolean;
  result: string | null;
  createdId: string | null;
  submitFailure: ResolvedFailure | null;
  templatesFailure: ResolvedFailure | null;
  prefillFailure: ResolvedFailure | null;
  cloudOpFailure: ResolvedFailure | null;
  templates: ProductCreationTemplate[];
  cloudTemplates: CloudTemplateRow[];
  templateName: string;
  dismissedHint: boolean;
  consentAiPrefill: boolean;
  aiBusy: boolean;
  introDismissed: boolean;
  setStep: (v: number) => void;
  setIdea: (v: string) => void;
  setInstructions: (v: string) => void;
  setDeliveryChoice: (v: DeliveryChoice) => void;
  setCategoryChoice: (v: string) => void;
  setMode: (v: ProductMode) => void;
  setContentLocale: (v: ContentLocaleChoice) => void;
  setStylePresetId: (v: string) => void;
  setLandingFastPath: (v: boolean) => void;
  setSubmitting: (v: boolean) => void;
  setResult: (v: string | null) => void;
  setCreatedId: (v: string | null) => void;
  setSubmitFailure: (v: ResolvedFailure | null) => void;
  setTemplatesFailure: (v: ResolvedFailure | null) => void;
  setPrefillFailure: (v: ResolvedFailure | null) => void;
  setCloudOpFailure: (v: ResolvedFailure | null) => void;
  setTemplates: (v: ProductCreationTemplate[]) => void;
  setCloudTemplates: (v: CloudTemplateRow[] | ((prev: CloudTemplateRow[]) => CloudTemplateRow[])) => void;
  setTemplateName: (v: string) => void;
  setDismissedHint: (v: boolean) => void;
  setConsentAiPrefill: (v: boolean) => void;
  setAiBusy: (v: boolean) => void;
  setIntroDismissed: (v: boolean) => void;
};

export const useNewProductTabStore = create<NewProductTabState>((set) => ({
  step: 1,
  idea: '',
  instructions: '',
  deliveryChoice: 'full_software',
  categoryChoice: 'saas',
  mode: 'prototype',
  contentLocale: 'auto',
  stylePresetId: '',
  landingFastPath: true,
  submitting: false,
  result: null,
  createdId: null,
  submitFailure: null,
  templatesFailure: null,
  prefillFailure: null,
  cloudOpFailure: null,
  templates: [],
  cloudTemplates: [],
  templateName: '',
  dismissedHint: false,
  consentAiPrefill: false,
  aiBusy: false,
  introDismissed: true,
  setStep: (v) => set({ step: v }),
  setIdea: (v) => set({ idea: v }),
  setInstructions: (v) => set({ instructions: v }),
  setDeliveryChoice: (v) => set({ deliveryChoice: v }),
  setCategoryChoice: (v) => set({ categoryChoice: v }),
  setMode: (v) => set({ mode: v }),
  setContentLocale: (v) => set({ contentLocale: v }),
  setStylePresetId: (v) => set({ stylePresetId: v }),
  setLandingFastPath: (v) => set({ landingFastPath: v }),
  setSubmitting: (v) => set({ submitting: v }),
  setResult: (v) => set({ result: v }),
  setCreatedId: (v) => set({ createdId: v }),
  setSubmitFailure: (v) => set({ submitFailure: v }),
  setTemplatesFailure: (v) => set({ templatesFailure: v }),
  setPrefillFailure: (v) => set({ prefillFailure: v }),
  setCloudOpFailure: (v) => set({ cloudOpFailure: v }),
  setTemplates: (v) => set({ templates: v }),
  setCloudTemplates: (v) =>
    set((s) => ({ cloudTemplates: typeof v === 'function' ? v(s.cloudTemplates) : v })),
  setTemplateName: (v) => set({ templateName: v }),
  setDismissedHint: (v) => set({ dismissedHint: v }),
  setConsentAiPrefill: (v) => set({ consentAiPrefill: v }),
  setAiBusy: (v) => set({ aiBusy: v }),
  setIntroDismissed: (v) => set({ introDismissed: v }),
}));
