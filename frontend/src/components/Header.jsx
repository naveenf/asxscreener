/**
 * Header Component
 *
 * Application header with title, status pills, and refresh button.
 */

import React from 'react';
import { NavLink } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { useAuth } from '../context/AuthContext';
import './Header.css';

function Header({ status, onRefresh, refreshing }) {
  const { user, login, logout } = useAuth();

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

          {user ? (
            <div className="user-profile">
              <nav className="nav-links">
                <NavLink to="/" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                  Screener
                </NavLink>
                <NavLink to="/portfolio" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                  Portfolio
                </NavLink>
              </nav>
              <div className="user-info">
                <span className="user-name">{user.name}</span>
                <button className="logout-button" onClick={logout}>Logout</button>
              </div>
            </div>
          ) : (
            <div className="guest-login">
              <GoogleLogin
                onSuccess={credentialResponse => {
                  login(credentialResponse);
                }}
                onError={(error) => {
                  console.error('Google Login Failed:', error);
                }}
                theme="filled_blue"
                shape="pill"
              />
            </div>
          )}

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
