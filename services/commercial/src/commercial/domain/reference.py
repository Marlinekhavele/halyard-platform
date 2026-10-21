"""Reference data for seeding: ports, trade lanes, carriers and surcharges.

The lane prices are planning figures (EUR per 40' high cube, all-in ocean) to
replace with real contract and spot rates from carriers and consolidators.
"""

# code, name, country, region, is_hub
PORTS = [
    ("CNSHA", "Shanghai", "CN", "ASIA", False),
    ("CNNGB", "Ningbo", "CN", "ASIA", False),
    ("CNSZX", "Shenzhen (Yantian)", "CN", "ASIA", False),
    ("CNTAO", "Qingdao", "CN", "ASIA", False),
    ("KRPUS", "Busan", "KR", "ASIA", True),
    ("VNSGN", "Ho Chi Minh City", "VN", "ASIA", False),
    ("VNHPH", "Haiphong", "VN", "ASIA", False),
    ("THLCH", "Laem Chabang", "TH", "ASIA", False),
    ("MYPKG", "Port Klang", "MY", "ASIA", False),
    ("SGSIN", "Singapore", "SG", "ASIA", True),
    ("LKCMB", "Colombo", "LK", "IN", True),
    ("INNSA", "Nhava Sheva", "IN", "IN", False),
    ("INMUN", "Mundra", "IN", "IN", False),
    ("AEJEA", "Jebel Ali", "AE", "ME", False),
    ("OMSLL", "Salalah", "OM", "ME", True),
    ("TRMER", "Mersin", "TR", "ME", False),
    ("DEHAM", "Hamburg", "DE", "EU", False),
    ("DEBRV", "Bremerhaven", "DE", "EU", False),
    ("NLRTM", "Rotterdam", "NL", "EU", False),
    ("BEANR", "Antwerp", "BE", "EU", False),
    ("PLGDN", "Gdańsk", "PL", "EU", False),
    ("MAPTM", "Tanger Med", "MA", "EU", True),
    ("ESALG", "Algeciras", "ES", "EU", True),
    ("USNYC", "New York / New Jersey", "US", "NAM", False),
    ("USSAV", "Savannah", "US", "NAM", False),
    ("USLAX", "Los Angeles", "US", "NAM", False),
    ("PAMIT", "Manzanillo (Panama)", "PA", "NAM", True),
    ("BRSSZ", "Santos", "BR", "SAM", False),
]

# (origin region, destination region) -> (sell EUR per 40HC, transit days)
LANES = {
    ("ASIA", "EU"): (2150, 32),
    ("EU", "ASIA"): (780, 34),
    ("ASIA", "NAM"): (2450, 19),
    ("NAM", "ASIA"): (900, 21),
    ("EU", "NAM"): (1650, 11),
    ("NAM", "EU"): (1100, 12),
    ("ASIA", "ASIA"): (450, 6),
    ("EU", "EU"): (620, 4),
    ("IN", "EU"): (1550, 22),
    ("EU", "IN"): (950, 23),
    ("ME", "EU"): (1400, 18),
    ("EU", "ME"): (1050, 19),
    ("SAM", "EU"): (1700, 17),
    ("EU", "SAM"): (1500, 18),
    ("ASIA", "SAM"): (2900, 35),
    ("SAM", "ASIA"): (1300, 37),
    ("ASIA", "IN"): (800, 12),
    ("IN", "ASIA"): (700, 12),
    ("ASIA", "ME"): (950, 16),
    ("ME", "ASIA"): (600, 16),
    ("IN", "NAM"): (2300, 30),
    ("NAM", "SAM"): (1400, 14),
    ("SAM", "NAM"): (1500, 14),
}

HUB_FOR_LANE = {
    ("ASIA", "EU"): "SGSIN",
    ("EU", "ASIA"): "MAPTM",
    ("IN", "EU"): "OMSLL",
    ("EU", "IN"): "OMSLL",
    ("ASIA", "NAM"): "KRPUS",
    ("ASIA", "SAM"): "PAMIT",
    ("SAM", "EU"): "ESALG",
    ("EU", "SAM"): "ESALG",
    ("ASIA", "IN"): "LKCMB",
    ("IN", "ASIA"): "LKCMB",
    ("ASIA", "ME"): "LKCMB",
}

CARRIERS = [
    "Maersk",
    "MSC",
    "CMA CGM",
    "Hapag-Lloyd",
    "ONE",
    "COSCO",
    "Evergreen",
]

# Three product profiles offered on every lane:
# name, sell multiplier, transit delta days, direct?, co2 factor, weekday
PROFILES = [
    ("fast", 1.12, -3, True, 1.08, 0),
    ("value", 0.94, 2, False, 1.00, 3),
    ("eco", 1.00, 5, True, 0.78, 5),
]

# Relative price of each container type against a 40' high cube.
CONTAINER_FACTORS = {"20DV": 0.62, "40DV": 0.95, "40HC": 1.0, "40RF": 1.75}
CONTAINER_TEU = {"20DV": 1, "40DV": 2, "40HC": 2, "40RF": 2}
CONTAINER_LABELS = {
    "20DV": "20' Dry",
    "40DV": "40' Dry",
    "40HC": "40' High Cube",
    "40RF": "40' Reefer",
}

# Share of the sell price we pay the carrier on the ocean leg.
OCEAN_BUY_RATIO = 0.955

# code, label, basis, sell, cost, min_sell, min_cost, container_type, option,
# sort
SURCHARGES = [
    ("BAF", "Bunker surcharge (BAF)", "percent_ocean",
     1400, 1400, 0, 0, None, None, 20),
    ("THC_O", "Origin terminal handling (THC)", "per_container",
     18500, 17000, 0, 0, None, None, 30),
    ("THC_D", "Destination terminal handling (THC)", "per_container",
     23500, 22000, 0, 0, None, None, 40),
    ("ISPS", "ISPS security fee", "per_container",
     1800, 1500, 0, 0, None, None, 50),
    ("REEFER", "Reefer plug-in and monitoring", "per_container",
     14000, 11000, 0, 0, "40RF", None, 60),
    ("DOC", "Documentation fee", "per_shipment",
     4500, 0, 0, 0, None, None, 70),
    ("CUSTOMS", "Import customs clearance", "per_shipment",
     9500, 4000, 0, 0, None, "customs", 80),
    ("TRUCK", "Truck to your warehouse", "per_container",
     52000, 45000, 0, 0, None, "trucking", 90),
    ("INSURANCE", "Cargo insurance", "percent_value",
     25, 16, 3500, 2000, None, "insurance", 100),
]  # fmt: skip

VESSELS = {
    "Maersk": ["Maersk Elba", "Maersk Kowloon", "Maersk Tangier"],
    "MSC": ["MSC Aldea Norte", "MSC Lisbon Star", "MSC Rhea"],
    "CMA CGM": ["CMA CGM Lys Horizon", "CMA CGM Tage", "CMA CGM Marseille"],
    "Hapag-Lloyd": ["Elbe Meridian", "Hamburg Express", "Cabo Frio Express"],
    "ONE": ["ONE Bright Kestrel", "ONE Harmony", "ONE Minato"],
    "COSCO": ["COSCO Pearl River", "COSCO Taicang", "COSCO Aden"],
    "Evergreen": ["Ever Gentle", "Ever Lotus", "Ever Summit"],
}
