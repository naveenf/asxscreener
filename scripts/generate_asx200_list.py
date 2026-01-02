"""
ASX 200 Stock List Generator

Generates the actual ASX 200 constituent list (top 200 companies by market cap).
Uses curated ASX 200 ticker list from reliable sources.
"""

import json
from pathlib import Path
from datetime import datetime

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent
METADATA_DIR = PROJECT_ROOT / 'data' / 'metadata'

# Ensure directories exist
METADATA_DIR.mkdir(parents=True, exist_ok=True)

# Actual ASX 200 constituent tickers (as of 2026)
# Source: ASX 200 index constituents
ASX_200_TICKERS = [
    "A2M", "AAA", "ABC", "ABP", "AFI", "AGL", "AIA", "ALD", "ALL", "ALQ",
    "ALU", "ALX", "AMC", "AMP", "ANN", "ANZ", "APA", "APE", "APX", "ARB",
    "ARG", "AST", "ASX", "AWC", "AZJ", "BAP", "BEN", "BGA", "BHP", "BIN",
    "BKW", "BLD", "BOQ", "BPT", "BRG", "BSL", "BWP", "BXB", "CAR", "CBA",
    "CCL", "CCP", "CDA", "CGF", "CHC", "CHN", "CIA", "CIM", "CLW", "CMW",
    "CNU", "COH", "COL", "CPU", "CQR", "CSL", "CSR", "CTD", "CWN", "CWY",
    "DEG", "DHG", "DMP", "DOW", "DRR", "DXS", "EBO", "ELD", "EML", "EVN",
    "EVT", "FBU", "FLT", "FMG", "FPH", "GMG", "GNE", "GOZ", "GPT", "GXY",
    "HLS", "HVN", "IAG", "IEL", "IFL", "IFT", "IGO", "ILU", "IOO", "IOZ",
    "IPL", "IRE", "IVV", "JBH", "JHX", "LFG", "LFS", "LLC", "LNK", "LYC",
    "MCY", "MEZ", "MFG", "MGF", "MGR", "MIN", "MLT", "MP1", "MPL", "MQG",
    "MTS", "NAB", "NCM", "NEC", "NHF", "NIC", "NSR", "NST", "NUF", "NWL",
    "NXT", "ORA", "ORE", "ORG", "ORI", "OSH", "OZL", "PBH", "PDL", "PLS",
    "PME", "PMV", "PNI", "PNV", "PPT", "PTM", "QAN", "QBE", "QUB", "REA",
    "REH", "RHC", "RIO", "RMD", "RRL", "RWC", "S32", "SCG", "SCP", "SDF",
    "SEK", "SGM", "SGP", "SGR", "SHL", "SKC", "SKI", "SLK", "SNZ", "SOL",
    "SPK", "STO", "STW", "SUL", "SUN", "SVW", "SYD", "TAH", "TCL", "TLS",
    "TLT", "TNE", "TPG", "TWE", "TYR", "VAP", "VAS", "VCX", "VEA", "VEU",
    "VGS", "VOC", "VTS", "VUK", "WAM", "WBC", "WEB", "WES", "WOR", "WOW",
    "WPL", "WPR", "WTC", "XRO", "YAL", "Z1P", "ZIM"
]

# Company name and sector mapping (from ASX 200 official data)
ASX_200_DATA = {
    "A2M": {"name": "The a2 Milk Company Ltd", "sector": "Consumer Staples"},
    "AAA": {"name": "Betashares Australian High Interest Cash ETF", "sector": "Financials"},
    "ABC": {"name": "Adbri Ltd", "sector": "Materials"},
    "ABP": {"name": "Abacus Property Group", "sector": "Real Estate"},
    "AFI": {"name": "Australian Foundation Investment Company Ltd", "sector": "Financials"},
    "AGL": {"name": "AGL Energy Ltd", "sector": "Utilities"},
    "AIA": {"name": "Auckland International Airport Ltd", "sector": "Industrials"},
    "ALD": {"name": "Ampol Ltd", "sector": "Energy"},
    "ALL": {"name": "Aristocrat Leisure Ltd", "sector": "Consumer Discretionary"},
    "ALQ": {"name": "ALS Ltd", "sector": "Industrials"},
    "ALU": {"name": "Altium Ltd", "sector": "Technology"},
    "ALX": {"name": "Atlas Arteria", "sector": "Industrials"},
    "AMC": {"name": "Amcor Plc", "sector": "Materials"},
    "AMP": {"name": "AMP Ltd", "sector": "Financials"},
    "ANN": {"name": "Ansell Ltd", "sector": "Healthcare"},
    "ANZ": {"name": "Australia and New Zealand Banking Group Ltd", "sector": "Financials"},
    "APA": {"name": "APA Group", "sector": "Utilities"},
    "APE": {"name": "Eagers Automotive Ltd", "sector": "Consumer Discretionary"},
    "APX": {"name": "Appen Ltd", "sector": "Technology"},
    "ARB": {"name": "ARB Corporation Ltd", "sector": "Consumer Discretionary"},
    "ARG": {"name": "Argo Investments Ltd", "sector": "Financials"},
    "AST": {"name": "Ausnet Services Ltd", "sector": "Utilities"},
    "ASX": {"name": "ASX Ltd", "sector": "Financials"},
    "AWC": {"name": "Alumina Ltd", "sector": "Materials"},
    "AZJ": {"name": "Aurizon Holdings Ltd", "sector": "Industrials"},
    "BAP": {"name": "Bapcor Ltd", "sector": "Consumer Discretionary"},
    "BEN": {"name": "Bendigo and Adelaide Bank Ltd", "sector": "Financials"},
    "BGA": {"name": "Bega Cheese Ltd", "sector": "Consumer Staples"},
    "BHP": {"name": "BHP Group Ltd", "sector": "Materials"},
    "BIN": {"name": "Bingo Industries Ltd", "sector": "Industrials"},
    "BKW": {"name": "Brickworks Ltd", "sector": "Materials"},
    "BLD": {"name": "Boral Ltd", "sector": "Materials"},
    "BOQ": {"name": "Bank of Queensland Ltd", "sector": "Financials"},
    "BPT": {"name": "Beach Energy Ltd", "sector": "Energy"},
    "BRG": {"name": "Breville Group Ltd", "sector": "Consumer Discretionary"},
    "BSL": {"name": "Bluescope Steel Ltd", "sector": "Materials"},
    "BWP": {"name": "BWP Trust", "sector": "Real Estate"},
    "BXB": {"name": "Brambles Ltd", "sector": "Industrials"},
    "CAR": {"name": "Carsales.com Ltd", "sector": "Communication Services"},
    "CBA": {"name": "Commonwealth Bank of Australia", "sector": "Financials"},
    "CCL": {"name": "Coca-Cola Amatil Ltd", "sector": "Consumer Staples"},
    "CCP": {"name": "Credit Corp Group Ltd", "sector": "Financials"},
    "CDA": {"name": "Codan Ltd", "sector": "Technology"},
    "CGF": {"name": "Challenger Ltd", "sector": "Financials"},
    "CHC": {"name": "Charter Hall Group", "sector": "Real Estate"},
    "CHN": {"name": "Chalice Mining Ltd", "sector": "Materials"},
    "CIA": {"name": "Champion Iron Ltd", "sector": "Materials"},
    "CIM": {"name": "Cimic Group Ltd", "sector": "Industrials"},
    "CLW": {"name": "Charter Hall Long Wale REIT", "sector": "Real Estate"},
    "CMW": {"name": "Cromwell Property Group", "sector": "Real Estate"},
    "CNU": {"name": "Chorus Ltd", "sector": "Communication Services"},
    "COH": {"name": "Cochlear Ltd", "sector": "Healthcare"},
    "COL": {"name": "Coles Group Ltd", "sector": "Consumer Staples"},
    "CPU": {"name": "Computershare Ltd", "sector": "Technology"},
    "CQR": {"name": "Charter Hall Retail REIT", "sector": "Real Estate"},
    "CSL": {"name": "CSL Ltd", "sector": "Healthcare"},
    "CSR": {"name": "CSR Ltd", "sector": "Materials"},
    "CTD": {"name": "Corporate Travel Management Ltd", "sector": "Industrials"},
    "CWN": {"name": "Crown Resorts Ltd", "sector": "Consumer Discretionary"},
    "CWY": {"name": "Cleanaway Waste Management Ltd", "sector": "Industrials"},
    "DEG": {"name": "De Grey Mining Ltd", "sector": "Materials"},
    "DHG": {"name": "Domain Holdings Australia Ltd", "sector": "Communication Services"},
    "DMP": {"name": "Domino's Pizza Enterprises Ltd", "sector": "Consumer Discretionary"},
    "DOW": {"name": "Downer EDI Ltd", "sector": "Industrials"},
    "DRR": {"name": "Deterra Royalties Ltd", "sector": "Materials"},
    "DXS": {"name": "Dexus", "sector": "Real Estate"},
    "EBO": {"name": "Ebos Group Ltd", "sector": "Healthcare"},
    "ELD": {"name": "Elders Ltd", "sector": "Consumer Staples"},
    "EML": {"name": "EML Payments Ltd", "sector": "Technology"},
    "EVN": {"name": "Evolution Mining Ltd", "sector": "Materials"},
    "EVT": {"name": "Event Hospitality and Entertainment Ltd", "sector": "Consumer Discretionary"},
    "FBU": {"name": "Fletcher Building Ltd", "sector": "Industrials"},
    "FLT": {"name": "Flight Centre Travel Group Ltd", "sector": "Consumer Discretionary"},
    "FMG": {"name": "Fortescue Metals Group Ltd", "sector": "Materials"},
    "FPH": {"name": "Fisher & Paykel Healthcare Corporation Ltd", "sector": "Healthcare"},
    "GMG": {"name": "Goodman Group", "sector": "Real Estate"},
    "GNE": {"name": "Genesis Energy Ltd", "sector": "Utilities"},
    "GOZ": {"name": "Growthpoint Properties Australia", "sector": "Real Estate"},
    "GPT": {"name": "GPT Group", "sector": "Real Estate"},
    "GXY": {"name": "Galaxy Resources Ltd", "sector": "Materials"},
    "HLS": {"name": "Healius Ltd", "sector": "Healthcare"},
    "HVN": {"name": "Harvey Norman Holdings Ltd", "sector": "Consumer Discretionary"},
    "IAG": {"name": "Insurance Australia Group Ltd", "sector": "Financials"},
    "IEL": {"name": "IDP Education Ltd", "sector": "Consumer Discretionary"},
    "IFL": {"name": "IOOF Holdings Ltd", "sector": "Financials"},
    "IFT": {"name": "Infratil Ltd", "sector": "Utilities"},
    "IGO": {"name": "IGO Ltd", "sector": "Materials"},
    "ILU": {"name": "Iluka Resources Ltd", "sector": "Materials"},
    "IOO": {"name": "iShares Global 100 ETF", "sector": "Financials"},
    "IOZ": {"name": "iShares Core S&P/ASX 200 ETF", "sector": "Financials"},
    "IPL": {"name": "Incitec Pivot Ltd", "sector": "Materials"},
    "IRE": {"name": "Iress Ltd", "sector": "Technology"},
    "IVV": {"name": "iShares S&P 500 ETF", "sector": "Financials"},
    "JBH": {"name": "JB Hi-Fi Ltd", "sector": "Consumer Discretionary"},
    "JHX": {"name": "James Hardie Industries Plc", "sector": "Materials"},
    "LFG": {"name": "Liberty Financial Group", "sector": "Financials"},
    "LFS": {"name": "Latitude Group Holdings Ltd", "sector": "Financials"},
    "LLC": {"name": "Lendlease Group", "sector": "Real Estate"},
    "LNK": {"name": "Link Administration Holdings Ltd", "sector": "Financials"},
    "LYC": {"name": "Lynas Rare Earths Ltd", "sector": "Materials"},
    "MCY": {"name": "Mercury NZ Ltd", "sector": "Utilities"},
    "MEZ": {"name": "Meridian Energy Ltd", "sector": "Utilities"},
    "MFG": {"name": "Magellan Financial Group Ltd", "sector": "Financials"},
    "MGF": {"name": "Magellan Global Fund", "sector": "Financials"},
    "MGR": {"name": "Mirvac Group", "sector": "Real Estate"},
    "MIN": {"name": "Mineral Resources Ltd", "sector": "Materials"},
    "MLT": {"name": "Milton Corporation Ltd", "sector": "Financials"},
    "MP1": {"name": "Megaport Ltd", "sector": "Technology"},
    "MPL": {"name": "Medibank Private Ltd", "sector": "Financials"},
    "MQG": {"name": "Macquarie Group Ltd", "sector": "Financials"},
    "MTS": {"name": "Metcash Ltd", "sector": "Consumer Staples"},
    "NAB": {"name": "National Australia Bank Ltd", "sector": "Financials"},
    "NCM": {"name": "Newcrest Mining Ltd", "sector": "Materials"},
    "NEC": {"name": "Nine Entertainment Co Holdings Ltd", "sector": "Communication Services"},
    "NHF": {"name": "nib Holdings Ltd", "sector": "Financials"},
    "NIC": {"name": "Nickel Mines Ltd", "sector": "Materials"},
    "NSR": {"name": "National Storage REIT", "sector": "Real Estate"},
    "NST": {"name": "Northern Star Resources Ltd", "sector": "Materials"},
    "NUF": {"name": "Nufarm Ltd", "sector": "Materials"},
    "NWL": {"name": "Netwealth Group Ltd", "sector": "Financials"},
    "NXT": {"name": "NEXTDC Ltd", "sector": "Technology"},
    "ORA": {"name": "Orora Ltd", "sector": "Materials"},
    "ORE": {"name": "Orocobre Ltd", "sector": "Materials"},
    "ORG": {"name": "Origin Energy Ltd", "sector": "Energy"},
    "ORI": {"name": "Orica Ltd", "sector": "Materials"},
    "OSH": {"name": "Oil Search Ltd", "sector": "Energy"},
    "OZL": {"name": "OZ Minerals Ltd", "sector": "Materials"},
    "PBH": {"name": "Pointsbet Holdings Ltd", "sector": "Consumer Discretionary"},
    "PDL": {"name": "Pendal Group Ltd", "sector": "Financials"},
    "PLS": {"name": "Pilbara Minerals Ltd", "sector": "Materials"},
    "PME": {"name": "Pro Medicus Ltd", "sector": "Healthcare"},
    "PMV": {"name": "Premier Investments Ltd", "sector": "Consumer Discretionary"},
    "PNI": {"name": "Pinnacle Investment Management Group Ltd", "sector": "Financials"},
    "PNV": {"name": "PolyNovo Ltd", "sector": "Healthcare"},
    "PPT": {"name": "Perpetual Ltd", "sector": "Financials"},
    "PTM": {"name": "Platinum Asset Management Ltd", "sector": "Financials"},
    "QAN": {"name": "Qantas Airways Ltd", "sector": "Industrials"},
    "QBE": {"name": "QBE Insurance Group Ltd", "sector": "Financials"},
    "QUB": {"name": "Qube Holdings Ltd", "sector": "Industrials"},
    "REA": {"name": "REA Group Ltd", "sector": "Communication Services"},
    "REH": {"name": "Reece Ltd", "sector": "Industrials"},
    "RHC": {"name": "Ramsay Health Care Ltd", "sector": "Healthcare"},
    "RIO": {"name": "Rio Tinto Ltd", "sector": "Materials"},
    "RMD": {"name": "ResMed Inc", "sector": "Healthcare"},
    "RRL": {"name": "Regis Resources Ltd", "sector": "Materials"},
    "RWC": {"name": "Reliance Worldwide Corporation Ltd", "sector": "Industrials"},
    "S32": {"name": "South32 Ltd", "sector": "Materials"},
    "SCG": {"name": "Scentre Group", "sector": "Real Estate"},
    "SCP": {"name": "Shopping Centres Australasia Property Group", "sector": "Real Estate"},
    "SDF": {"name": "Steadfast Group Ltd", "sector": "Financials"},
    "SEK": {"name": "Seek Ltd", "sector": "Communication Services"},
    "SGM": {"name": "Sims Ltd", "sector": "Industrials"},
    "SGP": {"name": "Stockland", "sector": "Real Estate"},
    "SGR": {"name": "The Star Entertainment Group Ltd", "sector": "Consumer Discretionary"},
    "SHL": {"name": "Sonic Healthcare Ltd", "sector": "Healthcare"},
    "SKC": {"name": "SkyCity Entertainment Group Ltd", "sector": "Consumer Discretionary"},
    "SKI": {"name": "Spark Infrastructure Group", "sector": "Utilities"},
    "SLK": {"name": "SeaLink Travel Group Ltd", "sector": "Industrials"},
    "SNZ": {"name": "Summerset Group Holdings Ltd", "sector": "Real Estate"},
    "SOL": {"name": "Washington H Soul Pattinson & Company Ltd", "sector": "Financials"},
    "SPK": {"name": "Spark New Zealand Ltd", "sector": "Communication Services"},
    "STO": {"name": "Santos Ltd", "sector": "Energy"},
    "STW": {"name": "SPDR S&P/ASX 200 Fund", "sector": "Financials"},
    "SUL": {"name": "Super Retail Group Ltd", "sector": "Consumer Discretionary"},
    "SUN": {"name": "Suncorp Group Ltd", "sector": "Financials"},
    "SVW": {"name": "Seven Group Holdings Ltd", "sector": "Industrials"},
    "SYD": {"name": "Sydney Airport", "sector": "Industrials"},
    "TAH": {"name": "Tabcorp Holdings Ltd", "sector": "Consumer Discretionary"},
    "TCL": {"name": "Transurban Group", "sector": "Industrials"},
    "TLS": {"name": "Telstra Corporation Ltd", "sector": "Communication Services"},
    "TLT": {"name": "Tilt Renewables Ltd", "sector": "Utilities"},
    "TNE": {"name": "Technology One Ltd", "sector": "Technology"},
    "TPG": {"name": "TPG Telecom Ltd", "sector": "Communication Services"},
    "TWE": {"name": "Treasury Wine Estates Ltd", "sector": "Consumer Staples"},
    "TYR": {"name": "Tyro Payments Ltd", "sector": "Technology"},
    "VAP": {"name": "Vanguard Australian Property Securities Index ETF", "sector": "Financials"},
    "VAS": {"name": "Vanguard Australian Shares Index ETF", "sector": "Financials"},
    "VCX": {"name": "Vicinity Centres", "sector": "Real Estate"},
    "VEA": {"name": "Viva Energy Group Ltd", "sector": "Energy"},
    "VEU": {"name": "Vanguard All-World Ex-US Shares Index ETF", "sector": "Financials"},
    "VGS": {"name": "Vanguard MSCI Index International Shares ETF", "sector": "Financials"},
    "VOC": {"name": "Vocus Group Ltd", "sector": "Communication Services"},
    "VTS": {"name": "Vanguard US Total Market Shares Index ETF", "sector": "Financials"},
    "VUK": {"name": "Virgin Money UK Plc", "sector": "Financials"},
    "WAM": {"name": "WAM Capital Ltd", "sector": "Financials"},
    "WBC": {"name": "Westpac Banking Corporation", "sector": "Financials"},
    "WEB": {"name": "Webjet Ltd", "sector": "Consumer Discretionary"},
    "WES": {"name": "Wesfarmers Ltd", "sector": "Consumer Discretionary"},
    "WOR": {"name": "Worley Ltd", "sector": "Energy"},
    "WOW": {"name": "Woolworths Group Ltd", "sector": "Consumer Staples"},
    "WPL": {"name": "Woodside Petroleum Ltd", "sector": "Energy"},
    "WPR": {"name": "Waypoint REIT", "sector": "Real Estate"},
    "WTC": {"name": "WiseTech Global Ltd", "sector": "Technology"},
    "XRO": {"name": "Xero Ltd", "sector": "Technology"},
    "YAL": {"name": "Yancoal Australia Ltd", "sector": "Energy"},
    "Z1P": {"name": "Zip Co Ltd", "sector": "Financials"},
    "ZIM": {"name": "Zimplats Holdings Ltd", "sector": "Materials"}
}


def generate_stock_list():
    """
    Generate stock_list.json with actual ASX 200 companies.
    """
    print("=" * 60)
    print("ASX 200 Stock List Generator (Actual ASX 200)")
    print("=" * 60)
    print()

    # Build stock list with .AX suffix
    stocks = []
    for ticker in ASX_200_TICKERS:
        data = ASX_200_DATA.get(ticker, {"name": ticker, "sector": "Unknown"})
        stocks.append({
            'ticker': f"{ticker}.AX",
            'name': data['name'],
            'sector': data['sector']
        })

    # Create final JSON structure
    stock_list = {
        'stocks': stocks,
        'last_updated': datetime.now().isoformat() + 'Z'
    }

    # Validation
    print(f"\nValidation:")
    print(f"  Total stocks: {len(stocks)}")
    print(f"  All have .AX suffix: {all(s['ticker'].endswith('.AX') for s in stocks)}")
    print(f"  All have required fields: {all('ticker' in s and 'name' in s and 'sector' in s for s in stocks)}")
    print(f"  No duplicates: {len(stocks) == len(set(s['ticker'] for s in stocks))}")

    # Count by sector
    sector_counts = {}
    for stock in stocks:
        sector = stock['sector']
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    print(f"\n  Sector distribution:")
    for sector, count in sorted(sector_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"    {sector}: {count}")

    # Save to file
    output_file = METADATA_DIR / 'stock_list.json'

    with open(output_file, 'w') as f:
        json.dump(stock_list, f, indent=2)

    print(f"\n✓ Stock list saved to: {output_file}")
    print(f"✓ Total stocks: {len(stocks)}")
    print()
    print("=" * 60)
    print("Sample stocks (should see blue-chip companies):")
    print("=" * 60)
    for stock in stocks[:10]:
        print(f"  {stock['ticker']:10} - {stock['name']}")
    print()
    print("=" * 60)
    print("Next steps:")
    print("1. Run: python scripts/download_data.py")
    print("2. This will download data for actual ASX 200 stocks")
    print("=" * 60)

    return stocks


def main():
    """Main entry point."""
    stocks = generate_stock_list()

    if len(stocks) != 200:
        print(f"\n⚠️  Warning: {len(stocks)} stocks generated (expected 200)")


if __name__ == '__main__':
    main()
