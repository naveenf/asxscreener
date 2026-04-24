/**
 * Settings Component
 *
 * Allows the admin user to enable/disable individual pair+strategy combos.
 * All logged-in users can view; only the admin can save.
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getStrategyOverrides, updateStrategyOverrides, getMarketHolidays, updateMarketHolidays, getTradeSettings, updateTradeSettings } from '../services/api';
import styles from './Settings.module.css';

// Display names shown in the holiday "affects" multi-select
const PAIR_DISPLAY_NAMES = {
  'XAU_USD':    'XAU/USD',
  'XAG_USD':    'XAG/USD',
  'JP225_USD':  'JP225',
  'NAS100_USD': 'NAS100',
  'EUR_USD':    'EUR/USD',
  'UK100_GBP':  'UK100',
  'BCO_USD':    'BCO',
  'USD_JPY':    'USD/JPY',
};
const ALL_PAIRS = Object.keys(PAIR_DISPLAY_NAMES);

function formatHolidayDate(dateStr) {
  // "2026-04-03" → "03 Apr 2026"
  try {
    const d = new Date(dateStr + 'T00:00:00Z');
    return d.toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
  } catch {
    return dateStr;
  }
}

function formatAffects(affects) {
  if (affects === 'all') return 'All pairs';
  if (Array.isArray(affects)) {
    return affects.map(p => PAIR_DISPLAY_NAMES[p] || p).join(', ');
  }
  return String(affects);
}

function Settings({ onShowToast }) {
  const { user, loading: authLoading } = useAuth();

  // Strategy overrides state
  const [combos, setCombos] = useState([]);
  const [disabled, setDisabled] = useState(new Set());
  const [directionOverrides, setDirectionOverrides] = useState({});
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Trade settings state
  const [holidayCloseEnabled, setHolidayCloseEnabled] = useState(true);
  const [tradeSettingsLoading, setTradeSettingsLoading] = useState(true);
  const [tradeSettingsSaving, setTradeSettingsSaving] = useState(false);

  // Holiday calendar state
  const [holidays, setHolidays] = useState([]);
  const [holidaysLoading, setHolidaysLoading] = useState(true);
  const [holidaysSaving, setHolidaysSaving] = useState(false);
  // New-row form state
  const [newDate, setNewDate] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [newAffectsAll, setNewAffectsAll] = useState(true);
  const [newAffectsPairs, setNewAffectsPairs] = useState([]);

  useEffect(() => {
    if (!user) return;
    loadOverrides();
    loadHolidays();
    loadTradeSettings();
  }, [user]);

  const loadOverrides = async () => {
    setLoading(true);
    try {
      const data = await getStrategyOverrides();
      setCombos(data.combos || []);
      setDisabled(new Set(data.disabled || []));
      setDirectionOverrides(data.direction_overrides || {});
      setIsAdmin(data.is_admin || false);
    } catch (err) {
      onShowToast({ message: 'Failed to load strategy settings', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const loadTradeSettings = async () => {
    setTradeSettingsLoading(true);
    try {
      const data = await getTradeSettings();
      setHolidayCloseEnabled(data.holiday_close_enabled ?? true);
      // Also set isAdmin from this response so the toggle is correctly disabled
      // even if loadTradeSettings resolves before loadOverrides.
      if (data.is_admin) setIsAdmin(true);
    } catch (err) {
      onShowToast({ message: 'Failed to load trade settings', type: 'error' });
    } finally {
      setTradeSettingsLoading(false);
    }
  };

  const handleHolidayCloseToggle = async () => {
    if (!isAdmin) return;
    const newValue = !holidayCloseEnabled;
    setHolidayCloseEnabled(newValue);
    setTradeSettingsSaving(true);
    try {
      await updateTradeSettings({ holiday_close_enabled: newValue });
      onShowToast({
        message: newValue
          ? 'Holiday close enabled — positions will be closed before holidays.'
          : 'Holiday close disabled — positions will stay open through holidays.',
        type: 'success',
      });
    } catch (err) {
      setHolidayCloseEnabled(!newValue); // revert on failure
      onShowToast({ message: err.message || 'Failed to save trade settings', type: 'error' });
    } finally {
      setTradeSettingsSaving(false);
    }
  };

  const loadHolidays = async () => {
    setHolidaysLoading(true);
    try {
      const data = await getMarketHolidays();
      setHolidays(data.holidays || []);
    } catch (err) {
      onShowToast({ message: 'Failed to load holiday calendar', type: 'error' });
    } finally {
      setHolidaysLoading(false);
    }
  };

  const handleToggle = (key) => {
    if (!isAdmin) return;
    setDisabled(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleDirectionChange = (key, value) => {
    if (!isAdmin) return;
    setDirectionOverrides(prev => {
      const next = { ...prev };
      if (value === 'both') {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateStrategyOverrides([...disabled], directionOverrides);
      onShowToast({ message: 'Strategy settings saved. Takes effect on next screener run.', type: 'success' });
    } catch (err) {
      onShowToast({ message: err.message || 'Failed to save', type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  // --- Holiday handlers ---
  const handleAddHoliday = () => {
    if (!newDate || !newLabel.trim()) {
      onShowToast({ message: 'Date and label are required', type: 'error' });
      return;
    }
    const affects = newAffectsAll ? 'all' : newAffectsPairs;
    if (!newAffectsAll && newAffectsPairs.length === 0) {
      onShowToast({ message: 'Select at least one pair or choose "All pairs"', type: 'error' });
      return;
    }
    setHolidays(prev => [...prev, { date: newDate, label: newLabel.trim(), affects }]);
    setNewDate('');
    setNewLabel('');
    setNewAffectsAll(true);
    setNewAffectsPairs([]);
  };

  const handleRemoveHoliday = (idx) => {
    setHolidays(prev => prev.filter((_, i) => i !== idx));
  };

  const handleSaveHolidays = async () => {
    setHolidaysSaving(true);
    try {
      await updateMarketHolidays(holidays);
      onShowToast({ message: 'Holiday calendar saved.', type: 'success' });
    } catch (err) {
      onShowToast({ message: err.message || 'Failed to save holidays', type: 'error' });
    } finally {
      setHolidaysSaving(false);
    }
  };

  const toggleNewAffectsPair = (pair) => {
    setNewAffectsPairs(prev =>
      prev.includes(pair) ? prev.filter(p => p !== pair) : [...prev, pair]
    );
  };

  // Group combos by pair
  const grouped = combos.reduce((acc, combo) => {
    if (!acc[combo.pair]) acc[combo.pair] = [];
    acc[combo.pair].push(combo);
    return acc;
  }, {});

  if (authLoading) {
    return (
      <div className={styles.container}>
        <p className={styles.loading}>Loading...</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className={styles.container}>
        <p className={styles.authMessage}>Please log in to view strategy settings.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className={styles.container}>
        <p className={styles.loading}>Loading strategy settings...</p>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>Strategy Controls</h2>
        <p className={styles.subtitle}>
          Enable or disable pair/strategy combinations. Changes apply from the next screener run.
          {!isAdmin && <span className={styles.readOnlyBadge}> Read-only</span>}
        </p>
      </div>

      <div className={styles.groups}>
        {Object.entries(grouped).map(([pair, pairCombos]) => (
          <div key={pair} className={styles.group}>
            <h3 className={styles.pairHeader}>{pair.replaceAll('_', '/')}</h3>
            {pairCombos.map(combo => {
              const isEnabled = !disabled.has(combo.key);
              const direction = directionOverrides[combo.key] || 'both';
              return (
                <div key={combo.key} className={styles.row}>
                  <span className={styles.strategyName}>{combo.strategy}</span>
                  <span className={styles.timeframe}>{combo.timeframe}</span>
                  <div className={`${styles.directionGroup} ${!isAdmin || !isEnabled ? styles.readOnly : ''}`}>
                    {['both', 'buy', 'sell'].map(opt => (
                      <button
                        key={opt}
                        className={`${styles.directionBtn} ${direction === opt ? styles.directionBtnActive : ''} ${styles[`directionBtn_${opt}`]}`}
                        onClick={() => handleDirectionChange(combo.key, opt)}
                        disabled={!isAdmin || !isEnabled}
                        title={opt === 'both' ? 'Both directions' : opt === 'buy' ? 'Buy only' : 'Sell only'}
                      >
                        {opt === 'both' ? '⇅' : opt === 'buy' ? '↑' : '↓'}
                      </button>
                    ))}
                  </div>
                  <label className={`${styles.toggle} ${!isAdmin ? styles.readOnly : ''}`}>
                    <input
                      type="checkbox"
                      checked={isEnabled}
                      onChange={() => handleToggle(combo.key)}
                      disabled={!isAdmin}
                    />
                    <span className={styles.slider} />
                    <span className={styles.toggleLabel}>{isEnabled ? 'ON' : 'OFF'}</span>
                  </label>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {isAdmin && (
        <div className={styles.footer}>
          <button
            className={styles.saveButton}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
          <span className={styles.disabledCount}>
            {disabled.size} disabled · {Object.keys(directionOverrides).length} direction{Object.keys(directionOverrides).length !== 1 ? 's' : ''} locked
          </span>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Trade Settings card                                                 */}
      {/* ------------------------------------------------------------------ */}
      <div className={styles.holidayCard}>
        <div className={styles.holidayCardHeader}>
          <h3 className={styles.holidayCardTitle}>Trade Settings</h3>
          <p className={styles.holidayCardSubtitle}>
            Global trade behaviour controls.
            {!isAdmin && <span className={styles.readOnlyBadge}> Read-only</span>}
          </p>
        </div>

        {tradeSettingsLoading ? (
          <p className={styles.loading}>Loading...</p>
        ) : (
          <div className={styles.tradeSettingRow}>
            <div className={styles.tradeSettingInfo}>
              <span className={styles.tradeSettingLabel}>Close positions before holidays</span>
              <span className={styles.tradeSettingDesc}>
                {holidayCloseEnabled
                  ? 'ON — open positions are closed 1 hour before market close on the preceding trading day.'
                  : 'OFF — positions remain open through holidays and weekends. New entries are still blocked during the pre-close window.'}
              </span>
            </div>
            <label className={`${styles.toggle} ${!isAdmin ? styles.readOnly : ''}`}>
              <input
                type="checkbox"
                checked={holidayCloseEnabled}
                onChange={handleHolidayCloseToggle}
                disabled={!isAdmin || tradeSettingsSaving}
              />
              <span className={styles.slider} />
              <span className={styles.toggleLabel}>{holidayCloseEnabled ? 'ON' : 'OFF'}</span>
            </label>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Holiday Calendar card                                               */}
      {/* ------------------------------------------------------------------ */}
      <div className={styles.holidayCard}>
        <div className={styles.holidayCardHeader}>
          <h3 className={styles.holidayCardTitle}>Holiday Calendar</h3>
          <p className={styles.holidayCardSubtitle}>
            Positions are closed 1 hour before market close on the trading day preceding each holiday.
            {!isAdmin && <span className={styles.readOnlyBadge}> Read-only</span>}
          </p>
        </div>

        {holidaysLoading ? (
          <p className={styles.loading}>Loading holidays...</p>
        ) : (
          <>
            {holidays.length === 0 ? (
              <p className={styles.holidayEmpty}>No holidays configured. Weekly Friday closes apply by default.</p>
            ) : (
              <table className={styles.holidayTable}>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Label</th>
                    <th>Affects</th>
                    {isAdmin && <th></th>}
                  </tr>
                </thead>
                <tbody>
                  {holidays
                    .map((h, origIdx) => ({ h, origIdx }))
                    .sort((a, b) => a.h.date.localeCompare(b.h.date))
                    .map(({ h, origIdx }) => (
                      <tr key={origIdx}>
                        <td className={styles.holidayDate}>{formatHolidayDate(h.date)}</td>
                        <td>{h.label}</td>
                        <td className={styles.holidayAffects}>{formatAffects(h.affects)}</td>
                        {isAdmin && (
                          <td>
                            <button
                              className={styles.removeBtn}
                              onClick={() => handleRemoveHoliday(origIdx)}
                              title="Remove holiday"
                            >
                              Remove
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                </tbody>
              </table>
            )}

            {isAdmin && (
              <div className={styles.holidayAddRow}>
                <input
                  type="date"
                  className={styles.holidayInput}
                  value={newDate}
                  onChange={e => setNewDate(e.target.value)}
                  title="Holiday date (the day markets are CLOSED)"
                />
                <input
                  type="text"
                  className={styles.holidayInput}
                  placeholder="Label (e.g. Good Friday)"
                  value={newLabel}
                  onChange={e => setNewLabel(e.target.value)}
                />
                <div className={styles.affectsGroup}>
                  <label className={styles.affectsAllLabel}>
                    <input
                      type="checkbox"
                      checked={newAffectsAll}
                      onChange={e => setNewAffectsAll(e.target.checked)}
                    />
                    <span>All pairs</span>
                  </label>
                  {!newAffectsAll && (
                    <div className={styles.affectsPairGrid}>
                      {ALL_PAIRS.map(pair => (
                        <label key={pair} className={styles.affectsPairLabel}>
                          <input
                            type="checkbox"
                            checked={newAffectsPairs.includes(pair)}
                            onChange={() => toggleNewAffectsPair(pair)}
                          />
                          <span>{PAIR_DISPLAY_NAMES[pair]}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <button className={styles.addHolidayBtn} onClick={handleAddHoliday}>
                  Add
                </button>
              </div>
            )}

            {isAdmin && (
              <div className={styles.holidayFooter}>
                <button
                  className={styles.saveButton}
                  onClick={handleSaveHolidays}
                  disabled={holidaysSaving}
                >
                  {holidaysSaving ? 'Saving...' : 'Save Holiday Calendar'}
                </button>
                <span className={styles.disabledCount}>{holidays.length} holiday{holidays.length !== 1 ? 's' : ''}</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default Settings;
