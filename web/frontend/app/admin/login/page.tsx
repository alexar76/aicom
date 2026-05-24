'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Cpu, Lock, KeyRound, AlertTriangle, Eye, EyeOff, User, Languages } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import api from '@/lib/api';
import { getPasskeyAssertion } from '@/lib/webauthnClient';
import {
  type AdminLocale,
  detectAdminLocale,
  saveAdminLocale,
  t,
} from '@/lib/adminI18n';

export default function AdminLoginPage() {
  const [locale, setLocale] = useState<AdminLocale>('en');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [requires2FA, setRequires2FA] = useState(false);
  const [requiresWebAuthn, setRequiresWebAuthn] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [oidcEnabled, setOidcEnabled] = useState(false);

  useEffect(() => {
    setLocale(detectAdminLocale());
    api.oidcStatus().then((s) => setOidcEnabled(Boolean(s.enabled))).catch(() => {});
  }, []);

  const onLocaleChange = (next: AdminLocale) => {
    setLocale(next);
    saveAdminLocale(next);
  };

  const handleLogin = async () => {
    if (!password) return;

    setLoading(true);
    setError(null);

    try {
      let webauthnCredential: Record<string, unknown> | undefined;
      if (requiresWebAuthn) {
        const { publicKey } = await api.webauthnLoginOptions(username.trim() || 'admin');
        webauthnCredential = await getPasskeyAssertion(publicKey);
      }
      const response = await api.login(
        username.trim() || 'admin',
        password,
        totpCode || undefined,
        webauthnCredential,
      );

      localStorage.setItem('admin_token', response.access_token);
      localStorage.removeItem('customer_token');
      localStorage.removeItem('customer_email');
      window.location.href = '/admin';
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t(locale, 'login.invalidCredentials');
      if (msg === '2FA code required' && !totpCode) {
        setRequires2FA(true);
        setRequiresWebAuthn(false);
        setLoading(false);
        return;
      }
      if (msg === 'WebAuthn required' && !requiresWebAuthn) {
        setRequiresWebAuthn(true);
        setRequires2FA(false);
        setLoading(false);
        return;
      }
      setError(msg === 'Invalid credentials' ? t(locale, 'login.invalidCredentials') : msg);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleLogin();
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden" aria-hidden>
        <div className="absolute top-1/3 left-1/3 w-96 h-96 bg-indigo-500/10 rounded-full blur-[128px]" />
        <div className="absolute bottom-1/3 right-1/3 w-96 h-96 bg-pink-500/10 rounded-full blur-[128px]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md relative"
      >
        <GlassCard className="p-8">
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-500 p-3 mx-auto mb-4">
              <Cpu className="w-full h-full text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white">{t(locale, 'login.title')}</h1>
            <p className="text-sm text-gray-400 mt-1">{t(locale, 'login.subtitle')}</p>
          </div>

          <div className="mb-5">
            <label className="mb-1.5 flex items-center gap-2 text-xs font-medium text-gray-400">
              <Languages className="h-3.5 w-3.5" aria-hidden />
              {t(locale, 'login.language')}
            </label>
            <select
              value={locale}
              onChange={(e) => onLocaleChange(e.target.value as AdminLocale)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white"
            >
              <option value="en">English</option>
              <option value="ru">Русский</option>
              <option value="es">Español</option>
            </select>
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 p-3 mb-6 rounded-xl bg-red-500/10 border border-red-500/20"
            >
              <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />
              <p className="text-sm text-red-300">{error}</p>
            </motion.div>
          )}

          <div className="space-y-5">
            <Input
              label={t(locale, 'login.username')}
              placeholder={t(locale, 'login.usernamePlaceholder')}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={handleKeyDown}
              icon={<User className="w-4 h-4" />}
            />
            <div className="relative">
              <Input
                label={t(locale, 'login.password')}
                type={showPassword ? 'text' : 'password'}
                placeholder={t(locale, 'login.passwordPlaceholder')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={handleKeyDown}
                icon={<Lock className="w-4 h-4" />}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-[38px] text-gray-400 hover:text-gray-300 transition-colors"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>

            {requiresWebAuthn && (
              <p className="text-sm text-indigo-200/90 text-center">{t(locale, 'login.webauthnHint')}</p>
            )}

            {requires2FA && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                <Input
                  label={t(locale, 'login.totp')}
                  placeholder={t(locale, 'login.totpPlaceholder')}
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.slice(0, 6))}
                  onKeyDown={handleKeyDown}
                  icon={<KeyRound className="w-4 h-4" />}
                  maxLength={6}
                />
              </motion.div>
            )}

            <Button
              className="w-full"
              size="lg"
              onClick={handleLogin}
              loading={loading}
              disabled={!password || !username.trim()}
            >
              {requiresWebAuthn
                ? t(locale, 'login.webauthn')
                : requires2FA
                  ? t(locale, 'login.verify2fa')
                  : t(locale, 'login.submit')}
            </Button>

            {oidcEnabled && !requires2FA && !requiresWebAuthn && (
              <>
                <motion.div className="relative flex items-center py-1">
                  <div className="grow border-t border-white/10" />
                  <span className="mx-3 text-xs text-gray-500">{t(locale, 'login.ssoDivider')}</span>
                  <div className="grow border-t border-white/10" />
                </motion.div>
                <Button
                  className="w-full"
                  size="lg"
                  variant="secondary"
                  onClick={() => {
                    window.location.href = '/api/admin/auth/oidc/login';
                  }}
                  disabled={loading}
                >
                  {t(locale, 'login.sso')}
                </Button>
              </>
            )}
          </div>

          <p className="text-center text-xs text-gray-600 mt-6">{t(locale, 'login.footer')}</p>
        </GlassCard>
      </motion.div>
    </div>
  );
}
