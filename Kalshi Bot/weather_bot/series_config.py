"""
series_config.py
All Kalshi daily-temperature series tickers from:
  https://kalshi.com/category/climate/daily-temperature

Each entry is the Kalshi series ticker (the prefix shared by all
markets in that series).  The bot queries every series each run and
scans EVERY open market found under it.

Format: KXHIGH<CITY_CODE> for high-temp, KXLOW<CITY_CODE> for low-temp.
If Kalshi uses a slightly different naming scheme for a city the bot
will simply receive 0 markets for that series and skip it gracefully.
"""

WEATHER_SERIES = [
    # ---- HIGH temperature series ---- (Verified kxhigh vs kxhight legacy split)
    "KXHIGHNY",       # NYC
    "KXHIGHCHI",      # Chicago
    "KXHIGHLAX",      # Los Angeles
    "KXHIGHTHOU",     # Houston
    "KXHIGHTPHX",     # Phoenix
    "KXHIGHPHIL",     # Philadelphia
    "KXHIGHTSATX",    # San Antonio
    "KXHIGHTSD",      # San Diego
    "KXHIGHTSJC",     # San Jose
    "KXHIGHTAUS",     # Austin
    "KXHIGHDEN",      # Denver
    "KXHIGHMIA",      # Miami
    "KXHIGHTATL",     # Atlanta
    "KXHIGHTSFO",     # San Francisco
    "KXHIGHTDC",      # Washington DC
    "KXHIGHTPDX",     # Portland
    "KXHIGHTLV",      # Las Vegas
    "KXHIGHTMEM",     # Memphis
    "KXHIGHTNOLA",    # New Orleans
    "KXHIGHTSLC",     # Salt Lake City
    "KXHIGHTNKC",     # Kansas City
    "KXHIGHTCLE",     # Cleveland
    "KXHIGHTPITT",    # Pittsburgh
    "KXHIGHTDET",     # Detroit
    "KXHIGHTIND",     # Indianapolis
    "KXHIGHTOKC",     # Oklahoma City
    "KXHIGHTMIL",     # Milwaukee
    "KXHIGHTBUF",     # Buffalo
    "KXHIGHTCOL",     # Columbus
    "KXHIGHTBNA",     # Nashville
    "KXHIGHTBOS",     # Boston
    "KXHIGHTSEA",     # Seattle
    "KXHIGHTCLT",     # Charlotte

    # ---- LOW temperature series ---- (Almost universally kxlowt)
    "KXLOWTNYC",      # NYC
    "KXLOWTCHI",      # Chicago
    "KXLOWTLAX",      # Los Angeles
    "KXLOWTHOU",      # Houston
    "KXLOWTPHX",      # Phoenix
    "KXLOWTPHIL",     # Philadelphia
    "KXLOWTSATX",     # San Antonio
    "KXLOWTSD",       # San Diego
    "KXLOWTSJC",      # San Jose
    "KXLOWTAUS",      # Austin
    "KXLOWTDEN",      # Denver
    "KXLOWTMIA",      # Miami
    "KXLOWTATL",      # Atlanta
    "KXLOWTSFO",      # San Francisco
    "KXLOWTDC",       # Washington DC
    "KXLOWTPDX",      # Portland
    "KXLOWTLV",       # Las Vegas
    "KXLOWTMEM",      # Memphis
    "KXLOWTNOLA",     # New Orleans
    "KXLOWTSLC",      # Salt Lake City
    "KXLOWTNKC",      # Kansas City
    "KXLOWTCLE",      # Cleveland
    "KXLOWTPITT",     # Pittsburgh
    "KXLOWTDET",      # Detroit
    "KXLOWTIND",      # Indianapolis
    "KXLOWTOKC",      # Oklahoma City
    "KXLOWTMIL",      # Milwaukee
    "KXLOWTBUF",      # Buffalo
    "KXLOWTCOL",      # Columbus
    "KXLOWTBNA",      # Nashville
    "KXLOWTBOS",      # Boston
    "KXLOWTSEA",      # Seattle
    "KXLOWTCLT",      # Charlotte
]



# ---- Strategy constants ----
ENTRY_PRICE_CENTS = 90          # Place resting maker BUY at 90¢
TRIGGER_PRICE_CENTS = 90        # Only enter when yes_bid >= 90¢
STOP_LOSS_PRICE_CENTS = 70      # Taker market-sell if yes_bid falls to 70¢
CONTRACTS_PER_MARKET = 1        # Always buy exactly 1 share
