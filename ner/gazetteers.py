"""
ner/gazetteers.py — Curated Indian Legal Gazetteers

Covers: Acts, Codes, Rules, Tribunals, Courts, Regulatory Bodies, Ministries.
Organised into named lists so callers can choose which to include.
All sorted longest-first for greedy matching.
"""

# ── Central Statutes ──────────────────────────────────────────────────────────
ACTS = [
    # Constitutional / Foundational
    "Constitution of India",
    # Income Tax
    "Income-tax Act, 1961",
    "Income Tax Act, 1961",
    "Income Tax Act",
    "Income-tax Act",
    "Direct Tax Vivad se Vishwas Act, 2020",
    "Direct Taxes Code",
    # Finance & Budget
    "Finance Act, 2025", "Finance Act, 2024", "Finance Act, 2023",
    "Finance Act, 2022", "Finance Act, 2021", "Finance Act, 2020",
    "Finance Act, 2019", "Finance Act, 2018", "Finance Act, 2017",
    "Finance (No. 2) Act, 2019", "Finance (No. 2) Act, 2014",
    # GST
    "Central Goods and Services Tax Act, 2017",
    "Integrated Goods and Services Tax Act, 2017",
    "Union Territory Goods and Services Tax Act, 2017",
    "Goods and Services Tax (Compensation to States) Act, 2017",
    "Central Goods and Services Tax Act",
    # Customs & Excise
    "Customs Act, 1962",
    "Central Excise Act, 1944",
    "Customs Tariff Act, 1975",
    # Black Money / Benami
    "Black Money (Undisclosed Foreign Income and Assets) and Imposition of Tax Act, 2015",
    "Prohibition of Benami Property Transactions Act, 1988",
    "Benami Transactions (Prohibition) Act, 1988",
    # FEMA / FERA / PMLA
    "Foreign Exchange Management Act, 1999",
    "Foreign Exchange Regulation Act, 1973",
    "Prevention of Money Laundering Act, 2002",
    "Foreign Contribution (Regulation) Act, 2010",
    "Foreign Contribution (Regulation) Act, 1976",
    # Companies
    "Companies Act, 2013",
    "Companies Act, 1956",
    "Limited Liability Partnership Act, 2008",
    "Insolvency and Bankruptcy Code, 2016",
    # Securities
    "Securities and Exchange Board of India Act, 1992",
    "Securities Contracts (Regulation) Act, 1956",
    "Depositories Act, 1996",
    # Banking & Finance
    "Reserve Bank of India Act, 1934",
    "Banking Regulation Act, 1949",
    "Negotiable Instruments Act, 1881",
    "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act, 2002",
    "SARFAESI Act, 2002",
    # Civil / Criminal
    "Code of Civil Procedure, 1908",
    "Code of Criminal Procedure, 1973",
    "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "Bharatiya Nyaya Sanhita, 2023",
    "Bharatiya Sakshya Adhiniyam, 2023",
    "Indian Penal Code, 1860",
    "Indian Evidence Act, 1872",
    "Indian Contract Act, 1872",
    "Specific Relief Act, 1963",
    "Limitation Act, 1963",
    "Transfer of Property Act, 1882",
    "Registration Act, 1908",
    # Labour
    "Industrial Disputes Act, 1947",
    "Employees' Provident Funds and Miscellaneous Provisions Act, 1952",
    "Payment of Gratuity Act, 1972",
    "Minimum Wages Act, 1948",
    "Factories Act, 1948",
    "Code on Wages, 2019",
    "Code on Social Security, 2020",
    "Industrial Relations Code, 2020",
    "Occupational Safety, Health and Working Conditions Code, 2020",
    # IP
    "Patents Act, 1970",
    "Trade Marks Act, 1999",
    "Copyright Act, 1957",
    "Designs Act, 2000",
    "Geographical Indications of Goods (Registration and Protection) Act, 1999",
    # RTI / Governance
    "Right to Information Act, 2005",
    "Prevention of Corruption Act, 1988",
    "Lokpal and Lokayuktas Act, 2013",
    # Other major statutes
    "Arbitration and Conciliation Act, 1996",
    "Consumer Protection Act, 2019",
    "Competition Act, 2002",
    "Real Estate (Regulation and Development) Act, 2016",
    "Environment Protection Act, 1986",
    "Information Technology Act, 2000",
    "Telecom Regulatory Authority of India Act, 1997",
    "Insurance Act, 1938",
    "Insurance Laws (Amendment) Act, 2015",
    "Stamp Act, 1899",
    "Indian Stamp Act, 1899",
    "Wealth Tax Act, 1957",
    "Gift Tax Act, 1958",
    "Interest Tax Act, 1974",
    "Expenditure Tax Act, 1987",
    "Smugglers and Foreign Exchange Manipulators (Forfeiture of Property) Act, 1976",
]

# ── Rules / Regulations (major sets) ─────────────────────────────────────────
RULES = [
    "Income-tax Rules, 1962",
    "Income Tax Rules, 1962",
    "Companies (Accounts) Rules, 2014",
    "Companies (Audit and Auditors) Rules, 2014",
    "SEBI (Listing Obligations and Disclosure Requirements) Regulations, 2015",
    "SEBI (Substantial Acquisition of Shares and Takeovers) Regulations, 2011",
    "SEBI (Prohibition of Insider Trading) Regulations, 2015",
    "FEMA (Non-Debt Instruments) Rules, 2019",
    "FEMA (Debt Instruments) Regulations, 2019",
    "Central Goods and Services Tax Rules, 2017",
    "Customs (Import of Goods at Concessional Rate of Duty) Rules, 2017",
    "Transfer Pricing Safe Harbour Rules",
    "Advance Pricing Agreement Rules",
]

# ── Courts ────────────────────────────────────────────────────────────────────
COURTS = [
    "Supreme Court of India",
    "High Court of Delhi",
    "Delhi High Court",
    "Bombay High Court",
    "High Court of Bombay",
    "Madras High Court",
    "High Court of Madras",
    "Calcutta High Court",
    "High Court of Calcutta",
    "Allahabad High Court",
    "High Court of Allahabad",
    "Karnataka High Court",
    "High Court of Karnataka",
    "Gujarat High Court",
    "High Court of Gujarat",
    "Rajasthan High Court",
    "Kerala High Court",
    "Andhra Pradesh High Court",
    "Telangana High Court",
    "Patna High Court",
    "Punjab and Haryana High Court",
    "Gauhati High Court",
    "Orissa High Court",
    "Uttarakhand High Court",
    "Jharkhand High Court",
    "Chhattisgarh High Court",
    "Himachal Pradesh High Court",
    "Tripura High Court",
    "Meghalaya High Court",
    "Manipur High Court",
    "Sikkim High Court",
]

# ── Tribunals / Quasi-Judicial ────────────────────────────────────────────────
TRIBUNALS = [
    "Income Tax Appellate Tribunal",
    "ITAT",
    "Authority for Advance Rulings",
    "Board for Advance Rulings",
    "National Company Law Tribunal",
    "National Company Law Appellate Tribunal",
    "NCLT",
    "NCLAT",
    "Debt Recovery Tribunal",
    "Debt Recovery Appellate Tribunal",
    "Securities Appellate Tribunal",
    "Customs, Excise and Service Tax Appellate Tribunal",
    "CESTAT",
    "Appellate Authority for Advance Ruling",
    "GST Appellate Authority",
    "GST Council",
    "Goods and Services Tax Appellate Tribunal",
    "Appellate Tribunal for Foreign Exchange",
    "Competition Commission of India",
    "Competition Appellate Tribunal",
    "Telecom Disputes Settlement and Appellate Tribunal",
    "National Green Tribunal",
    "Central Administrative Tribunal",
    "Armed Forces Tribunal",
    "Consumer Disputes Redressal Commission",
    "National Consumer Disputes Redressal Commission",
    "Insolvency and Bankruptcy Board of India",
    "Real Estate Regulatory Authority",
]

# ── Regulatory & Government Bodies ───────────────────────────────────────────
REGULATORS = [
    # Tax administration
    "Central Board of Direct Taxes",
    "CBDT",
    "Central Board of Indirect Taxes and Customs",
    "CBIC",
    "Income Tax Department",
    "Directorate of Income Tax",
    "Directorate General of Income Tax Investigation",
    "Principal Chief Commissioner of Income Tax",
    "Chief Commissioner of Income Tax",
    "Principal Commissioner of Income Tax",
    "Commissioner of Income Tax",
    "Assessing Officer",
    "Transfer Pricing Officer",
    "Dispute Resolution Panel",
    # Finance
    "Reserve Bank of India",
    "RBI",
    "Securities and Exchange Board of India",
    "SEBI",
    "Insurance Regulatory and Development Authority of India",
    "IRDAI",
    "Pension Fund Regulatory and Development Authority",
    "PFRDA",
    "National Bank for Agriculture and Rural Development",
    "NABARD",
    "Small Industries Development Bank of India",
    "SIDBI",
    "Export-Import Bank of India",
    "EXIM Bank",
    "National Housing Bank",
    # Companies / Enforcement
    "Ministry of Corporate Affairs",
    "Registrar of Companies",
    "Official Liquidator",
    "Enforcement Directorate",
    "Serious Fraud Investigation Office",
    "SFIO",
    "Financial Intelligence Unit",
    "FIU-IND",
    "Directorate of Enforcement",
    # GST specific
    "GST Network",
    "GSTN",
    "National Anti-Profiteering Authority",
    # Government of India
    "Government of India",
    "Union of India",
    "Ministry of Finance",
    "Department of Revenue",
    "Department of Economic Affairs",
    "Department of Financial Services",
    "Department of Commerce",
    "Ministry of Law and Justice",
    "Department of Legal Affairs",
    "Legislative Department",
    "Ministry of Home Affairs",
    "Ministry of External Affairs",
    "Ministry of Labour and Employment",
    "Ministry of Commerce and Industry",
    "Ministry of Electronics and Information Technology",
    "Prime Minister's Office",
    "Cabinet Secretariat",
    "Law Commission of India",
    "Comptroller and Auditor General of India",
    "CAG",
    "Attorney General of India",
    "Solicitor General of India",
    "Election Commission of India",
    "Central Information Commission",
    "National Human Rights Commission",
    # Banking
    "State Bank of India",
    "Punjab National Bank",
    "Bank of Baroda",
    "Union Bank of India",
    "HDFC Bank",
    "ICICI Bank",
    "Axis Bank",
    # International bodies (relevant to Indian tax law)
    "Organisation for Economic Co-operation and Development",
    "OECD",
    "United Nations",
    "International Monetary Fund",
    "IMF",
    "World Bank",
    "Financial Action Task Force",
    "FATF",
    "Global Forum on Transparency and Exchange of Information",
]

# ── DTAA Country Competent Authorities ────────────────────────────────────────
COMPETENT_AUTHORITIES = [
    "competent authority of India",
    "competent authority of",
    "Mutual Agreement Procedure",
]

# ── Combined for NER (all ORG-type entities) ──────────────────────────────────
ALL_ORGS = sorted(
    set(COURTS + TRIBUNALS + REGULATORS + COMPETENT_AUTHORITIES),
    key=len,
    reverse=True,   # longest first for greedy matching
)

ALL_ACTS = sorted(
    set(ACTS + RULES),
    key=len,
    reverse=True,
)
