import { useCallback, useEffect, useMemo, useState } from 'react';
import campaignRuleService from '../services/campaignRuleService';

const useCampaignRulesEditor = (t) => {
  const [active, setActive] = useState(null);
  const [schema, setSchema] = useState([]);
  const [values, setValues] = useState({});
  const [originalValues, setOriginalValues] = useState({});
  const [reason, setReason] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [conflict, setConflict] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [history, setHistory] = useState([]);

  const loadCurrent = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await campaignRuleService.getCurrent();
      setActive(data.active);
      setSchema(data.schema || []);
      setValues({ ...data.active.values });
      setOriginalValues({ ...data.active.values });
      setReason('');
      setFieldErrors({});
      setConflict(null);
      setMessage(null);
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.detail || t(
        'admin_campaign_rules_load_error',
        'Не удалось загрузить правила кампании',
      ) });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { loadCurrent(); }, [loadCurrent]);

  const changes = useMemo(() => Object.fromEntries(
    schema
      .filter((rule) => Number(values[rule.key]) !== Number(originalValues[rule.key]))
      .map((rule) => [rule.key, Number(values[rule.key])]),
  ), [originalValues, schema, values]);

  const categories = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return schema.reduce((grouped, rule) => {
      const label = t(rule.label_key, rule.key).toLocaleLowerCase();
      if (needle && !label.includes(needle) && !rule.key.toLowerCase().includes(needle)) return grouped;
      if (!grouped[rule.category]) grouped[rule.category] = [];
      grouped[rule.category].push(rule);
      return grouped;
    }, {});
  }, [schema, search, t]);

  const applyError = (error) => {
    const detail = error.response?.data?.detail;
    if (error.response?.status === 409 && detail?.active_version) {
      setConflict(detail);
      return;
    }
    const errors = detail?.errors || (Array.isArray(detail) ? detail : []);
    if (error.response?.status === 422 && errors.length) {
      setFieldErrors(Object.fromEntries(errors.map((item) => [
        item.field || item.loc?.at(-1), item.message || item.msg,
      ])));
    }
    setMessage({ type: 'error', text: t(
      'admin_campaign_rules_save_error',
      'Не удалось сохранить правила',
    ) });
  };

  const save = async () => {
    setSaving(true);
    setMessage(null);
    setConflict(null);
    setFieldErrors({});
    try {
      await campaignRuleService.update({
        expected_version: active.version,
        reason: reason.trim(),
        changes,
      });
      await loadCurrent();
      setMessage({ type: 'success', text: t(
        'admin_campaign_rules_save_success',
        'Новая версия правил активирована',
      ) });
    } catch (error) {
      applyError(error);
    } finally {
      setSaving(false);
    }
  };

  const openHistory = async () => {
    setHistoryOpen(true);
    setHistoryLoading(true);
    setMessage(null);
    try {
      const { data } = await campaignRuleService.getHistory();
      setHistory(data.items || []);
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.detail || t(
        'admin_campaign_rules_history_error',
        'Не удалось загрузить историю',
      ) });
    } finally {
      setHistoryLoading(false);
    }
  };

  const restore = async (version, restoreReason) => {
    setSaving(true);
    setMessage(null);
    try {
      await campaignRuleService.restore(version, {
        expected_version: active.version,
        reason: restoreReason,
      });
      await loadCurrent();
      setMessage({ type: 'success', text: t(
        'admin_campaign_rules_restore_success',
        'Версия восстановлена как новая активная версия',
      ) });
      return true;
    } catch (error) {
      applyError(error);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const changeValue = (key, value) => {
    setValues((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => ({ ...current, [key]: undefined }));
  };

  return {
    active, categories, changes, conflict, fieldErrors, history, historyLoading,
    historyOpen, loading, message, openHistory, originalValues, reason, restore,
    save, saving, search, setHistoryOpen, setReason, setSearch, values,
    changeValue, loadCurrent,
  };
};

export default useCampaignRulesEditor;
