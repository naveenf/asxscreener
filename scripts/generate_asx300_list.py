"""
ASX 300 Stock List Generator
Auto-generated from provided list.
"""
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
METADATA_DIR = PROJECT_ROOT / "data" / "metadata"
METADATA_DIR.mkdir(parents=True, exist_ok=True)

STOCKS_DATA = [
    {
        "ticker": "4DX",
        "name": "4DMedical"
    },
    {
        "ticker": "ABG",
        "name": "Abacus Group"
    },
    {
        "ticker": "ASK",
        "name": "Abacus Storage King"
    },
    {
        "ticker": "AGL",
        "name": "AGL Energy"
    },
    {
        "ticker": "AIZ",
        "name": "Air New Zealand"
    },
    {
        "ticker": "AAI",
        "name": "Alcoa Corporation"
    },
    {
        "ticker": "ALK",
        "name": "Alkane Resources"
    },
    {
        "ticker": "A4N",
        "name": "Alpha HPA"
    },
    {
        "ticker": "ALQ",
        "name": "ALS"
    },
    {
        "ticker": "AMC",
        "name": "Amcor Plc"
    },
    {
        "ticker": "AOV",
        "name": "Amotiv"
    },
    {
        "ticker": "AMP",
        "name": "AMP"
    },
    {
        "ticker": "ALD",
        "name": "Ampol"
    },
    {
        "ticker": "ANN",
        "name": "Ansell"
    },
    {
        "ticker": "ANZ",
        "name": "ANZ Group Holdings"
    },
    {
        "ticker": "APA",
        "name": "APA Group"
    },
    {
        "ticker": "ARU",
        "name": "Arafura Rare Earths"
    },
    {
        "ticker": "ARB",
        "name": "ARB Corporation"
    },
    {
        "ticker": "ARF",
        "name": "Arena REIT"
    },
    {
        "ticker": "ARG",
        "name": "Argo Investments"
    },
    {
        "ticker": "ALL",
        "name": "Aristocrat Leisure"
    },
    {
        "ticker": "APZ",
        "name": "Aspen Group"
    },
    {
        "ticker": "ASX",
        "name": "ASX"
    },
    {
        "ticker": "ALX",
        "name": "Atlas Arteria"
    },
    {
        "ticker": "AUB",
        "name": "AUB Group"
    },
    {
        "ticker": "AIA",
        "name": "Auckland International Airport"
    },
    {
        "ticker": "AZJ",
        "name": "Aurizon Holdings"
    },
    {
        "ticker": "ABB",
        "name": "Aussie Broadband"
    },
    {
        "ticker": "ASB",
        "name": "Austal"
    },
    {
        "ticker": "AFI",
        "name": "Australian Foundation Investment Company"
    },
    {
        "ticker": "AUI",
        "name": "Australian United Investment Company"
    },
    {
        "ticker": "BOQ",
        "name": "Bank of Queensland"
    },
    {
        "ticker": "BCI",
        "name": "BCI Minerals"
    },
    {
        "ticker": "BPT",
        "name": "Beach Energy"
    },
    {
        "ticker": "BAP",
        "name": "Bapcor Ltd"
    },
    {
        "ticker": "BGA",
        "name": "Bega Cheese"
    },
    {
        "ticker": "BGL",
        "name": "Bellevue Gold"
    },
    {
        "ticker": "BEN",
        "name": "Bendigo and Adelaide Bank"
    },
    {
        "ticker": "BHP",
        "name": "BHP Group"
    },
    {
        "ticker": "BKI",
        "name": "BKI Investment Company"
    },
    {
        "ticker": "BC8",
        "name": "Black Cat Syndicate"
    },
    {
        "ticker": "XYZ",
        "name": "Block, Inc."
    },
    {
        "ticker": "BSL",
        "name": "BlueScope Steel"
    },
    {
        "ticker": "BXB",
        "name": "Brambles"
    },
    {
        "ticker": "BVS",
        "name": "Bravura Solutions"
    },
    {
        "ticker": "BRE",
        "name": "Brazilian Rare Earths"
    },
    {
        "ticker": "BRG",
        "name": "Breville Group"
    },
    {
        "ticker": "BGP",
        "name": "Briscoe Group Australasia"
    },
    {
        "ticker": "BFL",
        "name": "BSP Financial Group"
    },
    {
        "ticker": "BWP",
        "name": "BWP Trust"
    },
    {
        "ticker": "CMM",
        "name": "Capricorn Metals"
    },
    {
        "ticker": "CSC",
        "name": "Capstone Copper Corp."
    },
    {
        "ticker": "CAR",
        "name": "CAR Group"
    },
    {
        "ticker": "CYL",
        "name": "Catalyst Metals"
    },
    {
        "ticker": "CAT",
        "name": "Catapult Sports"
    },
    {
        "ticker": "CNI",
        "name": "Centuria Capital Group"
    },
    {
        "ticker": "CIP",
        "name": "Centuria Industrial REIT"
    },
    {
        "ticker": "CGF",
        "name": "Challenger"
    },
    {
        "ticker": "CIA",
        "name": "Champion Iron"
    },
    {
        "ticker": "CHC",
        "name": "Charter Hall Group"
    },
    {
        "ticker": "CLW",
        "name": "Charter Hall Long Wale REIT"
    },
    {
        "ticker": "CQR",
        "name": "Charter Hall Retail REIT"
    },
    {
        "ticker": "CQE",
        "name": "Charter Hall Social Infrastructure REIT"
    },
    {
        "ticker": "CNU",
        "name": "Chorus"
    },
    {
        "ticker": "CHI",
        "name": "Churchill Leisure Industries"
    },
    {
        "ticker": "CU6",
        "name": "Clarity Pharmaceuticals"
    },
    {
        "ticker": "CWY",
        "name": "Cleanaway Waste Management"
    },
    {
        "ticker": "CBO",
        "name": "Cobram Estate Olives"
    },
    {
        "ticker": "COH",
        "name": "Cochlear"
    },
    {
        "ticker": "CDA",
        "name": "Codan"
    },
    {
        "ticker": "COL",
        "name": "Coles Group"
    },
    {
        "ticker": "CKF",
        "name": "Collins Foods"
    },
    {
        "ticker": "CBA",
        "name": "Commonwealth Bank of Australia"
    },
    {
        "ticker": "CPU",
        "name": "Computershare"
    },
    {
        "ticker": "CEN",
        "name": "Contact Energy"
    },
    {
        "ticker": "CTD",
        "name": "Corporate Travel Management"
    },
    {
        "ticker": "CCP",
        "name": "Credit Corp Group"
    },
    {
        "ticker": "CMW",
        "name": "Cromwell Property Group"
    },
    {
        "ticker": "CSL",
        "name": "CSL"
    },
    {
        "ticker": "DBI",
        "name": "Dalrymple Bay Infrastructure"
    },
    {
        "ticker": "DTL",
        "name": "Data3"
    },
    {
        "ticker": "DTR",
        "name": "Dateline Resources"
    },
    {
        "ticker": "DYL",
        "name": "Deep Yellow"
    },
    {
        "ticker": "DRR",
        "name": "Deterra Royalties"
    },
    {
        "ticker": "DVP",
        "name": "Develop Global"
    },
    {
        "ticker": "DXS",
        "name": "Dexus"
    },
    {
        "ticker": "DDR",
        "name": "Dicker Data"
    },
    {
        "ticker": "DGT",
        "name": "Digico Infrastructure REIT"
    },
    {
        "ticker": "DUI",
        "name": "Diversified United Investment"
    },
    {
        "ticker": "DMP",
        "name": "Domino's Pizza Enterprises"
    },
    {
        "ticker": "DOW",
        "name": "Downer EDI"
    },
    {
        "ticker": "DPM",
        "name": "DPM Metals Inc."
    },
    {
        "ticker": "DRO",
        "name": "DroneShield"
    },
    {
        "ticker": "DNL",
        "name": "Dyno Nobel"
    },
    {
        "ticker": "APE",
        "name": "Eagers Automotive"
    },
    {
        "ticker": "EBO",
        "name": "EBOS Group"
    },
    {
        "ticker": "ELD",
        "name": "Elders"
    },
    {
        "ticker": "EOS",
        "name": "Electro Optic Systems Holdings"
    },
    {
        "ticker": "ELV",
        "name": "Elevra Lithium"
    },
    {
        "ticker": "EMR",
        "name": "Emerald Resources NL"
    },
    {
        "ticker": "EDV",
        "name": "Endeavour Group"
    },
    {
        "ticker": "ERA",
        "name": "Energy Resources of Australia"
    },
    {
        "ticker": "EVN",
        "name": "Evolution Mining"
    },
    {
        "ticker": "EVT",
        "name": "EVT"
    },
    {
        "ticker": "FCL",
        "name": "FINEOS Corporation Holdings PLC"
    },
    {
        "ticker": "FFM",
        "name": "FireFly Metals"
    },
    {
        "ticker": "FPH",
        "name": "Fisher & Paykel Healthcare Corporation"
    },
    {
        "ticker": "FBU",
        "name": "Fletcher Building"
    },
    {
        "ticker": "FLT",
        "name": "Flight Centre Travel Group"
    },
    {
        "ticker": "FML",
        "name": "Focus Minerals"
    },
    {
        "ticker": "FMG",
        "name": "Fortescue"
    },
    {
        "ticker": "FRW",
        "name": "Freightways Group"
    },
    {
        "ticker": "GLF",
        "name": "Gemlife Communities Group"
    },
    {
        "ticker": "GDG",
        "name": "Generation Development Group"
    },
    {
        "ticker": "GNE",
        "name": "Genesis Energy"
    },
    {
        "ticker": "GMD",
        "name": "Genesis Minerals"
    },
    {
        "ticker": "GNP",
        "name": "GenusPlus Group"
    },
    {
        "ticker": "GMG",
        "name": "Goodman Group"
    },
    {
        "ticker": "GPT",
        "name": "GPT Group"
    },
    {
        "ticker": "GQG",
        "name": "GQG Partners Inc."
    },
    {
        "ticker": "GNC",
        "name": "Graincorp"
    },
    {
        "ticker": "GGP",
        "name": "Greatland Resources"
    },
    {
        "ticker": "GOZ",
        "name": "Growthpoint Properties Australia"
    },
    {
        "ticker": "GCI",
        "name": "Gryphon Capital Income Trust"
    },
    {
        "ticker": "GYG",
        "name": "Guzman Y Gomez"
    },
    {
        "ticker": "HSN",
        "name": "Hansen Technologies"
    },
    {
        "ticker": "HVN",
        "name": "Harvey Norman Holdings"
    },
    {
        "ticker": "HLI",
        "name": "Helia Group"
    },
    {
        "ticker": "HMC",
        "name": "HMC Capital"
    },
    {
        "ticker": "HDN",
        "name": "HomeCo Daily Needs REIT"
    },
    {
        "ticker": "HUB",
        "name": "HUB24"
    },
    {
        "ticker": "IEL",
        "name": "IDP Education"
    },
    {
        "ticker": "IGO",
        "name": "IGO"
    },
    {
        "ticker": "ILU",
        "name": "Iluka Resources"
    },
    {
        "ticker": "IMD",
        "name": "Imdex"
    },
    {
        "ticker": "IFT",
        "name": "Infratil"
    },
    {
        "ticker": "INA",
        "name": "Ingenia Communities Group"
    },
    {
        "ticker": "IFL",
        "name": "Insignia Financial"
    },
    {
        "ticker": "IAG",
        "name": "Insurance Australia Group"
    },
    {
        "ticker": "IPX",
        "name": "IperionX"
    },
    {
        "ticker": "IRE",
        "name": "IRESS"
    },
    {
        "ticker": "JHX",
        "name": "James Hardie Industries Plc"
    },
    {
        "ticker": "JBH",
        "name": "JB Hi-Fi"
    },
    {
        "ticker": "JDO",
        "name": "Judo Capital Holdings"
    },
    {
        "ticker": "KAR",
        "name": "Karoon Energy"
    },
    {
        "ticker": "KLS",
        "name": "Kelsian Group"
    },
    {
        "ticker": "KCN",
        "name": "Kingsgate Consolidated"
    },
    {
        "ticker": "GLS",
        "name": "L1 Global Long Short Fund"
    },
    {
        "ticker": "L1G",
        "name": "L1 Group"
    },
    {
        "ticker": "LSF",
        "name": "L1 Long Short Fund"
    },
    {
        "ticker": "LFS",
        "name": "Latitude Group Holdings"
    },
    {
        "ticker": "LLC",
        "name": "LendLease Group"
    },
    {
        "ticker": "LFG",
        "name": "Liberty Financial Group"
    },
    {
        "ticker": "360",
        "name": "Life360 Inc"
    },
    {
        "ticker": "LNW",
        "name": "Light & Wonder Inc."
    },
    {
        "ticker": "LTR",
        "name": "Liontown"
    },
    {
        "ticker": "LOV",
        "name": "Lovisa Holdings"
    },
    {
        "ticker": "LYC",
        "name": "Lynas Rare Earths"
    },
    {
        "ticker": "MAF",
        "name": "MA Financial Group"
    },
    {
        "ticker": "MGH",
        "name": "MAAS Group Holdings"
    },
    {
        "ticker": "MAH",
        "name": "Macmahon Holdings"
    },
    {
        "ticker": "MQG",
        "name": "Macquarie Group"
    },
    {
        "ticker": "MAQ",
        "name": "Macquarie Technology Group"
    },
    {
        "ticker": "MAD",
        "name": "Mader Group"
    },
    {
        "ticker": "MFG",
        "name": "Magellan Financial Group"
    },
    {
        "ticker": "MMS",
        "name": "McMillan Shakespeare"
    },
    {
        "ticker": "MPL",
        "name": "Medibank Private"
    },
    {
        "ticker": "MP1",
        "name": "Megaport"
    },
    {
        "ticker": "MCY",
        "name": "Mercury NZ"
    },
    {
        "ticker": "MEZ",
        "name": "Meridian Energy"
    },
    {
        "ticker": "MSB",
        "name": "Mesoblast"
    },
    {
        "ticker": "MLX",
        "name": "Metals X"
    },
    {
        "ticker": "MTS",
        "name": "Metcash"
    },
    {
        "ticker": "MXT",
        "name": "Metrics Master Income Trust"
    },
    {
        "ticker": "MFF",
        "name": "MFF Capital Investments"
    },
    {
        "ticker": "MIN",
        "name": "Mineral Resources"
    },
    {
        "ticker": "MGR",
        "name": "Mirvac Group"
    },
    {
        "ticker": "MND",
        "name": "Monadelphous Group"
    },
    {
        "ticker": "NAN",
        "name": "Nanosonics"
    },
    {
        "ticker": "NAB",
        "name": "National Australia Bank"
    },
    {
        "ticker": "NSR",
        "name": "National Storage REIT"
    },
    {
        "ticker": "NGI",
        "name": "Navigator Global Investments"
    },
    {
        "ticker": "NWL",
        "name": "Netwealth Group"
    },
    {
        "ticker": "NEU",
        "name": "Neuren Pharmaceuticals"
    },
    {
        "ticker": "NHC",
        "name": "New Hope Corporation"
    },
    {
        "ticker": "NEM",
        "name": "Newmont Corporation"
    },
    {
        "ticker": "NWS",
        "name": "News Corporation"
    },
    {
        "ticker": "NXG",
        "name": "NexGen Energy (Canada)"
    },
    {
        "ticker": "NXT",
        "name": "NEXTDC"
    },
    {
        "ticker": "NHF",
        "name": "NIB Holdings"
    },
    {
        "ticker": "NCK",
        "name": "Nick Scali"
    },
    {
        "ticker": "NIC",
        "name": "Nickel Industries"
    },
    {
        "ticker": "NEC",
        "name": "Nine Entertainment Co. Holdings"
    },
    {
        "ticker": "NST",
        "name": "Northern Star Resources"
    },
    {
        "ticker": "NWH",
        "name": "NRW Holdings"
    },
    {
        "ticker": "OCL",
        "name": "Objective Corporation"
    },
    {
        "ticker": "OBM",
        "name": "Ora Banda Mining"
    },
    {
        "ticker": "ORI",
        "name": "Orica"
    },
    {
        "ticker": "ORG",
        "name": "Origin Energy"
    },
    {
        "ticker": "ORA",
        "name": "Orora"
    },
    {
        "ticker": "PDN",
        "name": "Paladin Energy"
    },
    {
        "ticker": "PNR",
        "name": "Pantoro Gold"
    },
    {
        "ticker": "PRN",
        "name": "Perenti"
    },
    {
        "ticker": "PPT",
        "name": "Perpetual"
    },
    {
        "ticker": "PRU",
        "name": "Perseus Mining"
    },
    {
        "ticker": "PXA",
        "name": "PEXA Group"
    },
    {
        "ticker": "PNI",
        "name": "Pinnacle Investment Management Group"
    },
    {
        "ticker": "PL8",
        "name": "Plato Income Maximiser"
    },
    {
        "ticker": "PLS",
        "name": "PLS Group"
    },
    {
        "ticker": "PGF",
        "name": "PM Capital Global Opportunities Fund"
    },
    {
        "ticker": "PDI",
        "name": "Predictive Discovery"
    },
    {
        "ticker": "PMV",
        "name": "Premier Investments"
    },
    {
        "ticker": "PME",
        "name": "Pro Medicus"
    },
    {
        "ticker": "PYC",
        "name": "PYC Therapeutics"
    },
    {
        "ticker": "QAN",
        "name": "Qantas Airways"
    },
    {
        "ticker": "QBE",
        "name": "QBE Insurance Group"
    },
    {
        "ticker": "QAL",
        "name": "Qualitas"
    },
    {
        "ticker": "QRI",
        "name": "Qualitas Real Estate Income Fund"
    },
    {
        "ticker": "QUB",
        "name": "Qube Holdings"
    },
    {
        "ticker": "RMS",
        "name": "Ramelius Resources"
    },
    {
        "ticker": "RHC",
        "name": "Ramsay Health Care"
    },
    {
        "ticker": "REA",
        "name": "REA Group"
    },
    {
        "ticker": "RDX",
        "name": "Redox"
    },
    {
        "ticker": "REH",
        "name": "Reece"
    },
    {
        "ticker": "RPL",
        "name": "Regal Partners"
    },
    {
        "ticker": "RGN",
        "name": "Region Group"
    },
    {
        "ticker": "REG",
        "name": "Regis Healthcare"
    },
    {
        "ticker": "RRL",
        "name": "Regis Resources"
    },
    {
        "ticker": "RWC",
        "name": "Reliance Worldwide Corporation"
    },
    {
        "ticker": "RMD",
        "name": "ResMed Inc."
    },
    {
        "ticker": "RSG",
        "name": "Resolute Mining"
    },
    {
        "ticker": "SGLLV",
        "name": "Ricegrowers"
    },
    {
        "ticker": "RIC",
        "name": "Ridley Corporation"
    },
    {
        "ticker": "RIO",
        "name": "Rio Tinto"
    },
    {
        "ticker": "RUL",
        "name": "RPMGlobal Holdings"
    },
    {
        "ticker": "RYM",
        "name": "Ryman Healthcare"
    },
    {
        "ticker": "SFR",
        "name": "Sandfire Resources"
    },
    {
        "ticker": "STO",
        "name": "Santos"
    },
    {
        "ticker": "SCG",
        "name": "Scentre Group"
    },
    {
        "ticker": "SEK",
        "name": "SEEK"
    },
    {
        "ticker": "SSM",
        "name": "Service Stream"
    },
    {
        "ticker": "SGH",
        "name": "SGH"
    },
    {
        "ticker": "SIG",
        "name": "Sigma Healthcare"
    },
    {
        "ticker": "SLX",
        "name": "Silex Systems"
    },
    {
        "ticker": "SGM",
        "name": "Sims"
    },
    {
        "ticker": "SDR",
        "name": "SiteMinder"
    },
    {
        "ticker": "SIQ",
        "name": "Smartgroup Corporation"
    },
    {
        "ticker": "SHL",
        "name": "Sonic Healthcare"
    },
    {
        "ticker": "S32",
        "name": "South32"
    },
    {
        "ticker": "SX2",
        "name": "Southern Cross Gold Consolidated"
    },
    {
        "ticker": "SPK",
        "name": "Spark New Zealand"
    },
    {
        "ticker": "SRG",
        "name": "SRG Global"
    },
    {
        "ticker": "SMR",
        "name": "Stanmore Resources"
    },
    {
        "ticker": "SDF",
        "name": "Steadfast Group"
    },
    {
        "ticker": "SGP",
        "name": "Stockland"
    },
    {
        "ticker": "SNZ",
        "name": "Summerset Group Holdings"
    },
    {
        "ticker": "SUN",
        "name": "Suncorp Group"
    },
    {
        "ticker": "SRL",
        "name": "Sunrise Energy Metals"
    },
    {
        "ticker": "SUL",
        "name": "Super Retail Group"
    },
    {
        "ticker": "SLC",
        "name": "Superloop"
    },
    {
        "ticker": "SNL",
        "name": "Supply Network"
    },
    {
        "ticker": "TAH",
        "name": "Tabcorp Holdings"
    },
    {
        "ticker": "TEA",
        "name": "Tasmea"
    },
    {
        "ticker": "TNE",
        "name": "Technology One"
    },
    {
        "ticker": "TLX",
        "name": "Telix Pharmaceuticals"
    },
    {
        "ticker": "TLS",
        "name": "Telstra Group"
    },
    {
        "ticker": "TPW",
        "name": "Temple & Webster Group"
    },
    {
        "ticker": "A2M",
        "name": "The a2 Milk Company"
    },
    {
        "ticker": "TLC",
        "name": "The Lottery Corporation"
    },
    {
        "ticker": "SGR",
        "name": "The Star Entertainment Group"
    },
    {
        "ticker": "TPG",
        "name": "TPG Telecom"
    },
    {
        "ticker": "TCL",
        "name": "Transurban Group"
    },
    {
        "ticker": "TWE",
        "name": "Treasury Wine Estates"
    },
    {
        "ticker": "TUA",
        "name": "Tuas"
    },
    {
        "ticker": "VAU",
        "name": "Vault Minerals"
    },
    {
        "ticker": "VNT",
        "name": "Ventia Services Group"
    },
    {
        "ticker": "VCX",
        "name": "Vicinity Centres"
    },
    {
        "ticker": "VGN",
        "name": "Virgin Australia Holdings"
    },
    {
        "ticker": "VEA",
        "name": "Viva Energy Group"
    },
    {
        "ticker": "VUL",
        "name": "Vulcan Energy Resources"
    },
    {
        "ticker": "VSL",
        "name": "Vulcan Steel"
    },
    {
        "ticker": "WA1",
        "name": "WA1 Resources"
    },
    {
        "ticker": "WAM",
        "name": "WAM Capital"
    },
    {
        "ticker": "WLE",
        "name": "WAM Leaders"
    },
    {
        "ticker": "SOL",
        "name": "Washington H. Soul Pattinson and Co."
    },
    {
        "ticker": "WPR",
        "name": "Waypoint REIT"
    },
    {
        "ticker": "WEB",
        "name": "WEB Travel Group"
    },
    {
        "ticker": "WBT",
        "name": "Weebit Nano"
    },
    {
        "ticker": "WES",
        "name": "Wesfarmers"
    },
    {
        "ticker": "WAF",
        "name": "West African Resources"
    },
    {
        "ticker": "WGX",
        "name": "Westgold Resources"
    },
    {
        "ticker": "WBC",
        "name": "Westpac Banking Corporation"
    },
    {
        "ticker": "WHC",
        "name": "Whitehaven Coal"
    },
    {
        "ticker": "WTC",
        "name": "Wisetech Global"
    },
    {
        "ticker": "WDS",
        "name": "Woodside Energy Group"
    },
    {
        "ticker": "WOW",
        "name": "Woolworths Group"
    },
    {
        "ticker": "WOR",
        "name": "Worley"
    },
    {
        "ticker": "XRO",
        "name": "Xero"
    },
    {
        "ticker": "YAL",
        "name": "Yancoal Australia"
    },
    {
        "ticker": "ZIM",
        "name": "Zimplats Holdings"
    },
    {
        "ticker": "ZIP",
        "name": "Zip Co"
    }
]

def generate_stock_list():
    stocks = []
    for s in STOCKS_DATA:
        stocks.append({
            "ticker": f"{s['ticker']}.AX",
            "name": s['name'],
            "sector": "Unknown"
        })
    
    stock_list = {
        "stocks": stocks,
        "last_updated": datetime.now().isoformat() + "Z"
    }
    
    output_file = METADATA_DIR / "stock_list.json"
    with open(output_file, "w") as f:
        json.dump(stock_list, f, indent=2)
    
    print(f"Generated {len(stocks)} stocks in {output_file}")

if __name__ == "__main__":
    generate_stock_list()
