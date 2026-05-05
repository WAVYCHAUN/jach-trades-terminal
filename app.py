import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import random
from scipy.stats import norm

# ──────────────────────────────────────────────
# GREEKS / GEX ENGINE
def black_scholes_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S/K) + (r + sigma**2/2)*T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

def compute_total_gex(S, options_df, r=0.05):
    gex_per_strike = []
    total = 0
    for _, row in options_df.iterrows():
        T = (row['expiry'] - pd.Timestamp.now(tz='UTC')).days / 365.0
        sigma = row['iv']
        gamma = black_scholes_gamma(S, row['strike'], T, r, sigma)
        gex = gamma * row['oi'] * S * 100
        total += gex
        gex_per_strike.append({'strike': row['strike'], 'gex': gex})
    return total, pd.DataFrame(gex_per_strike)

# ──────────────────────────────────────────────
# DATA FEEDS
def get_spot(ticker):
    try:
        return yf.Ticker(ticker).history(period='1d')['Close'].iloc[-1]
    except:
        return None

def get_option_chain(ticker):
    try:
        tk = yf.Ticker(ticker)
        exps = tk.options
        if not exps:
            return None
        exp = exps[0]
        calls = tk.option_chain(exp).calls
        puts = tk.option_chain(exp).puts
        calls['type'] = 'call'
        puts['type'] = 'put'
        df = pd.concat([calls, puts])
        df['expiry'] = pd.to_datetime(exp).tz_localize('UTC')
        df = df.rename(columns={'openInterest':'oi','impliedVolatility':'iv'})
        return df
    except:
        return None

def get_vix():
    return yf.Ticker('^VIX').history(period='1d')['Close'].iloc[-1]

# ──────────────────────────────────────────────
# MOCK FLOW (until you plug in real data)
def mock_flow(n=12):
    syms = ['NVDA','AAPL','SPY','TSLA','META']
    rows = []
    for _ in range(n):
        sym = random.choice(syms)
        strike = random.randint(100,500)
        cp = random.choice(['CALL','PUT'])
        exp = datetime.now() + timedelta(days=random.choice([1,2,7,30]))
        price = round(random.uniform(0.1,5),2)
        side = random.choice(['ASK','BID'])
        sent = 'BULLISH' if (cp=='CALL' and side=='ASK') or (cp=='PUT' and side=='BID') else 'BEARISH'
        size = random.choice([10,50,100,500])
        prem = size * price * 100
        rows.append({
            'Time': datetime.now().strftime('%H:%M:%S'),
            'SYM': sym,
            'Strike': strike,
            'Type': cp,
            'Expiry': exp.strftime('%m/%d/%y'),
            'DTE': (exp - datetime.now()).days,
            'Price': price,
            'Side': side,
            'Sentiment': sent,
            'Size': size,
            'Premium': f'${prem:,.0f}'
        })
    return pd.DataFrame(rows)

# ──────────────────────────────────────────────
# UI
st.set_page_config(layout='wide')
st.title("JACH TRADES TERMINAL")
st.caption("Agent-first trading intelligence — live GEX · options flow · macro")

# ---- SIDEBAR ----
st.sidebar.header("⚙️ Control Panel")
ticker = st.sidebar.selectbox("Ticker for GEX", ['SPY','NVDA','AAPL','TSLA','QQQ'])
st.sidebar.header("📡 Agent Status")
run = st.sidebar.button("🔁 Run All Agents")
st.sidebar.markdown("---")
st.sidebar.write("Built by the community · No financial advice.")

# ---- RUN AGENTS ----
if run or 'gex_result' not in st.session_state:
    with st.spinner("🧠 Agents analyzing markets..."):
        # GEX Agent
        spot = get_spot(ticker)
        chain = get_option_chain(ticker)
        if spot and chain is not None:
            total_gex, strike_gex_df = compute_total_gex(spot, chain)
            strike_gex_df_sorted = strike_gex_df.sort_values('strike')
            strike_gex_df_sorted['cum_gex'] = strike_gex_df_sorted['gex'].cumsum()
            flip = None
            for i, row in strike_gex_df_sorted.iterrows():
                if row['cum_gex'] < 0:
                    flip = row['strike']
                    break
            st.session_state.gex_result = {
                'spot': spot,
                'total_gex': total_gex,
                'flip': flip,
                'strike_gex': strike_gex_df_sorted
            }
        else:
            st.session_state.gex_result = None

        # Macro Agent
        st.session_state.macro = {
            'vix': get_vix(),
            'pcr': round(random.uniform(0.9,1.4),2)  # placeholder
        }

        # Flow Agent
        st.session_state.flow_df = mock_flow(15)

# ---- DISPLAY ----
col1, col2 = st.columns([1,2])

with col1:
    st.subheader("🌐 Macro")
    macro = st.session_state.get('macro', {})
    st.metric("VIX", f"{macro.get('vix', 0):.2f}")
    st.metric("Put/Call", macro.get('pcr','-'))
    sentiment = 'BEARISH' if macro.get('vix',0)>25 else ('BULLISH' if macro.get('vix',0)<15 else 'NEUTRAL')
    st.metric("Signal", sentiment)

    st.subheader("📉 Dealer Gamma (GEX)")
    gex = st.session_state.get('gex_result')
    if gex:
        st.metric("Total GEX", f"${gex['total_gex']:,.0f}")
        st.metric("Flip Strike", f"{gex['flip']}  (Spot: {gex['spot']:.2f})")
        fig = px.bar(gex['strike_gex'], x='strike', y='gex',
                     title=f"{ticker} Gamma Exposure")
        fig.add_vline(x=gex['spot'], line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("Failed to load options data.")

with col2:
    st.subheader("📊 Live Options Flow")
    flow = st.session_state.get('flow_df', pd.DataFrame())
    st.dataframe(flow, height=400, use_container_width=True)

# ---- CONFLUENCE SIGNALS ----
st.markdown("---")
st.subheader("🔥 High-Confluence Signals")
if 'flow_df' in st.session_state and 'gex_result' in st.session_state:
    gex_r = st.session_state.gex_result
    flow_df = st.session_state.flow_df
    signals = []
    for _, row in flow_df.iterrows():
        score = 50
        sym = row['SYM']
        if gex_r and sym == ticker:
            if gex_r['total_gex'] > 0 and row['Sentiment'] == 'BULLISH':
                score += 20
            elif gex_r['total_gex'] < 0 and row['Sentiment'] == 'BEARISH':
                score += 20
            if gex_r['flip'] and gex_r['spot'] and abs(gex_r['spot']-gex_r['flip'])/gex_r['spot'] < 0.01:
                score += 10
        if sentiment == row['Sentiment']:
            score += 10
        signals.append({**row, 'Confluence Score': score})
    signals_df = pd.DataFrame(signals).sort_values('Confluence Score', ascending=False)
    st.dataframe(signals_df[['SYM','Type','Sentiment','Premium','Confluence Score']], use_container_width=True)
    top = signals_df.iloc[0]
    st.success(f"⚡ Top Signal: **{top['SYM']} {top['Type']}** | Score {top['Confluence Score']} | {top['Sentiment']} | Premium: {top['Premium']}")

