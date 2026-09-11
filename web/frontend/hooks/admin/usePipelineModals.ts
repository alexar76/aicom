'use client';

import { useState } from 'react';
import api from '@/lib/api';

export type TaskStageModalState = {
  productId: string;
  productName: string;
  agentType: string;
  task: Record<string, unknown> | null;
} | null;

export type ProductSpecView = {
  product_name?: string;
  description?: string;
  core_features?: string[];
  user_stories?: string[];
  technical_risks?: string[];
};

export function usePipelineModals() {
  const [expandedProduct, setExpandedProduct] = useState<string | null>(null);
  const [expandedFailureProduct, setExpandedFailureProduct] = useState<string | null>(null);
  const [specModalProduct, setSpecModalProduct] = useState<string | null>(null);
  const [specData, setSpecData] = useState<ProductSpecView | null>(null);
  const [specLoading, setSpecLoading] = useState(false);
  const [handoffModalProduct, setHandoffModalProduct] = useState<string | null>(null);
  const [handoffData, setHandoffData] = useState<Awaited<ReturnType<typeof api.getDeveloperHandoff>> | null>(null);
  const [handoffLoading, setHandoffLoading] = useState(false);
  const [taskStageModal, setTaskStageModal] = useState<TaskStageModalState>(null);

  const loadSpec = async (productId: string) => {
    setSpecModalProduct(productId);
    setSpecLoading(true);
    setSpecData(null);
    try {
      const result = await api.getProductSpec(productId);
      setSpecData(result.spec);
    } catch {
      setSpecData(null);
    } finally {
      setSpecLoading(false);
    }
  };

  const loadDeveloperHandoff = async (productId: string) => {
    setHandoffModalProduct(productId);
    setHandoffLoading(true);
    setHandoffData(null);
    try {
      const result = await api.getDeveloperHandoff(productId);
      setHandoffData(result);
    } catch {
      setHandoffData(null);
    } finally {
      setHandoffLoading(false);
    }
  };

  const openTaskDetailModal = (
    productId: string,
    productTitle: string,
    agentType: string,
    task: Record<string, unknown> | null | undefined,
  ) => {
    setTaskStageModal({
      productId,
      productName: productTitle,
      agentType,
      task: task ? { ...task } : null,
    });
  };

  const closeSpecModal = () => {
    setSpecModalProduct(null);
    setSpecData(null);
  };

  const closeHandoffModal = () => {
    setHandoffModalProduct(null);
    setHandoffData(null);
  };

  return {
    expandedProduct,
    setExpandedProduct,
    expandedFailureProduct,
    setExpandedFailureProduct,
    specModalProduct,
    setSpecModalProduct,
    specData,
    specLoading,
    loadSpec,
    closeSpecModal,
    handoffModalProduct,
    setHandoffModalProduct,
    handoffData,
    handoffLoading,
    loadDeveloperHandoff,
    closeHandoffModal,
    taskStageModal,
    setTaskStageModal,
    openTaskDetailModal,
  };
}
