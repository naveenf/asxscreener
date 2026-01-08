✦ I have analyzed your requirement for tracking major institutional transactions.

  Analysis
  Based on my investigation of the yfinance library and the ASX reporting structure:
   * Institutional Data Availability: yfinance provides periodic snapshots of institutional holders (via
     ticker.institutional_holders), but these are typically updated quarterly or half-yearly, meaning they cannot
     provide a reliable "last 2 weeks" transaction feed.
   * Insider Transactions: yfinance does provide a granular feed of Insider Transactions (Directors and Executives) for
     ASX stocks. This data includes the number of shares, the dollar value, the date, and whether it was a Buy or Sell.
   * Net Calculation: We can fulfill the request by aggregating these insider trades over the last 14 days. We will
     calculate the Net Value (Total Buys minus Total Sells) and the Net Shares for each stock.
   * Performance: Fetching transaction data for all ASX 300 stocks is resource-intensive. The best approach is to
     integrate this into the existing "Refresh" pipeline and cache the results in a JSON file to keep the UI fast.
   * Terminology: Since yfinance primarily exposes Insider (Director) trades for the ASX rather than individual Fund
     trades (which are only reported when they cross 5% thresholds via PDFs), we will label this as "Major
     Insider/Director Transactions" to ensure accuracy while still providing the "Major Buys" insight you are looking
     for.

  Implementation Plan
   1. Backend: Transaction Service
       * Create a new service backend/app/services/transaction_tracker.py.
       * Implement a function to iterate through the ASX 300 list and fetch insider_transactions for the last 14 days.
       * Aggregate the data: Group by ticker, calculate Net Value, and determine the predominant action (Net Buy vs. Net
         Sell).
   2. Backend: Integration & Caching
       * Update the /api/refresh logic in backend/app/api/routes.py to trigger this tracker during the global data
         refresh.
       * Save the summary to data/processed/major_transactions.json.
   3. Backend: API Endpoint
       * Add GET /api/major-transactions to return the 14-day summary, sorted by the highest dollar value movements.
   4. Frontend: Dashboard Component
       * Create a new component MajorMoves.jsx to display a summary table of these transactions.
       * Add this section to the main Screener dashboard (e.g., as a sidebar or a top-level summary row).
       * Use green/red indicators for Net Buy/Sell and format values in AUD.
   5. Final Step: Await user approval.

  Would you like me to proceed with this plan to track Insider/Major transactions?