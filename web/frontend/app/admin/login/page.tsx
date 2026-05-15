'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Cpu, Lock, KeyRound, AlertTriangle, Eye, EyeOff, User } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import api from '@/lib/api';
import { getPasskeyAssertion } from '@/lib/webauthnClient';

export default function AdminLoginPage() {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [requires2FA, setRequires2FA] = useState(false);
  const [requiresWebAuthn, setRequiresWebAuthn] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

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
        webauthnCredential
      );

      localStorage.setItem('admin_token', response.access_token);
      window.location.href = '/admin';
    } catch (err: any) {
      const msg = err.message || 'Invalid credentials';
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
      setError(msg);
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
      {/* Background effects */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-1/3 left-1/3 w-96 h-96 bg-indigo-500/10 rounded-full blur-[128px]" />
        <div className="absolute bottom-1/3 right-1/3 w-96 h-96 bg-pink-500/10 rounded-full blur-[128px]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md relative"
      >
        <GlassCard className="p-8">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-500 p-3 mx-auto mb-4">
              <Cpu className="w-full h-full text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white">Admin Login</h1>
            <p className="text-sm text-gray-400 mt-1">
              AI-Factory v2.1 Management Panel
            </p>
          </div>

          {/* Error */}
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
              label="Username"
              placeholder="admin"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={handleKeyDown}
              icon={<User className="w-4 h-4" />}
            />
            {/* Password */}
            <div className="relative">
              <Input
                label="Password"
                type={showPassword ? 'text' : 'password'}
                placeholder="Enter admin password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={handleKeyDown}
                icon={<Lock className="w-4 h-4" />}
              />
              <button
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-[38px] text-gray-400 hover:text-gray-300 transition-colors"
              >
                {showPassword ? (
                  <EyeOff className="w-4 h-4" />
                ) : (
                  <Eye className="w-4 h-4" />
                )}
              </button>
            </div>

            {/* 2FA Code (shown after password verification) */}
            {requiresWebAuthn && (
              <p className="text-sm text-indigo-200/90 text-center">
                Use your passkey (Touch ID, Windows Hello, security key) on the next step.
              </p>
            )}

            {requires2FA && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
              >
                <Input
                  label="2FA Code"
                  placeholder="Enter 6-digit code"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.slice(0, 6))}
                  onKeyDown={handleKeyDown}
                  icon={<KeyRound className="w-4 h-4" />}
                  maxLength={6}
                />
              </motion.div>
            )}

            {/* Login Button */}
            <Button
              className="w-full"
              size="lg"
              onClick={handleLogin}
              loading={loading}
              disabled={!password || !username.trim()}
            >
              {requiresWebAuthn ? 'Sign in with passkey' : requires2FA ? 'Verify 2FA' : 'Login'}
            </Button>
          </div>

          {/* Footer */}
          <p className="text-center text-xs text-gray-600 mt-6">
            Secure admin access with password and optional 2FA
          </p>
        </GlassCard>
      </motion.div>
    </div>
  );
}
