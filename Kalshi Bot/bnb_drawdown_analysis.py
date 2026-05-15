import pandas as pd
import numpy as np

def analyze_bnb_drawdown():
    df = pd.read_csv('market_history.csv')
    bnb = df[df['ticker'].str.contains('KXBNB15M', na=False)].copy()
    if bnb.empty: return

    bnb['t'] = pd.to_datetime(bnb['timestamp'])
    bnb['ct'] = pd.to_datetime(bnb['close_time'])
    bnb['rem'] = (bnb['ct'] - bnb['t']).dt.total_seconds() / 60.0
    bnb['price'] = bnb['last_price'].fillna((pd.to_numeric(bnb['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(bnb['yes_ask'], errors='coerce').fillna(100))/2)

    results = {}
    for ticker, group in bnb.groupby('ticker'):
        res = group['result'].dropna().unique()
        if len(res) > 0: results[ticker] = res[0].upper()

    print(f"Analyzing BNB Drawdowns for {len(results)} markets...")

    drawdowns = []
    # Trigger: Price hits 80c
    for ticker, group in bnb.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # YES Trigger
        match_yes = group[group['price'] >= 80].head(1)
        if not match_yes.empty:
            trigger_time = match_yes['t'].iloc[0]
            later = group[group['t'] > trigger_time]
            if not later.empty:
                min_p = later['price'].min()
                drawdowns.append({'ticker': ticker, 'side': 'YES', 'outcome': outcome, 'min_price': min_p})
        
        # NO Trigger
        match_no = group[group['price'] <= 20].head(1)
        if not match_no.empty:
            trigger_time = match_no['t'].iloc[0]
            later = group[group['t'] > trigger_time]
            if not later.empty:
                # For NO side, drawdown is 'max price' (since we want it lower)
                max_p = later['price'].max()
                drawdowns.append({'ticker': ticker, 'side': 'NO', 'outcome': outcome, 'min_price': max_p})

    dd_df = pd.DataFrame(drawdowns)
    if dd_df.empty: return

    # Analyze YES trades that won
    yes_wins = dd_df[(dd_df['side'] == 'YES') & (dd_df['outcome'] == 'YES')]
    if not yes_wins.empty:
        print(f"\nYES Wins: {len(yes_wins)}")
        print(f"Average Min Price after 80c entry: {yes_wins['min_price'].mean():.1f}c")
        print(f"Worst Drawdown among winners: {yes_wins['min_price'].min()}c")
    
    # Analyze YES trades that lost
    yes_losses = dd_df[(dd_df['side'] == 'YES') & (dd_df['outcome'] == 'NO')]
    if not yes_losses.empty:
        print(f"YES Losses: {len(yes_losses)}")
        print(f"Average Min Price on losses: {yes_losses['min_price'].mean():.1f}c")

if __name__ == "__main__":
    analyze_bnb_drawdown()
