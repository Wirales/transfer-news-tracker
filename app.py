# Transfer News Tracker (Updated)

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urlparse
import html
import json
from pathlib import Path
import re
from dateutil import parser
from dateutil import tz
from pytz import timezone as pytz_timezone
from streamlit_javascript import st_javascript

from core.trust import update_trust_levels_from_votes

st.set_page_config(
    page_title="Transfer News Tracker",
    page_icon="assets/transfer_icon.png",  # relative path to your icon
    layout="centered"  # or "wide" if you prefer
)



# --- Detect local timezone ---
timezone = st.session_state.get("timezone", None)
if timezone is None:
    tzname = st_javascript("await Intl.DateTimeFormat().resolvedOptions().timeZone")
    if tzname:
        st.session_state["timezone"] = tzname
        timezone = tzname

# --- Trust Levels ---
with open("data/trust_levels.json", "r") as f:
    TRUST_LEVELS = json.load(f)

# --- Voting state (session-limited per article) ---
if "votes_cast" not in st.session_state:
    st.session_state["votes_cast"] = {}

# --- Helper Functions ---
def parse_date_safe(date_str):
    try:
        tzinfos = {"CET": tz.gettz("Europe/Berlin"), "CEST": tz.gettz("Europe/Berlin")}
        dt = parser.parse(date_str, tzinfos=tzinfos)
        return dt.replace(tzinfo=None)
    except:
        return pd.NaT

def trust_score_to_tier(score):
    if score >= 9:
        return "A"
    elif score >= 7:
        return "B"
    elif score >= 5:
        return "C"
    elif score > 0:
        return "D"
    else:
        return "U"

def record_vote(domain, direction, undo=False):
    votes_file = Path("data/trust_votes.json")
    if votes_file.exists():
        with open(votes_file, "r") as f:
            data = json.load(f)
    else:
        data = {}

    if domain not in data:
        data[domain] = {"up": 0, "down": 0}

    if direction == "up":
        data[domain]["up"] += (-1 if undo else 1)
    else:
        data[domain]["down"] += (-1 if undo else 1)

    with open(votes_file, "w") as f:
        json.dump(data, f, indent=2)

def log_unknown_source(domain):
    unknown_path = Path("data/unknown_sources.json")
    if unknown_path.exists():
        with open(unknown_path, "r") as f:
            known = set(json.load(f))
    else:
        known = set()

    if domain not in TRUST_LEVELS and domain not in known:
        known.add(domain)
        with open(unknown_path, "w") as f:
            json.dump(sorted(list(known)), f, indent=2)

def extract_clean_title(title, fallback_link):
    match = re.match(r"\[(.*?)\]\((.*?)\)", title)
    if match:
        return match.group(1), match.group(2)
    return title, fallback_link

def extract_real_domain(link):
    try:
        parsed = urlparse(link)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return "unknown"

def clean_google_link(link):
    try:
        if "url=" in link:
            return html.unescape(link.split("url=")[-1])
        elif link.startswith("https://news.google.com/rss/articles/"):
            return html.unescape(link)
        return html.unescape(link)
    except Exception:
        return link

def convert_to_local(pub_date_str, user_tz_name="Europe/Berlin"):
    try:
        tzinfos = {"CET": tz.gettz("Europe/Berlin"), "CEST": tz.gettz("Europe/Berlin")}
        gmt_dt = parser.parse(pub_date_str, tzinfos=tzinfos)
        local_tz = pytz_timezone(user_tz_name)
        return gmt_dt.astimezone(local_tz).strftime("%a, %d %b %Y %H:%M:%S %Z")
    except Exception:
        return pub_date_str

def search_google_news_rss(query):
    url = f"https://news.google.com/rss/search?q={query}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "xml")
    items = soup.find_all("item")

    results = []
    for item in items:
        raw_title = item.title.text
        raw_link = item.link.text
        link = clean_google_link(raw_link)
        title, link = extract_clean_title(raw_title, link)
        source = item.source.text if item.source else "Unknown"
        source_url = item.source['url'] if item.source and item.source.has_attr('url') else link
        domain = extract_real_domain(source_url)
        trust = TRUST_LEVELS.get(domain, 0)
        if domain not in TRUST_LEVELS:
            log_unknown_source(domain)
        snippet = item.description.text if item.description else ""
        pub_date = item.pubDate.text if item.pubDate else ""
        results.append({
            "Title": title,
            "Source": source,
            "Snippet": snippet,
            "Link": link,
            "Domain": domain,
            "Trust": trust,
            "Date": convert_to_local(pub_date, timezone) if timezone else pub_date
        })
    return pd.DataFrame(results)

# --- Routing: Source Tier Voting View ---
rate_domain = st.query_params.get("rate")
if rate_domain:
    st.title("📝 Rate Source:")
    st.code(rate_domain)
    current_tier = trust_score_to_tier(TRUST_LEVELS.get(rate_domain, 0))
    st.markdown(f"**Current Tier:** `{current_tier}`")

    tier = st.selectbox(
        "Select trust tier",
        ["A", "B", "C", "D", "U"],
        index=["A", "B", "C", "D", "U"].index(current_tier)
    )

    if st.button("Submit Tier Vote"):
        record_vote(rate_domain, "up")  # simplified tier voting logic
        st.success(f"✅ Vote recorded: {rate_domain} → Tier {tier}")

        # Attempt to close the window using JS
        st.markdown("""
                <script>
                    setTimeout(() => {
                        window.open('', '_self').close();
                    }, 1500);
                </script>
            """, unsafe_allow_html=True)

    st.stop()



# --- Main Page UI ---
st.title("⚽ Transfer News Tracker")
st.markdown("Track the latest transfer rumours by player or club.")
query = st.text_input("🔍 Enter player or team name:", st.session_state.get("query", "Arda Güler"))
trust_min = st.slider("🔒 Minimum trust level", 1, 10, 5)

if st.button("Search") or "df" not in st.session_state:
    with st.spinner("Fetching latest news..."):
        df = search_google_news_rss(query)
        st.session_state["query"] = query
        st.session_state["df"] = df

if "df" in st.session_state:
    df = st.session_state["df"]
    available_domains = sorted(df["Domain"].unique())
    selected_domains = st.multiselect("🌍 Filter by news source (optional):", options=available_domains, default=available_domains)
    filtered_df = df[(df["Trust"] >= trust_min) & (df["Domain"].isin(selected_domains))].copy()
    filtered_df["ParsedDate"] = filtered_df["Date"].apply(parse_date_safe)
    filtered_df = filtered_df.sort_values("ParsedDate", ascending=False)
    filtered_df["Tier"] = filtered_df["Trust"].apply(trust_score_to_tier)

    st.markdown("### 📄 Filtered Results")
    filtered_df["Snippet"] = filtered_df["Snippet"].str.slice(0, 150) + "..."

    for i, row in filtered_df.iterrows():
        vote_key = f"feedback_{i}"

        with st.container():
            box_col, vote_col = st.columns([6, 1])
            with box_col:
                st.markdown(f"""
                <div style='background-color:#fdfdfd;padding:1.2em;margin-bottom:1.4em;border-radius:12px;border:1px solid #ddd;'>
                    <h4><a href='{row['Link']}' target='_blank' style='text-decoration:none;color:#0056b3;'>{row['Title']}</a></h4>
                    <div style='color:#777;font-size:0.85rem;margin-bottom:0.6em;'>
                        📰 <a href='?rate={row['Domain']}'>{row['Source']}</a> &nbsp;|
                        🌐 {row['Domain']} &nbsp;|
                        🔒 Tier: {row['Tier']} &nbsp;|
                        🕒 {row['Date']}
                    </div>
                    <div style='font-size:0.92rem;color:#444;'>{row['Snippet']}</div>
                </div>
                """, unsafe_allow_html=True)

            with vote_col:
                sentiment = st.feedback("thumbs", key=vote_key)
                if sentiment is not None:
                    # Save user vote to session (optional, for display or control)
                    st.session_state["votes_cast"][vote_key] = sentiment
                    if sentiment == 1:
                        record_vote(row["Domain"], "up")
                        st.toast("⬆️ Liked!")
                    elif sentiment == 0:
                        record_vote(row["Domain"], "down")
                        st.toast("⬇️ Disliked!")


# with st.expander("🛠 Trust Level Maintenance"):
#     if st.button("🔁 Update trust levels from user votes"):
#         promoted = update_trust_levels_from_votes()
#         if promoted:
#             st.success(f"Promoted: {', '.join(promoted)}")
#         else:
#             st.info("No new promotions yet.")


st.markdown("""
<p style="font-size: 0.8rem; text-align: center; color: gray; margin-top: 3rem;">
    <a href="https://iconscout.com/icons/transfer-window" target="_blank">Transfer Window</a> icon by 
    <a href="https://iconscout.com/contributors/wichai-wi" target="_blank">WiStudio</a> on IconScout
</p>
""", unsafe_allow_html=True)
