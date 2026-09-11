'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { QRCodeSVG } from 'qrcode.react';
import apiClient from '@/lib/api';
import toast from 'react-hot-toast';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { GlassCard } from '@/components/ui/GlassCard';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { t } from '@/lib/adminI18n';
import type { SettingsTabApi } from './useSettingsTabState';

export function AccountSecuritySettings({
  api,
  publicDemo = false,
}: {
  api: SettingsTabApi;
  publicDemo?: boolean;
}) {
  const [pwdCurrent, setPwdCurrent] = useState('');
  const [pwdNew, setPwdNew] = useState('');
  const [pwdConfirm, setPwdConfirm] = useState('');
  const [pwdBusy, setPwdBusy] = useState(false);

  const {
    locale,
    twofaEnabled,
    twofaPending,
    twofaModalOpen,
    twofaStep,
    twofaPassword,
    twofaUri,
    twofaSecret,
    twofaVerify,
    twofaBusy,
    disable2faModalOpen,
    disable2faPassword,
    disable2faBusy,
    webauthnEnabled,
    mfaMethod,
    passkeyBusy,
    disablePasskeyModalOpen,
    disablePasskeyPassword,
    setTwofaModalOpen,
    setTwofaStep,
    setTwofaPassword,
    setTwofaUri,
    setTwofaSecret,
    setTwofaVerify,
    setTwofaBusy,
    setDisable2faModalOpen,
    setDisable2faPassword,
    setDisable2faBusy,
    setDisablePasskeyModalOpen,
    setDisablePasskeyPassword,
    setPasskeyBusy,
    refreshTwofaStatus,
  } = api;

  return (
    <>
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4">{t(locale, 'settings.section.changePassword')}</h3>
        {publicDemo ? (
          <p className="text-sm text-sky-200/90">{t(locale, 'settings.factoryBackup.demoBlocked')}</p>
        ) : (
          <div className="space-y-4">
            <Input
              label={t(locale, 'settings.password.current')}
              type="password"
              value={pwdCurrent}
              onChange={(e) => setPwdCurrent(e.target.value)}
            />
            <Input
              label={t(locale, 'settings.password.new')}
              type="password"
              value={pwdNew}
              onChange={(e) => setPwdNew(e.target.value)}
            />
            <Input
              label={t(locale, 'settings.password.confirm')}
              type="password"
              value={pwdConfirm}
              onChange={(e) => setPwdConfirm(e.target.value)}
            />
            <Button
              loading={pwdBusy}
              disabled={pwdBusy || pwdNew.length < 12 || pwdNew !== pwdConfirm}
              onClick={async () => {
                if (pwdNew !== pwdConfirm) {
                  toast.error(t(locale, 'settings.password.mismatch'));
                  return;
                }
                setPwdBusy(true);
                try {
                  await apiClient.changePassword(pwdCurrent, pwdNew);
                  toast.success(t(locale, 'settings.password.updated'));
                  setPwdCurrent('');
                  setPwdNew('');
                  setPwdConfirm('');
                } catch (e) {
                  toast.error(e instanceof Error ? e.message : String(e));
                } finally {
                  setPwdBusy(false);
                }
              }}
            >
              {t(locale, 'settings.password.update')}
            </Button>
          </div>
        )}
      </GlassCard>

      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4">{t(locale, 'settings.section.passkey')}</h3>
        <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.passkey.intro')}</p>
        {mfaMethod === 'totp' && twofaEnabled && (
          <p className="text-xs text-amber-200/80 mb-3">{t(locale, 'settings.passkey.disableTotpFirst')}</p>
        )}
        <motion.div className="flex flex-wrap items-center gap-2 mb-2">
          {webauthnEnabled ? (
            <>
              <Badge variant="success">{t(locale, 'settings.passkey.badgeEnabled')}</Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDisablePasskeyModalOpen(true);
                  setDisablePasskeyPassword('');
                }}
              >
                {t(locale, 'settings.passkey.remove')}
              </Button>
            </>
          ) : (
            <Button
              variant="secondary"
              disabled={passkeyBusy || (twofaEnabled && mfaMethod === 'totp')}
              onClick={() => {
                void (async () => {
                  setPasskeyBusy(true);
                  try {
                    const { publicKey } = await apiClient.webauthnRegisterOptions();
                    const { createPasskey } = await import('@/lib/webauthnClient');
                    const credential = await createPasskey(publicKey);
                    await apiClient.webauthnRegisterVerify(credential, t(locale, 'settings.passkey.credentialName'));
                    toast.success(t(locale, 'settings.toast.passkeyRegistered'));
                    await refreshTwofaStatus();
                  } catch (e: unknown) {
                    toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.passkeyFailed'));
                  } finally {
                    setPasskeyBusy(false);
                  }
                })();
              }}
            >
              {passkeyBusy ? t(locale, 'settings.passkey.waitingDevice') : t(locale, 'settings.passkey.register')}
            </Button>
          )}
        </motion.div>
      </GlassCard>

      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4">{t(locale, 'settings.section.twofa')}</h3>
        <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.twofa.intro')}</p>
        {webauthnEnabled && (
          <p className="text-xs text-amber-200/80 mb-3">{t(locale, 'settings.twofa.removePasskeyFirst')}</p>
        )}
        {twofaPending && !twofaEnabled && (
          <div className="mb-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 text-sm text-amber-100">
            {t(locale, 'settings.twofa.pendingBanner')}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          {!twofaEnabled ? (
            <>
              <Button
                variant="secondary"
                onClick={() => {
                  setTwofaModalOpen(true);
                  setTwofaStep(twofaPending ? 2 : 1);
                  setTwofaPassword('');
                  setTwofaVerify('');
                  if (!twofaPending) {
                    setTwofaUri('');
                    setTwofaSecret('');
                  }
                }}
              >
                {twofaPending ? t(locale, 'settings.twofa.completeSetup') : t(locale, 'settings.twofa.setup')}
              </Button>
              {twofaPending && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    void (async () => {
                      try {
                        await apiClient.cancel2FASetup();
                        toast.success(t(locale, 'settings.toast.pendingCleared'));
                        await refreshTwofaStatus();
                      } catch (e: unknown) {
                        toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.genericFailed'));
                      }
                    })();
                  }}
                >
                  {t(locale, 'settings.twofa.cancelPending')}
                </Button>
              )}
            </>
          ) : (
            <>
              <Badge variant="success">{t(locale, 'settings.twofa.badgeEnabled')}</Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDisable2faModalOpen(true);
                  setDisable2faPassword('');
                }}
              >
                {t(locale, 'settings.twofa.disable')}
              </Button>
            </>
          )}
        </div>
      </GlassCard>

      <Modal
        isOpen={twofaModalOpen}
        onClose={() => setTwofaModalOpen(false)}
        title={
          twofaStep === 1
            ? t(locale, 'settings.twofa.modal.step1Title')
            : t(locale, 'settings.twofa.modal.step2Title')
        }
        size={twofaStep === 2 ? 'lg' : 'md'}
      >
        <div className="space-y-4" onClick={(e) => e.stopPropagation()}>
          {twofaStep === 1 ? (
            <>
              <Input
                label={t(locale, 'settings.twofa.passwordLabel')}
                type="password"
                value={twofaPassword}
                onChange={(e) => setTwofaPassword(e.target.value)}
                placeholder={t(locale, 'settings.twofa.passwordPlaceholder')}
              />
              <Button
                variant="primary"
                disabled={twofaBusy || twofaPassword.length < 1}
                onClick={() => {
                  void (async () => {
                    setTwofaBusy(true);
                    try {
                      const res = await apiClient.setup2FA(twofaPassword);
                      setTwofaUri(res.uri);
                      setTwofaSecret(res.secret);
                      setTwofaStep(2);
                      await refreshTwofaStatus();
                      toast.success(t(locale, 'settings.toast.secretCreated'));
                    } catch (e: unknown) {
                      toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.genericFailed'));
                    } finally {
                      setTwofaBusy(false);
                    }
                  })();
                }}
              >
                {twofaBusy ? t(locale, 'settings.twofa.working') : t(locale, 'settings.twofa.continue')}
              </Button>
            </>
          ) : (
            <>
              {twofaUri ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="p-3 rounded-xl bg-white">
                    <QRCodeSVG value={twofaUri} size={200} level="M" />
                  </div>
                  <p className="text-xs text-gray-500 text-center">
                    {t(locale, 'settings.twofa.manualEntry')}{' '}
                    <span className="font-mono text-gray-300">{twofaSecret}</span>
                  </p>
                </div>
              ) : (
                <p className="text-sm text-gray-400">{t(locale, 'settings.twofa.needQrAgain')}</p>
              )}
              <Input
                label={t(locale, 'settings.twofa.verificationCode')}
                value={twofaVerify}
                onChange={(e) => setTwofaVerify(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder={t(locale, 'settings.twofa.codePlaceholder')}
                maxLength={6}
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  disabled={twofaBusy || twofaVerify.length !== 6}
                  onClick={() => {
                    void (async () => {
                      setTwofaBusy(true);
                      try {
                        await apiClient.verify2FA(twofaVerify.trim());
                        toast.success(t(locale, 'settings.toast.twofaEnabled'));
                        setTwofaModalOpen(false);
                        setTwofaVerify('');
                        await refreshTwofaStatus();
                      } catch (e: unknown) {
                        toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.invalidCode'));
                      } finally {
                        setTwofaBusy(false);
                      }
                    })();
                  }}
                >
                  {twofaBusy ? t(locale, 'settings.twofa.verifying') : t(locale, 'settings.twofa.verifyEnable')}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={twofaBusy}
                  onClick={() => {
                    void (async () => {
                      try {
                        await apiClient.cancel2FASetup();
                        toast(t(locale, 'settings.toast.twofaCancelled'));
                        setTwofaModalOpen(false);
                        await refreshTwofaStatus();
                      } catch (e: unknown) {
                        toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.genericFailed'));
                      }
                    })();
                  }}
                >
                  {t(locale, 'settings.twofa.cancelSetup')}
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>

      <Modal
        isOpen={disablePasskeyModalOpen}
        onClose={() => setDisablePasskeyModalOpen(false)}
        title={t(locale, 'settings.passkey.modal.title')}
        size="md"
      >
        <motion.div className="space-y-4">
          <p className="text-sm text-gray-400">{t(locale, 'settings.passkey.modal.body')}</p>
          <Input
            label={t(locale, 'settings.label.currentPassword')}
            type="password"
            value={disablePasskeyPassword}
            onChange={(e) => setDisablePasskeyPassword(e.target.value)}
          />
          <Button
            variant="secondary"
            disabled={passkeyBusy || disablePasskeyPassword.length < 1}
            onClick={() => {
              void (async () => {
                setPasskeyBusy(true);
                try {
                  await apiClient.disableWebAuthn(disablePasskeyPassword);
                  toast.success(t(locale, 'settings.toast.passkeysRemoved'));
                  setDisablePasskeyModalOpen(false);
                  setDisablePasskeyPassword('');
                  await refreshTwofaStatus();
                } catch (e: unknown) {
                  toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.genericFailed'));
                } finally {
                  setPasskeyBusy(false);
                }
              })();
            }}
          >
            {passkeyBusy ? t(locale, 'settings.twofa.working') : t(locale, 'settings.passkey.modal.confirm')}
          </Button>
        </motion.div>
      </Modal>

      <Modal
        isOpen={disable2faModalOpen}
        onClose={() => setDisable2faModalOpen(false)}
        title={t(locale, 'settings.twofa.modal.disableTitle')}
        size="md"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-400">{t(locale, 'settings.twofa.modal.disableBody')}</p>
          <Input
            label={t(locale, 'settings.label.currentPassword')}
            type="password"
            value={disable2faPassword}
            onChange={(e) => setDisable2faPassword(e.target.value)}
          />
          <Button
            variant="secondary"
            disabled={disable2faBusy || disable2faPassword.length < 1}
            onClick={() => {
              void (async () => {
                setDisable2faBusy(true);
                try {
                  await apiClient.disable2FA(disable2faPassword);
                  toast.success(t(locale, 'settings.toast.twofaDisabled'));
                  setDisable2faModalOpen(false);
                  setDisable2faPassword('');
                  await refreshTwofaStatus();
                } catch (e: unknown) {
                  toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.genericFailed'));
                } finally {
                  setDisable2faBusy(false);
                }
              })();
            }}
          >
            {disable2faBusy ? t(locale, 'settings.twofa.working') : t(locale, 'settings.twofa.disable')}
          </Button>
        </div>
      </Modal>
    </>
  );
}

export function ThemeSettings({ api }: { api: SettingsTabApi }) {
  const { locale, currentTheme, themeSaving, handleThemeChange } = api;

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-4">{t(locale, 'settings.section.theme')}</h3>
      <div className="flex flex-wrap gap-3">
        {['cyberpunk', 'minimal', 'glass', 'neon', 'corporate'].map((theme) => (
          <button
            key={theme}
            type="button"
            onClick={() => handleThemeChange(theme)}
            disabled={themeSaving === theme}
            className={`px-4 py-2 rounded-xl glass transition-all capitalize text-sm ${
              currentTheme === theme
                ? 'border-indigo-500/60 bg-indigo-500/15 text-white shadow-lg shadow-indigo-500/10'
                : 'hover:border-indigo-500/30 text-gray-300'
            }`}
          >
            {themeSaving === theme ? (
              <span className="flex items-center gap-2">
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                {theme}
              </span>
            ) : (
              theme
            )}
          </button>
        ))}
      </div>
    </GlassCard>
  );
}
