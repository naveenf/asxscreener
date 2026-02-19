import React from 'react';

const SummaryCard = ({ title, value, subtext, className = "" }) => {
  return (
    <div className={`summary-card ${className}`}>
      <div className="card-title">{title}</div>
      <div className="card-value">{value}</div>
      {subtext && <div className="card-subtext">{subtext}</div>}
    </div>
  );
};

export default SummaryCard;
