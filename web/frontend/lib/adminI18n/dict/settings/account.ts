import type { I18nDict } from '../../types';

export const ACCOUNT_SETTINGS_DICT: I18nDict = {
  'settings.section.changePassword': {
    en: 'Change Password',
    ru: 'Сменить пароль',
    es: 'Cambiar contraseña',
  },
  'settings.password.current': {
    en: 'Current Password',
    ru: 'Текущий пароль',
    es: 'Contraseña actual',
  },
  'settings.password.new': {
    en: 'New Password',
    ru: 'Новый пароль',
    es: 'Nueva contraseña',
  },
  'settings.password.confirm': {
    en: 'Confirm New Password',
    ru: 'Подтвердите новый пароль',
    es: 'Confirmar nueva contraseña',
  },
  'settings.password.mismatch': {
    en: 'New password and confirmation do not match',
    ru: 'Новый пароль и подтверждение не совпадают',
    es: 'La nueva contraseña y la confirmación no coinciden',
  },
  'settings.password.updated': {
    en: 'Password changed',
    ru: 'Пароль изменён',
    es: 'Contraseña cambiada',
  },
  'settings.password.update': {
    en: 'Update Password',
    ru: 'Обновить пароль',
    es: 'Actualizar contraseña',
  },
  'settings.section.passkey': {
    en: 'Passkey (WebAuthn)',
    ru: 'Passkey (WebAuthn)',
    es: 'Passkey (WebAuthn)',
  },
  'settings.passkey.intro': {
    en: 'Platform passkeys (Touch ID, Windows Hello, security key) instead of TOTP codes.',
    ru: 'Платформенные passkeys (Touch ID, Windows Hello, ключ безопасности) вместо кодов TOTP.',
    es: 'Passkeys de plataforma (Touch ID, Windows Hello, llave) en lugar de códigos TOTP.',
  },
  'settings.passkey.disableTotpFirst': {
    en: 'Disable TOTP first to register a passkey.',
    ru: 'Сначала отключите TOTP, чтобы зарегистрировать passkey.',
    es: 'Desactiva primero TOTP para registrar un passkey.',
  },
  'settings.passkey.badgeEnabled': {
    en: 'Passkey enabled',
    ru: 'Passkey включён',
    es: 'Passkey activado',
  },
  'settings.passkey.remove': {
    en: 'Remove passkeys',
    ru: 'Удалить passkeys',
    es: 'Quitar passkeys',
  },
  'settings.passkey.register': {
    en: 'Register passkey',
    ru: 'Зарегистрировать passkey',
    es: 'Registrar passkey',
  },
  'settings.passkey.waitingDevice': {
    en: 'Waiting for device…',
    ru: 'Ожидание устройства…',
    es: 'Esperando al dispositivo…',
  },
  'settings.passkey.modal.title': {
    en: 'Remove passkeys',
    ru: 'Удалить passkeys',
    es: 'Quitar passkeys',
  },
  'settings.passkey.modal.body': {
    en: 'Confirm your password to remove all registered passkeys.',
    ru: 'Подтвердите пароль, чтобы удалить все зарегистрированные passkeys.',
    es: 'Confirma tu contraseña para quitar todos los passkeys registrados.',
  },
  'settings.label.currentPassword': {
    en: 'Current password',
    ru: 'Текущий пароль',
    es: 'Contraseña actual',
  },
  'settings.passkey.modal.confirm': {
    en: 'Remove passkeys',
    ru: 'Удалить passkeys',
    es: 'Quitar passkeys',
  },
  'settings.section.twofa': {
    en: 'Two-Factor Authentication',
    ru: 'Двухфакторная аутентификация',
    es: 'Autenticación de dos factores',
  },
  'settings.twofa.intro': {
    en: 'TOTP-based 2FA (Google Authenticator, 1Password, etc.). After enabling, login requires a 6-digit code.',
    ru: '2FA на основе TOTP (Google Authenticator, 1Password и т.д.). После включения вход требует 6‑значный код.',
    es: '2FA con TOTP (Google Authenticator, 1Password, etc.). Tras activarlo, el inicio de sesión pide un código de 6 dígitos.',
  },
  'settings.twofa.removePasskeyFirst': {
    en: 'Remove passkeys first to use TOTP.',
    ru: 'Сначала удалите passkeys, чтобы использовать TOTP.',
    es: 'Quita primero los passkeys para usar TOTP.',
  },
  'settings.twofa.pendingBanner': {
    en: 'A secret is pending verification — open Complete 2FA setup or cancel to start over.',
    ru: 'Секрет ожидает проверки — откройте «Завершить настройку 2FA» или отмените, чтобы начать заново.',
    es: 'Hay un secreto pendiente de verificación — abre Completar configuración 2FA o cancela para empezar de nuevo.',
  },
  'settings.twofa.setup': {
    en: 'Setup 2FA',
    ru: 'Настроить 2FA',
    es: 'Configurar 2FA',
  },
  'settings.twofa.completeSetup': {
    en: 'Complete 2FA setup',
    ru: 'Завершить настройку 2FA',
    es: 'Completar configuración 2FA',
  },
  'settings.twofa.cancelPending': {
    en: 'Cancel pending setup',
    ru: 'Отменить ожидающую настройку',
    es: 'Cancelar configuración pendiente',
  },
  'settings.twofa.badgeEnabled': {
    en: '2FA enabled',
    ru: '2FA включена',
    es: '2FA activada',
  },
  'settings.twofa.disable': {
    en: 'Disable 2FA',
    ru: 'Отключить 2FA',
    es: 'Desactivar 2FA',
  },
  'settings.twofa.modal.step1Title': {
    en: 'Setup 2FA — confirm password',
    ru: 'Настройка 2FA — подтвердите пароль',
    es: 'Configurar 2FA — confirmar contraseña',
  },
  'settings.twofa.modal.step2Title': {
    en: 'Setup 2FA — scan & verify',
    ru: 'Настройка 2FA — сканирование и проверка',
    es: 'Configurar 2FA — escanear y verificar',
  },
  'settings.twofa.passwordLabel': {
    en: 'Current admin password',
    ru: 'Текущий пароль администратора',
    es: 'Contraseña de admin actual',
  },
  'settings.twofa.passwordPlaceholder': {
    en: 'Required to generate a secret',
    ru: 'Нужно для генерации секрета',
    es: 'Necesario para generar el secreto',
  },
  'settings.twofa.continue': {
    en: 'Continue',
    ru: 'Продолжить',
    es: 'Continuar',
  },
  'settings.twofa.working': {
    en: 'Working…',
    ru: 'Выполняется…',
    es: 'Trabajando…',
  },
  'settings.twofa.manualEntry': {
    en: 'Or enter manually:',
    ru: 'Или введите вручную:',
    es: 'O introduce manualmente:',
  },
  'settings.twofa.needQrAgain': {
    en: 'Enter the 6-digit code from your authenticator app. Need the QR again? Cancel pending setup from Settings and start over.',
    ru: 'Введите 6‑значный код из приложения‑аутентификатора. Нужен QR снова? Отмените ожидающую настройку в Настройках и начните заново.',
    es: 'Introduce el código de 6 dígitos de tu app autenticadora. ¿Otra vez el QR? Cancela la configuración pendiente en Ajustes y empieza de nuevo.',
  },
  'settings.twofa.verificationCode': {
    en: 'Verification code',
    ru: 'Код подтверждения',
    es: 'Código de verificación',
  },
  'settings.twofa.codePlaceholder': {
    en: '000000',
    ru: '000000',
    es: '000000',
  },
  'settings.twofa.verifyEnable': {
    en: 'Verify & enable',
    ru: 'Проверить и включить',
    es: 'Verificar y activar',
  },
  'settings.twofa.verifying': {
    en: 'Verifying…',
    ru: 'Проверка…',
    es: 'Verificando…',
  },
  'settings.twofa.cancelSetup': {
    en: 'Cancel setup',
    ru: 'Отменить настройку',
    es: 'Cancelar configuración',
  },
  'settings.twofa.modal.disableTitle': {
    en: 'Disable 2FA',
    ru: 'Отключить 2FA',
    es: 'Desactivar 2FA',
  },
  'settings.twofa.modal.disableBody': {
    en: 'Confirm your password to remove TOTP protection from this admin account.',
    ru: 'Подтвердите пароль, чтобы снять защиту TOTP с этой учётной записи админа.',
    es: 'Confirma tu contraseña para quitar la protección TOTP de esta cuenta de admin.',
  },
  'settings.section.theme': {
    en: 'Theme',
    ru: 'Тема оформления',
    es: 'Tema',
  },
  'settings.persist.saving': {
    en: 'Saving settings…',
    ru: 'Сохранение настроек…',
    es: 'Guardando ajustes…',
  },
  'settings.persist.hint': {
    en: 'Settings save automatically while you edit.',
    ru: 'Настройки сохраняются автоматически при редактировании.',
    es: 'Los ajustes se guardan solos mientras editas.',
  },
  'settings.toast.passkeyRegistered': {
    en: 'Passkey registered',
    ru: 'Passkey зарегистрирован',
    es: 'Passkey registrado',
  },
  'settings.toast.passkeyFailed': {
    en: 'Passkey setup failed',
    ru: 'Не удалось настроить passkey',
    es: 'Falló la configuración del passkey',
  },
  'settings.toast.passkeysRemoved': {
    en: 'Passkeys removed',
    ru: 'Passkeys удалены',
    es: 'Passkeys quitados',
  },
  'settings.toast.secretCreated': {
    en: 'Secret created — scan the QR code',
    ru: 'Секрет создан — отсканируйте QR',
    es: 'Secreto creado — escanea el código QR',
  },
  'settings.toast.twofaEnabled': {
    en: '2FA is now enabled',
    ru: '2FA теперь включена',
    es: '2FA está activada',
  },
  'settings.toast.invalidCode': {
    en: 'Invalid code',
    ru: 'Неверный код',
    es: 'Código inválido',
  },
  'settings.toast.twofaCancelled': {
    en: '2FA setup cancelled',
    ru: 'Настройка 2FA отменена',
    es: 'Configuración 2FA cancelada',
  },
  'settings.toast.pendingCleared': {
    en: 'Pending 2FA setup cleared',
    ru: 'Ожидающая настройка 2FA сброшена',
    es: 'Configuración 2FA pendiente borrada',
  },
  'settings.toast.twofaDisabled': {
    en: '2FA disabled',
    ru: '2FA отключена',
    es: '2FA desactivada',
  },
  'settings.toast.genericFailed': {
    en: 'Failed',
    ru: 'Не удалось',
    es: 'Error',
  },
  'settings.error.unknown': {
    en: 'Unknown error',
    ru: 'Неизвестная ошибка',
    es: 'Error desconocido',
  },
  'settings.passkey.credentialName': {
    en: 'Admin passkey',
    ru: 'Passkey администратора',
    es: 'Passkey de admin',
  },
};
