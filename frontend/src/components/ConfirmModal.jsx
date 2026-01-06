import React from 'react';
import './ConfirmModal.css';

const ConfirmModal = ({ title, message, onConfirm, onCancel }) => {
  return (
    <div className="portfolio-overlay">
      <div className="portfolio-modal confirm-modal">
        <div className="portfolio-header">
          <h2>{title || 'CONFIRM ACTION'}</h2>
          <button className="close-button" onClick={onCancel}>×</button>
        </div>
        
        <div className="confirm-body">
          <p>{message}</p>
        </div>

        <div className="confirm-footer">
          <button className="cancel-btn" onClick={onCancel}>Cancel</button>
          <button className="confirm-btn" onClick={onConfirm}>Confirm</button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmModal;
