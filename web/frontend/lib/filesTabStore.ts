import { create } from 'zustand';

type SandboxProgress = { percent: number; label: string } | null;

type FilesTabState = {
  products: any[];
  selectedProduct: string | null;
  files: any[];
  truncatedByCategory: Record<string, boolean> | null;
  catalogInitialLoading: boolean;
  catalogLoadingMore: boolean;
  catalogTotal: number | null;
  lastCatalogBatchSize: number;
  catalogProgress: { loaded: number; total: number | null } | null;
  productsLoadError: string | null;
  productsReloadKey: number;
  fileLoading: boolean;
  expandedFile: string | null;
  sandboxIframeSrc: string | null;
  sandboxLoading: boolean;
  sandboxProgress: SandboxProgress;
  sandboxError: string | null;
  sandboxReloadKey: number;
  sandboxModalOpen: boolean;
  productSearch: string;
  productStateFilter: string;
  createdFrom: string;
  createdTo: string;
  fileSearch: string;
  fileCategoryFilter: string;
  ownerZipBusy: boolean;
  setProducts: (v: any[] | ((prev: any[]) => any[])) => void;
  setSelectedProduct: (v: string | null) => void;
  setFiles: (v: any[]) => void;
  setTruncatedByCategory: (v: Record<string, boolean> | null) => void;
  setCatalogInitialLoading: (v: boolean) => void;
  setCatalogLoadingMore: (v: boolean) => void;
  setCatalogTotal: (v: number | null) => void;
  setLastCatalogBatchSize: (v: number) => void;
  setCatalogProgress: (v: { loaded: number; total: number | null } | null) => void;
  setProductsLoadError: (v: string | null) => void;
  setProductsReloadKey: (v: number | ((prev: number) => number)) => void;
  setFileLoading: (v: boolean) => void;
  setExpandedFile: (v: string | null) => void;
  setSandboxIframeSrc: (v: string | null) => void;
  setSandboxLoading: (v: boolean) => void;
  setSandboxProgress: (v: SandboxProgress) => void;
  setSandboxError: (v: string | null) => void;
  setSandboxReloadKey: (v: number | ((prev: number) => number)) => void;
  setSandboxModalOpen: (v: boolean) => void;
  setProductSearch: (v: string) => void;
  setProductStateFilter: (v: string) => void;
  setCreatedFrom: (v: string) => void;
  setCreatedTo: (v: string) => void;
  setFileSearch: (v: string) => void;
  setFileCategoryFilter: (v: string) => void;
  setOwnerZipBusy: (v: boolean) => void;
};

export const useFilesTabStore = create<FilesTabState>((set) => ({
  products: [],
  selectedProduct: null,
  files: [],
  truncatedByCategory: null,
  catalogInitialLoading: true,
  catalogLoadingMore: false,
  catalogTotal: null,
  lastCatalogBatchSize: 0,
  catalogProgress: null,
  productsLoadError: null,
  productsReloadKey: 0,
  fileLoading: false,
  expandedFile: null,
  sandboxIframeSrc: null,
  sandboxLoading: false,
  sandboxProgress: null,
  sandboxError: null,
  sandboxReloadKey: 0,
  sandboxModalOpen: false,
  productSearch: '',
  productStateFilter: 'all',
  createdFrom: '',
  createdTo: '',
  fileSearch: '',
  fileCategoryFilter: 'all',
  ownerZipBusy: false,
  setProducts: (v) => set((s) => ({ products: typeof v === 'function' ? v(s.products) : v })),
  setSelectedProduct: (v) => set({ selectedProduct: v }),
  setFiles: (v) => set({ files: v }),
  setTruncatedByCategory: (v) => set({ truncatedByCategory: v }),
  setCatalogInitialLoading: (v) => set({ catalogInitialLoading: v }),
  setCatalogLoadingMore: (v) => set({ catalogLoadingMore: v }),
  setCatalogTotal: (v) => set({ catalogTotal: v }),
  setLastCatalogBatchSize: (v) => set({ lastCatalogBatchSize: v }),
  setCatalogProgress: (v) => set({ catalogProgress: v }),
  setProductsLoadError: (v) => set({ productsLoadError: v }),
  setProductsReloadKey: (v) =>
    set((s) => ({ productsReloadKey: typeof v === 'function' ? v(s.productsReloadKey) : v })),
  setFileLoading: (v) => set({ fileLoading: v }),
  setExpandedFile: (v) => set({ expandedFile: v }),
  setSandboxIframeSrc: (v) => set({ sandboxIframeSrc: v }),
  setSandboxLoading: (v) => set({ sandboxLoading: v }),
  setSandboxProgress: (v) => set({ sandboxProgress: v }),
  setSandboxError: (v) => set({ sandboxError: v }),
  setSandboxReloadKey: (v) =>
    set((s) => ({ sandboxReloadKey: typeof v === 'function' ? v(s.sandboxReloadKey) : v })),
  setSandboxModalOpen: (v) => set({ sandboxModalOpen: v }),
  setProductSearch: (v) => set({ productSearch: v }),
  setProductStateFilter: (v) => set({ productStateFilter: v }),
  setCreatedFrom: (v) => set({ createdFrom: v }),
  setCreatedTo: (v) => set({ createdTo: v }),
  setFileSearch: (v) => set({ fileSearch: v }),
  setFileCategoryFilter: (v) => set({ fileCategoryFilter: v }),
  setOwnerZipBusy: (v) => set({ ownerZipBusy: v }),
}));
