'use client';

import { useRef, useState } from 'react';
import type React from 'react';
import toast from 'react-hot-toast';
import api from '@/lib/api';
import { resolveActionableFailure } from '@/lib/actionableErrors';

export type WorkshopCanvasNode = {
  id: string;
  label: string;
  x: number;
  y: number;
  branchId?: string;
};

export type WorkshopCanvasEdge = { id: string; source: string; target: string; kind?: string };

function uid(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function useWorkshopCanvas() {
  const [canvasPid, setCanvasPid] = useState('');
  const [canvasVersion, setCanvasVersion] = useState(1);
  const [nodes, setNodes] = useState<WorkshopCanvasNode[]>([]);
  const [edges, setEdges] = useState<WorkshopCanvasEdge[]>([]);
  const [canvasLoadBusy, setCanvasLoadBusy] = useState(false);
  const [canvasSaveBusy, setCanvasSaveBusy] = useState(false);
  const [canvasFailure, setCanvasFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [canvasSaveFailure, setCanvasSaveFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [edgeFrom, setEdgeFrom] = useState('');
  const [edgeTo, setEdgeTo] = useState('');
  const dragRef = useRef<{ id: string; ox: number; oy: number; px: number; py: number } | null>(null);

  const loadCanvas = async () => {
    if (!canvasPid.trim()) {
      toast.error('Enter a product ID for the canvas');
      return;
    }
    setCanvasLoadBusy(true);
    setCanvasFailure(null);
    setCanvasSaveFailure(null);
    try {
      const doc = await api.getIterationCanvas(canvasPid.trim());
      setCanvasVersion(Number(doc.version) || 1);
      setNodes((doc.nodes || []) as WorkshopCanvasNode[]);
      setEdges((doc.edges || []) as WorkshopCanvasEdge[]);
    } catch (e: unknown) {
      setCanvasFailure(resolveActionableFailure(e, { operation: 'workshop_canvas_load' }));
    } finally {
      setCanvasLoadBusy(false);
    }
  };

  const saveCanvas = async () => {
    if (!canvasPid.trim()) return;
    setCanvasSaveBusy(true);
    setCanvasSaveFailure(null);
    setCanvasFailure(null);
    try {
      const doc = await api.putIterationCanvas(canvasPid.trim(), {
        version: canvasVersion,
        nodes,
        edges,
      });
      setCanvasVersion(Number(doc.version) || 1);
      toast.success('Canvas saved');
    } catch (e: unknown) {
      setCanvasSaveFailure(resolveActionableFailure(e, { operation: 'workshop_canvas_save' }));
    } finally {
      setCanvasSaveBusy(false);
    }
  };

  const addStageNode = () => {
    const n = nodes.length;
    setNodes((prev) => [
      ...prev,
      {
        id: uid('stage'),
        label: `Stage ${n + 1}`,
        x: 80 + (n % 4) * 140,
        y: 80 + Math.floor(n / 4) * 100,
        branchId: 'main',
      },
    ]);
  };

  const forkSelectedBranch = (nodeId: string) => {
    const br = uid('branch');
    setNodes((prev) =>
      prev.map((x) => (x.id === nodeId ? { ...x, branchId: br, label: `${x.label} (fork)` } : x)),
    );
    toast.success('Node moved to a new branch id (edges unchanged)');
  };

  const addEdge = () => {
    if (!edgeFrom || !edgeTo || edgeFrom === edgeTo) {
      toast.error('Pick two different nodes');
      return;
    }
    setEdges((prev) => [...prev, { id: uid('e'), source: edgeFrom, target: edgeTo }]);
  };

  const mergeEdge = () => {
    if (!edgeFrom || !edgeTo || edgeFrom === edgeTo) {
      toast.error('Pick merge source and target');
      return;
    }
    setEdges((prev) => [...prev, { id: uid('e'), source: edgeFrom, target: edgeTo, kind: 'merge' }]);
    toast.success('Merge edge recorded');
  };

  const onNodePointerDown = (e: React.PointerEvent, id: string) => {
    e.preventDefault();
    const node = nodes.find((n) => n.id === id);
    if (!node) return;
    dragRef.current = { id, ox: node.x, oy: node.y, px: e.clientX, py: e.clientY };
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const onNodePointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const dx = e.clientX - d.px;
    const dy = e.clientY - d.py;
    setNodes((prev) =>
      prev.map((n) =>
        n.id === d.id ? { ...n, x: Math.max(20, d.ox + dx), y: Math.max(20, d.oy + dy) } : n,
      ),
    );
  };

  const onNodePointerUp = () => {
    dragRef.current = null;
  };

  return {
    canvasPid,
    setCanvasPid,
    canvasVersion,
    nodes,
    edges,
    canvasLoadBusy,
    canvasSaveBusy,
    canvasFailure,
    canvasSaveFailure,
    edgeFrom,
    setEdgeFrom,
    edgeTo,
    setEdgeTo,
    loadCanvas,
    saveCanvas,
    addStageNode,
    forkSelectedBranch,
    addEdge,
    mergeEdge,
    onNodePointerDown,
    onNodePointerMove,
    onNodePointerUp,
  };
}
