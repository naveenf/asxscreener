import React, { useEffect } from 'react';
import './Toast.css';

const Toast = ({ message, type = 'success', onClose }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, 3000);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div className={`toast-container ${type}`}>
      <div className="toast-content">
        <span className="toast-icon">
          {type === 'success' ? '✓' : 'ℹ'}
        </span>
        <span className="toast-message">{message}</span>
      </div>
      <div className="toast-progress"></div>
    </div>
  );
};

export default Toast;
