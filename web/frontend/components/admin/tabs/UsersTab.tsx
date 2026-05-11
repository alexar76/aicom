'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { UserPlus, Trash2, Shield, Loader2, RefreshCw } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import api, { AdminPanelUser, AdminRoleMeta } from '@/lib/api';
import { AdminLocale, t, tVars } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

/** Must match `AdminRole` in `web/backend/core/admin_roles.py`. */
const ADMIN_ROLE_IDS: readonly string[] = ['viewer', 'operator', 'admin', 'super_admin'];

function roleLabel(loc: AdminLocale, id: string): string {
  switch (id) {
    case 'viewer':
      return t(loc, 'users.role.viewer');
    case 'operator':
      return t(loc, 'users.role.operator');
    case 'admin':
      return t(loc, 'users.role.admin');
    case 'super_admin':
      return t(loc, 'users.role.super_admin');
    default:
      return id;
  }
}

function roleDescription(loc: AdminLocale, id: string): string {
  switch (id) {
    case 'viewer':
      return t(loc, 'users.roleDesc.viewer');
    case 'operator':
      return t(loc, 'users.roleDesc.operator');
    case 'admin':
      return t(loc, 'users.roleDesc.admin');
    case 'super_admin':
      return t(loc, 'users.roleDesc.super_admin');
    default:
      return '';
  }
}

function buildRoleOptions(meta: AdminRoleMeta[], loc: AdminLocale): AdminRoleMeta[] {
  const out: AdminRoleMeta[] = ADMIN_ROLE_IDS.map((id) => ({
    id,
    label: roleLabel(loc, id),
    description: roleDescription(loc, id),
  }));
  const known = new Set(ADMIN_ROLE_IDS);
  for (const r of meta) {
    if (r.id && !known.has(r.id)) {
      out.push({
        id: r.id,
        label: r.label || r.id,
        description: r.description || '',
      });
    }
  }
  return out;
}

export function UsersTab({ locale }: { locale: AdminLocale }) {
  const [users, setUsers] = useState<AdminPanelUser[]>([]);
  const [rolesMeta, setRolesMeta] = useState<AdminRoleMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('operator');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    let userList: AdminPanelUser[] = [];
    let meta: AdminRoleMeta[] = [];
    try {
      const u = await api.listAdminUsers();
      userList = u.users || [];
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(msg);
    }
    try {
      const r = await api.getAdminRolesMeta();
      meta = r.roles || [];
    } catch {
      /* UI falls back to built-in four roles + i18n */
    }
    setUsers(userList);
    setRolesMeta(meta);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async () => {
    if (newPassword.length < 12) {
      toast.error(t(locale, 'users.passwordMin'));
      return;
    }
    setSaving(true);
    try {
      await api.createAdminUser({
        username: newUsername.trim(),
        password: newPassword,
        role: newRole,
      });
      toast.success(t(locale, 'users.created'));
      setModalOpen(false);
      setNewUsername('');
      setNewPassword('');
      setNewRole('operator');
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const toggleEnabled = async (u: AdminPanelUser) => {
    try {
      await api.patchAdminUser(u.id, { enabled: !u.enabled });
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(msg);
    }
  };

  const changeRole = async (u: AdminPanelUser, role: string) => {
    try {
      await api.patchAdminUser(u.id, { role });
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(msg);
    }
  };

  const roleOptions = useMemo(() => {
    const base = buildRoleOptions(rolesMeta, locale);
    const ids = new Set(base.map((r) => r.id));
    const extras: AdminRoleMeta[] = [];
    for (const u of users) {
      const rid = u.role;
      if (rid && !ids.has(rid)) {
        ids.add(rid);
        extras.push({ id: rid, label: rid, description: '' });
      }
    }
    return [...base, ...extras];
  }, [rolesMeta, locale, users]);

  const selectClass =
    'rounded-lg border border-white/15 bg-slate-900 px-2 py-1.5 text-sm text-white shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40';

  const remove = async (u: AdminPanelUser) => {
    if (!confirm(tVars(locale, 'users.confirmDelete', { name: u.username }))) return;
    try {
      await api.deleteAdminUser(u.id);
      toast.success(t(locale, 'users.deleted'));
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(msg);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex flex-wrap items-center justify-between gap-4 mb-2">
          <div className="flex items-center gap-3">
            <Shield className="w-8 h-8 text-indigo-400" />
            <div>
              <h1 className="text-2xl font-semibold text-white">{t(locale, 'users.title')}</h1>
              <p className="text-sm text-gray-400">{t(locale, 'users.subtitle')}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => load()} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              {t(locale, 'users.refresh')}
            </Button>
            <Button onClick={() => setModalOpen(true)}>
              <UserPlus className="w-4 h-4 mr-2" />
              {t(locale, 'users.add')}
            </Button>
          </div>
        </div>
      </motion.div>

      <GlassCard className="p-0 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-400 gap-2">
            <Loader2 className="w-5 h-5 animate-spin" />
            {t(locale, 'users.loading')}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-white/5 text-left text-gray-400 uppercase text-xs tracking-wide">
                <tr>
                  <th className="px-4 py-3">{t(locale, 'users.colUser')}</th>
                  <th className="px-4 py-3">{t(locale, 'users.colRole')}</th>
                  <th className="px-4 py-3">{t(locale, 'users.colStatus')}</th>
                  <th className="px-4 py-3 text-right">{t(locale, 'users.colActions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-white/5">
                    <td className="px-4 py-3 text-white font-medium">{u.username}</td>
                    <td className="px-4 py-3">
                      <select
                        value={u.role}
                        onChange={(e) => changeRole(u, e.target.value)}
                        className={selectClass}
                      >
                        {roleOptions.map((r) => (
                          <option key={r.id} value={r.id} className="bg-slate-900 text-white">
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => toggleEnabled(u)}
                        className={`text-xs px-2 py-1 rounded-lg border ${
                          u.enabled
                            ? 'border-emerald-500/40 text-emerald-300'
                            : 'border-red-500/40 text-red-300'
                        }`}
                      >
                        {u.enabled ? t(locale, 'users.active') : t(locale, 'users.disabled')}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => remove(u)}
                        className="p-2 rounded-lg text-red-400 hover:bg-red-500/10"
                        aria-label="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      <Modal
        isOpen={modalOpen}
        onClose={() => !saving && setModalOpen(false)}
        title={t(locale, 'users.modalTitle')}
      >
        <div className="space-y-4">
          <Input
            label={t(locale, 'users.username')}
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
            placeholder="operator1"
          />
          <Input
            label={t(locale, 'users.password')}
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="••••••••••••"
          />
          <div>
            <label className="block text-xs text-gray-500 mb-1">{t(locale, 'users.role')}</label>
            <select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              className={`w-full ${selectClass} px-3 py-2`}
            >
              {roleOptions.map((r) => (
                <option key={r.id} value={r.id} className="bg-slate-900 text-white">
                  {r.description ? `${r.label} — ${r.description}` : r.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setModalOpen(false)} disabled={saving}>
              {t(locale, 'users.cancel')}
            </Button>
            <Button onClick={handleCreate} loading={saving} disabled={!newUsername.trim()}>
              {t(locale, 'users.save')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
