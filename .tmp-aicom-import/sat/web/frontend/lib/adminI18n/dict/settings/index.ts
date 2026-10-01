import type { I18nDict } from '../../types';
import { DIRECTOR_SETTINGS_DICT } from './director';
import { STANDUP_SETTINGS_DICT } from './standup';
import { DEPLOY_SETTINGS_DICT } from './deploy';
import { CONTENT_SETTINGS_DICT } from './content';
import { ACCOUNT_SETTINGS_DICT } from './account';
import { TELEGRAM_SETTINGS_DICT } from './telegram';
import { QUALITY_SETTINGS_DICT } from './quality';
import { PIPELINE_DB_SETTINGS_DICT } from './pipelineDb';
import { FACTORY_BACKUP_SETTINGS_DICT } from './factoryBackup';
import { FACTORY_HOLD_SETTINGS_DICT } from './factoryHold';
import { AUTONOMY_MODE_SETTINGS_DICT } from './autonomyMode';
import { HOST_DISK_SETTINGS_DICT } from './hostDisk';
import { SETTINGS_NAV_DICT } from './nav';

export const SETTINGS_DICT: I18nDict = {
  ...SETTINGS_NAV_DICT,
  ...HOST_DISK_SETTINGS_DICT,
  ...FACTORY_HOLD_SETTINGS_DICT,
  ...AUTONOMY_MODE_SETTINGS_DICT,
  ...DIRECTOR_SETTINGS_DICT,
  ...STANDUP_SETTINGS_DICT,
  ...DEPLOY_SETTINGS_DICT,
  ...CONTENT_SETTINGS_DICT,
  ...ACCOUNT_SETTINGS_DICT,
  ...TELEGRAM_SETTINGS_DICT,
  ...QUALITY_SETTINGS_DICT,
  ...PIPELINE_DB_SETTINGS_DICT,
  ...FACTORY_BACKUP_SETTINGS_DICT,
};
