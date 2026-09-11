import { create } from 'zustand';
import type { ResolvedFailure } from '@/lib/actionableErrors';

type MaterialKind = 'spec' | 'architecture';
type WorkshopRow = Record<string, unknown> & { id?: string; state?: string; idea?: string };

type WorkshopTabState = {
  rows: WorkshopRow[];
  loading: boolean;
  boardFailure: ResolvedFailure | null;
  diffFailure: ResolvedFailure | null;
  patternFailure: ResolvedFailure | null;
  pushFailure: ResolvedFailure | null;
  pushTestFailure: ResolvedFailure | null;
  workshopIntroDismissed: boolean;
  aId: string;
  bId: string;
  leftJson: string;
  rightJson: string;
  diffBusy: boolean;
  materialKind: MaterialKind;
  labPid: string;
  labSandboxId: string;
  labRefreshMs: number;
  labTick: number;
  patterns: any[];
  patternsBusy: boolean;
  patName: string;
  patTags: string;
  patDoc: string;
  pushBusy: boolean;
  setRows: (v: WorkshopRow[]) => void;
  setLoading: (v: boolean) => void;
  setBoardFailure: (v: ResolvedFailure | null) => void;
  setDiffFailure: (v: ResolvedFailure | null) => void;
  setPatternFailure: (v: ResolvedFailure | null) => void;
  setPushFailure: (v: ResolvedFailure | null) => void;
  setPushTestFailure: (v: ResolvedFailure | null) => void;
  setWorkshopIntroDismissed: (v: boolean) => void;
  setAId: (v: string) => void;
  setBId: (v: string) => void;
  setLeftJson: (v: string) => void;
  setRightJson: (v: string) => void;
  setDiffBusy: (v: boolean) => void;
  setMaterialKind: (v: MaterialKind) => void;
  setLabPid: (v: string) => void;
  setLabSandboxId: (v: string) => void;
  setLabRefreshMs: (v: number) => void;
  setLabTick: (v: number | ((x: number) => number)) => void;
  setPatterns: (v: any[]) => void;
  setPatternsBusy: (v: boolean) => void;
  setPatName: (v: string) => void;
  setPatTags: (v: string) => void;
  setPatDoc: (v: string) => void;
  setPushBusy: (v: boolean) => void;
};

export const useWorkshopTabStore = create<WorkshopTabState>((set) => ({
  rows: [],
  loading: true,
  boardFailure: null,
  diffFailure: null,
  patternFailure: null,
  pushFailure: null,
  pushTestFailure: null,
  workshopIntroDismissed: true,
  aId: '',
  bId: '',
  leftJson: '',
  rightJson: '',
  diffBusy: false,
  materialKind: 'spec',
  labPid: '',
  labSandboxId: '',
  labRefreshMs: 8000,
  labTick: 0,
  patterns: [],
  patternsBusy: false,
  patName: '',
  patTags: '',
  patDoc: '{\n  "example": true\n}',
  pushBusy: false,
  setRows: (v) => set({ rows: v }),
  setLoading: (v) => set({ loading: v }),
  setBoardFailure: (v) => set({ boardFailure: v }),
  setDiffFailure: (v) => set({ diffFailure: v }),
  setPatternFailure: (v) => set({ patternFailure: v }),
  setPushFailure: (v) => set({ pushFailure: v }),
  setPushTestFailure: (v) => set({ pushTestFailure: v }),
  setWorkshopIntroDismissed: (v) => set({ workshopIntroDismissed: v }),
  setAId: (v) => set({ aId: v }),
  setBId: (v) => set({ bId: v }),
  setLeftJson: (v) => set({ leftJson: v }),
  setRightJson: (v) => set({ rightJson: v }),
  setDiffBusy: (v) => set({ diffBusy: v }),
  setMaterialKind: (v) => set({ materialKind: v }),
  setLabPid: (v) => set({ labPid: v }),
  setLabSandboxId: (v) => set({ labSandboxId: v }),
  setLabRefreshMs: (v) => set({ labRefreshMs: v }),
  setLabTick: (v) => set((s) => ({ labTick: typeof v === 'function' ? v(s.labTick) : v })),
  setPatterns: (v) => set({ patterns: v }),
  setPatternsBusy: (v) => set({ patternsBusy: v }),
  setPatName: (v) => set({ patName: v }),
  setPatTags: (v) => set({ patTags: v }),
  setPatDoc: (v) => set({ patDoc: v }),
  setPushBusy: (v) => set({ pushBusy: v }),
}));
