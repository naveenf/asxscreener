/**
 * Header Component
 *
 * Application header with title, status pills, and refresh button.
 */

import React from 'react';
import { NavLink } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { Search, Sun, Moon } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import './Header.css';

function Header({ status, onRefresh, refreshing, onSearch }) {
  const { user, login, logout } = useAuth();
  const { theme, toggle } = useTheme();

  return (
    <header className="header">
      <div className="header-content">
        <div className="header-left">
          <h1>ASX STOCK SCREENER</h1>
          <p className="subtitle">ASX 300 Pro Dashboard</p>
        </div>

        <div className="header-right">
          {status && (
            <div className="status-info">
              <div className="status-pill">
                <span className="label">Signals</span>
                <span className="value">{status.signals_count}</span>
              </div>
              <div className="status-pill">
                <span className="label">Stocks</span>
                <span className="value">{status.total_stocks}</span>
              </div>
            </div>
          )}
          
          <button className="search-trigger-btn" onClick={onSearch}>
            <Search size={14} /> Analyze
          </button>

          <nav className="nav-links">
            <NavLink to="/" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              Screener
            </NavLink>
            <NavLink to="/forex" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              Forex
            </NavLink>
            {user && (
              <NavLink to="/portfolio" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                Portfolio
              </NavLink>
            )}
            <NavLink to="/insider-trades" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              Insider Trades
            </NavLink>
            {user && (
              <NavLink to="/settings" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                Settings
              </NavLink>
            )}
          </nav>

          {user ? (
            <div className="user-profile">
              <div className="user-info">
                <span className="user-name">{user.name}</span>
                <button className="logout-button" onClick={logout}>Logout</button>
              </div>
            </div>
          ) : (
            <div className="guest-login">
              <GoogleLogin
                onSuccess={async (credentialResponse) => {
                  try {
                    await login(credentialResponse);
                  } catch (err) {
                    console.error('Login failed:', err);
                    alert('Sign-in failed: ' + (err.response?.data?.detail || err.message || 'Unknown error'));
                  }
                }}
                onError={(error) => {
                  console.error('Google Login Failed:', error);
                  alert('Google Sign-In error. Please try again.');
                }}
                theme={theme === 'light' ? 'outline' : 'filled_black'}
                shape="pill"
                size="medium"
              />
            </div>
          )}

          <button
            className="theme-toggle-btn"
            onClick={toggle}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          <button
            className="refresh-button"
            onClick={onRefresh}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
    </header>
  );
}

export default Header;
