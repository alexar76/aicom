import { useCallback, useEffect, useState } from 'react';
import { meshApi, type ActivityEvent, type Agent, type MeshStats, type Task } from './lib/api';
import { ActivityFeed } from './components/ActivityFeed';
import { AgentGrid } from './components/AgentGrid';
import { MeshTopology } from './components/MeshTopology';
import { StatsBar } from './components/StatsBar';

const SLOW_POLL_MS = 20_000;

export default function App() {
  const [stats, setStats] = useState<MeshStats | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [taskIntent, setTaskIntent] = useState('research and summarize agent mesh patterns');
  const [taskBudget, setTaskBudget] = useState(3.5);
  const [submitting, setSubmitting] = useState(false);

  const refreshCore = useCallback(async () => {
    try {
      const [s, a, t] = await Promise.all([
        meshApi.stats(),
        meshApi.agents(),
        meshApi.tasks(),
      ]);
      setStats(s);
      setAgents(a);
      setTasks(t);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'API unreachable');
    }
  }, []);

  const refreshActivity = useCallback(async () => {
    try {
      const ev = await meshApi.activity();
      setActivity(ev);
    } catch {
      /* SSE is primary; polling is fallback */
    }
  }, []);

  useEffect(() => {
    void refreshCore();
    void refreshActivity();
    const id = setInterval(() => void refreshCore(), SLOW_POLL_MS);
    return () => clearInterval(id);
  }, [refreshCore, refreshActivity]);

  useEffect(() => {
    const es = new EventSource(meshApi.activityStreamUrl());
    es.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as ActivityEvent;
        setActivity((prev) => {
          if (prev.some((e) => e.id === event.id)) return prev;
          const next = [...prev, event];
          return next.slice(-80);
        });
      } catch {
        /* ignore malformed SSE payloads */
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, []);

  const submitTask = async () => {
    setSubmitting(true);
    try {
      await meshApi.createTask(taskIntent, taskBudget);
      await refreshCore();
      await refreshActivity();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Task failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mesh-grid min-h-screen">
      <header className="border-b border-white/10 bg-black/40 backdrop-blur-xl sticky top-0 z-20">
        <div className="mx-auto max-w-7xl px-4 py-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400/90">
              Killer Product
            </p>
            <h1 className="font-display text-2xl md:text-3xl font-bold text-white tracking-tight">
              AI Service Mesh
            </h1>
            <p className="text-sm text-slate-400 mt-1 max-w-xl">
              Airbnb for AI agents — discover, verify, escrow, and pay autonomously.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="live-dot inline-block h-2 w-2 rounded-full bg-emerald-400" />
            Live activity (SSE)
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 space-y-8">
        {error && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            {error} — start API: <code className="font-mono text-cyan-300">cd backend && pip install -e .[dev] && python -m ai_service_mesh.main</code>
          </div>
        )}

        {stats && <StatsBar stats={stats} />}

        <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 shadow-glow">
          <h2 className="font-display text-lg font-semibold text-white mb-3">Submit mesh task</h2>
          <p className="text-xs text-slate-500 mb-3">
            Routes through AIMarket Hub — real discovery and <code className="text-cyan-400/80">/ai-market/v2/invoke</code>.
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              className="flex-1 rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
              value={taskIntent}
              onChange={(e) => setTaskIntent(e.target.value)}
            />
            <input
              type="number"
              min={0.01}
              step={0.01}
              aria-label="Task budget USD"
              className="w-full sm:w-28 rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
              value={taskBudget}
              onChange={(e) => setTaskBudget(Number(e.target.value) || 0.01)}
            />
            <button
              type="button"
              disabled={submitting}
              onClick={() => void submitTask()}
              className="shrink-0 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-600 px-6 py-3 text-sm font-semibold text-white disabled:opacity-50 hover:from-cyan-400 hover:to-violet-500 transition"
            >
              {submitting ? 'Mesh running…' : 'Execute pipeline'}
            </button>
          </div>
        </section>

        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <ActivityFeed events={activity} />
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <h2 className="font-display text-lg font-semibold text-white mb-4">Recent tasks</h2>
              <ul className="space-y-3">
                {tasks.length === 0 && (
                  <li className="text-sm text-slate-500">No tasks yet — submit a task above (requires AIMarket Hub on :9080).</li>
                )}
                {tasks.map((t) => (
                  <li
                    key={t.id}
                    className="rounded-xl border border-white/5 bg-black/30 px-4 py-3 text-sm"
                  >
                    <div className="flex flex-wrap justify-between gap-2 mb-1">
                      <span className="font-mono text-xs text-cyan-300/80">{t.id}</span>
                      <span
                        className={`text-xs font-medium uppercase ${
                          t.status === 'completed' ? 'text-emerald-400' : t.status === 'failed' ? 'text-rose-400' : 'text-amber-300'
                        }`}
                      >
                        {t.status}
                      </span>
                    </div>
                    <p className="text-slate-300 line-clamp-2">{t.intent}</p>
                    <p className="text-xs text-slate-500 mt-1">
                      {t.hops.length} hops · ${t.total_spent_usd.toFixed(2)} spent
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="space-y-6">
            <MeshTopology agents={agents} />
            <AgentGrid agents={agents} />
          </div>
        </div>
      </main>

      <footer className="border-t border-white/5 py-6 text-center text-xs text-slate-600">
        AI Service Mesh v0.1 — future standalone repo · integrates aimarket-hub, plugins, widget, aicom
      </footer>
    </div>
  );
}
