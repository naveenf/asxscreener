/**
 * Settings Component
 *
 * Allows the admin user to enable/disable individual pair+strategy combos.
 * All logged-in users can view; only the admin can save.
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getStrategyOverrides, updateStrategyOverrides } from '../services/api';
import styles from './Settings.module.css';

function Settings({ onShowToast }) {
  const { user, loading: authLoading } = useAuth();
  const [combos, setCombos] = useState([]);
  const [disabled, setDisabled] = useState(new Set());
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    loadOverrides();
  }, [user]);

  const loadOverrides = async () => {
    setLoading(true);
    try {
      const data = await getStrategyOverrides();
      setCombos(data.combos || []);
      setDisabled(new Set(data.disabled || []));
      setIsAdmin(data.is_admin || false);
    } catch (err) {
      onShowToast({ message: 'Failed to load strategy settings', type: 'error' });
    } finally {
      setLoading(false);
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

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateStrategyOverrides([...disabled]);
      onShowToast({ message: 'Strategy settings saved. Takes effect on next screener run.', type: 'success' });
    } catch (err) {
      onShowToast({ message: err.message || 'Failed to save', type: 'error' });
    } finally {
      setSaving(false);
    }
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
              return (
                <div key={combo.key} className={styles.row}>
                  <span className={styles.strategyName}>{combo.strategy}</span>
                  <span className={styles.timeframe}>{combo.timeframe}</span>
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
            {disabled.size} combo{disabled.size !== 1 ? 's' : ''} disabled
          </span>
        </div>
      )}
    </div>
  );
}

export default Settings;
