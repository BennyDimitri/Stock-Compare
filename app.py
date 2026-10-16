import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

st.set_page_config(page_title="Stock Head-to-Head", page_icon="📈", layout="wide")
st.title("📈 Stock Head-to-Head")
st.caption("Compare two stocks: price action, fundamentals, Wall Street opinion, and news sentiment. Not financial advice.")

# ---------- sidebar ----------
with st.sidebar:
    st.header("Pick two stocks")
    a = st.text_input("Ticker 1", "AAPL").strip().upper()
    b = st.text_input("Ticker 2", "MSFT").strip().upper()
    period = st.selectbox("Comparison period", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], index=3)
    st.button("Refresh data", on_click=st.cache_data.clear)

if not a or not b:
    st.info("Enter two tickers in the sidebar.")
    st.stop()

# ---------- data ----------
@st.cache_data(ttl=300)
def get_info(t):
    try:
        return yf.Ticker(t).info or {}
    except Exception:
        return {}

@st.cache_data(ttl=300)
def get_history(t, period):
    try:
        return yf.Ticker(t).history(period=period)["Close"]
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=900)
def get_analyst(t):
    tk = yf.Ticker(t)
    out = {}
    for key, fn in {
        "targets": lambda: tk.analyst_price_targets,
        "summary": lambda: tk.recommendations_summary,
        "changes": lambda: tk.upgrades_downgrades,
    }.items():
        try:
            out[key] = fn()
        except Exception:
            out[key] = None
    return out

@st.cache_data(ttl=600)
def get_news(t):
    try:
        raw = yf.Ticker(t).news or []
    except Exception:
        return []
    items = []
    for n in raw:
        c = n.get("content", n)  # yfinance changed formats over time
        title = c.get("title")
        if not title:
            continue
        url = (c.get("canonicalUrl") or {}).get("url") or c.get("link") or ""
        pub = (c.get("provider") or {}).get("displayName") or c.get("publisher") or ""
        date = c.get("pubDate") or ""
        items.append({"title": title, "url": url, "publisher": pub, "date": date[:10]})
    return items

vader = SentimentIntensityAnalyzer()

def sentiment(items):
    if not items:
        return None
    return sum(vader.polarity_scores(i["title"])["compound"] for i in items) / len(items)

def fmt_big(x):
    if not isinstance(x, (int, float)):
        return "—"
    for unit, div in [("T", 1e12), ("B", 1e9), ("M", 1e6)]:
        if abs(x) >= div:
            return f"${x/div:,.2f}{unit}"
    return f"${x:,.0f}"

def fmt(x, pre="", suf="", d=2):
    return f"{pre}{x:,.{d}f}{suf}" if isinstance(x, (int, float)) else "—"

def tv_chart(symbol, key, height=520):
    html = f"""
    <div class="tradingview-widget-container" style="height:{height}px">
      <div id="tv_{key}" style="height:{height}px"></div>
      <script src="https://s3.tradingview.com/tv.js"></script>
      <script>
        new TradingView.widget({{
          "autosize": true, "symbol": "{symbol}", "interval": "D",
          "timezone": "Etc/UTC", "theme": "dark", "style": "1",
          "locale": "en", "allow_symbol_change": false,
          "hide_side_toolbar": false, "container_id": "tv_{key}"
        }});
      </script>
    </div>"""
    components.html(html, height=height)

tickers = [a, b]
infos = {t: get_info(t) for t in tickers}
bad = [t for t in tickers if not infos[t]]
if bad:
    st.error(f"Couldn't load data for: {', '.join(bad)}. Check the ticker symbol(s).")
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Live charts", "Analyst outlook", "News & sentiment"])

# ---------- overview ----------
with tab1:
    cols = st.columns(2)
    for col, t in zip(cols, tickers):
        i = infos[t]
        with col:
            st.subheader(f"{t} — {i.get('shortName', '')}")
            price = i.get("currentPrice") or i.get("regularMarketPrice")
            prev = i.get("previousClose")
            delta = f"{(price/prev-1)*100:+.2f}%" if price and prev else None
            st.metric("Price", fmt(price, "$"), delta)
            m1, m2, m3 = st.columns(3)
            m1.metric("Market cap", fmt_big(i.get("marketCap")))
            m2.metric("P/E (trailing)", fmt(i.get("trailingPE")))
            m3.metric("P/E (forward)", fmt(i.get("forwardPE")))
            m4, m5, m6 = st.columns(3)
            m4.metric("52w high", fmt(i.get("fiftyTwoWeekHigh"), "$"))
            m5.metric("52w low", fmt(i.get("fiftyTwoWeekLow"), "$"))
            m6.metric("Beta", fmt(i.get("beta")))
            st.caption(f"{i.get('sector', '—')} · {i.get('industry', '—')}")

    st.subheader(f"Performance over {period} (starting value = 100)")
    hist = pd.concat({t: get_history(t, period) for t in tickers}, axis=1).dropna()
    if not hist.empty:
        st.line_chart(hist / hist.iloc[0] * 100)
        total = (hist.iloc[-1] / hist.iloc[0] - 1) * 100
        st.write("  |  ".join(f"**{t}**: {total[t]:+.1f}%" for t in tickers))

# ---------- live charts ----------
with tab2:
    cols = st.columns(2)
    for col, t in zip(cols, tickers):
        with col:
            st.subheader(t)
            tv_chart(t, t.replace(".", "_").replace("-", "_"))

# ---------- analysts ----------
with tab3:
    cols = st.columns(2)
    for col, t in zip(cols, tickers):
        i, data = infos[t], get_analyst(t)
        with col:
            st.subheader(t)
            rec = (i.get("recommendationKey") or "—").replace("_", " ").title()
            st.metric("Consensus", rec, f"{i.get('numberOfAnalystOpinions', '—')} analysts", delta_color="off")
            tg = data["targets"]
            if isinstance(tg, dict) and tg.get("mean"):
                cur = tg.get("current") or i.get("currentPrice")
                up = (tg["mean"] / cur - 1) * 100 if cur else None
                st.metric("Mean price target", fmt(tg["mean"], "$"), f"{up:+.1f}% vs. now" if up is not None else None)
                st.write(f"Low {fmt(tg.get('low'), '$')} · Median {fmt(tg.get('median'), '$')} · High {fmt(tg.get('high'), '$')}")
            s = data["summary"]
            if isinstance(s, pd.DataFrame) and not s.empty:
                st.markdown("**Rating breakdown (most recent month)**")
                row = s.iloc[0]
                st.bar_chart(pd.Series({k: row[k] for k in ["strongBuy", "buy", "hold", "sell", "strongSell"] if k in row}))
            ch = data["changes"]
            if isinstance(ch, pd.DataFrame) and not ch.empty:
                st.markdown("**Recent upgrades / downgrades**")
                st.dataframe(ch.head(8), use_container_width=True)

# ---------- news ----------
with tab4:
    cols = st.columns(2)
    for col, t in zip(cols, tickers):
        news = get_news(t)
        score = sentiment(news)
        with col:
            st.subheader(t)
            if score is None:
                st.write("No recent news found.")
                continue
            label = "Positive 🟢" if score > 0.15 else "Negative 🔴" if score < -0.15 else "Neutral ⚪"
            st.metric("Headline sentiment", label, f"{score:+.2f} avg (−1 to +1)", delta_color="off")
            for n in news[:10]:
                link = f"[{n['title']}]({n['url']})" if n["url"] else n["title"]
                st.markdown(f"- {link}  \n  <small>{n['publisher']} · {n['date']}</small>", unsafe_allow_html=True)

st.divider()
st.caption("Data via Yahoo Finance (yfinance, may be delayed) and TradingView widgets. Sentiment is a simple keyword model on headlines, so treat it as a rough signal. Not financial advice.")
