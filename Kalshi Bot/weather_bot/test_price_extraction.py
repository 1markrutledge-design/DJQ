from strategy import extract_yes_bid

def test():
    # 1. Sample from the user's log
    market_log = {
        'ticker': 'KXHIGHNY-26APR20-T58',
        'yes_bid_dollars': '0.0000',
        'last_price_dollars': '0.0100',
        'yes_ask_dollars': '0.0100'
    }
    extracted = extract_yes_bid(market_log)
    print(f"Test 1 (Log sample): {market_log['ticker']} -> {extracted}¢ (Expected 0¢)")
    assert extracted == 0

    # 2. Case where yes_bid_dollars is 90 cents
    market_90 = {
        'ticker': 'KXHIGHLA-26APR20-T75',
        'yes_bid_dollars': '0.9000',
        'yes_ask_dollars': '0.9100'
    }
    extracted = extract_yes_bid(market_90)
    print(f"Test 2 (90 cents): {market_90['ticker']} -> {extracted}¢ (Expected 90¢)")
    assert extracted == 90

    # 3. Case with old integer field
    market_int = {
        'ticker': 'KXBTCHIGH',
        'yes_bid': 94
    }
    extracted = extract_yes_bid(market_int)
    print(f"Test 3 (Integer field): {market_int['ticker']} -> {extracted}¢ (Expected 94¢)")
    assert extracted == 94

    # 4. Case with last_price_dollars
    market_last = {
        'ticker': 'KXLOWCHI',
        'last_price_dollars': '0.8500'
    }
    extracted = extract_yes_bid(market_last)
    print(f"Test 4 (Last price dollars): {market_last['ticker']} -> {extracted}¢ (Expected 85¢)")
    assert extracted == 85

    print("\n✅ All price extraction tests passed!")

if __name__ == "__main__":
    test()
