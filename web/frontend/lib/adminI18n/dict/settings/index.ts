import type { I18nDict } from '../../types';
import { DIRECTOR_SETTINGS_DICT } from './director';
import { STANDUP_SETTINGS_DICT } from './standup';
import { DEPLOY_SETTINGS_DICT } from './deploy';
import { CONTENT_SETTINGS_DICT } from './content';
import { ACCOUNT_SETTINGS_DICT } from './account';
import { TELEGRAM_SETTINGS_DICT } from './telegram';
import { QUALITY_SETTINGS_DICT } from './quality';
import { PIPELINE_DB_SETTINGS_DICT } from './pipelineDb';

export const SETTINGS_DICT: I18nDict = {
  ...DIRECTOR_SETTINGS_DICT,
  ...STANDUP_SETTINGS_DICT,
  ...DEPLOY_SETTINGS_DICT,
  ...CONTENT_SETTINGS_DICT,
  ...ACCOUNT_SETTINGS_DICT,
  ...TELEGRAM_SETTINGS_DICT,
  ...QUALITY_SETTINGS_DICT,
  ...PIPELINE_DB_SETTINGS_DICT,
};
