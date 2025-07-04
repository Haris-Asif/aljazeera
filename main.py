import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# Constants
SPREADSHEET_ID = "1EXeS9dsKQn4MQaXrb8YEI6CF0wfsh0ANTskOfublZb4"
WORKSHEET_NAME = "Plots_Sale"
REQUIRED_COLS = ["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"]
DISPLAY_COLS = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]

st.set_page_config(page_title="🏡 Al-Jazeera Real Estate Tool")

# Load Data
@st.cache_data(ttl=3600)
def load_data():
    creds = Credentials.from_service_account_info(st.secrets["GCP_JSON"])
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return df

# Helper: Filter by partial match (case insensitive)
def filter_partial(df, column, keyword):
    return df[df[column].astype(str).str.lower().str.contains(keyword.lower())]

# Main WhatsApp message generation logic
def generate_whatsapp_message(df):
    grouped_messages = []
    df['SectorGroup'] = df['Sector'].apply(lambda s: s.split('/')[0].strip() if isinstance(s, str) else "")
    df = df.drop_duplicates(subset=["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"])
    grouped = df.groupby(["Sector", "Plot Size"])

    for (sector, size), group in grouped:
        if not sector or not size:
            continue

        is_i15 = "I-15" in sector.replace(" ", "").upper()
        lines = []

        for _, row in group.iterrows():
            p = row.get("Plot No#", "")
            s = row.get("Plot Size", "")
            d = row.get("Demand/Price", "")
            st_no = row.get("Street#", "")
            if is_i15:
                lines.append(f"St: {st_no} | P: {p} | S: {s} | D: {d}")
            else:
                lines.append(f"P: {p} | S: {s} | D: {d}")

        if lines:
            header = f"*Available Options in {sector} Size: {size}*"
            message = "\n".join([header] + lines)
            grouped_messages.append(message)

    return "\n\n".join(grouped_messages) if grouped_messages else "No valid listings to generate message."

# App UI
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    df = load_data()

    with st.expander("➕ Add Contact"):
        contact_name = st.text_input("Name to save current filtered listings as (Contact field):")
        if contact_name:
            df.loc[:, "Contact"] = contact_name

    st.markdown("### 📋 Filter Listings")

    sector_input = st.text_input("Sector (e.g. I-14/1, I-15, I-16)", placeholder="I-14/1 or I-14")
    street_input = st.text_input("Street#", placeholder="27A")
    plot_no_input = st.text_input("Plot No#", placeholder="234")
    size_input = st.text_input("Plot Size (e.g. 25x50)", placeholder="25x50")
    contact_filter = st.text_input("Contact (search saved contact):")

    df_filtered = df.copy()

    if sector_input:
        sector_input_clean = sector_input.strip().upper().replace(" ", "")
        if "/" in sector_input_clean:
            df_filtered = filter_partial(df_filtered, "Sector", sector_input_clean)
        else:
            df_filtered = df_filtered[df_filtered["Sector"].astype(str).str.replace(" ", "").str.upper().str.contains(sector_input_clean)]

    if street_input:
        df_filtered = filter_partial(df_filtered, "Street#", street_input)
    if plot_no_input:
        df_filtered = filter_partial(df_filtered, "Plot No#", plot_no_input)
    if size_input:
        parts = size_input.lower().replace(" ", "").replace("*", "x").replace("+", "x").split("x")
        if len(parts) == 2:
            df_filtered = df_filtered[df_filtered["Plot Size"].astype(str).str.contains(parts[0]) & df_filtered["Plot Size"].astype(str).str.contains(parts[1])]

    if contact_filter:
        df_filtered = filter_partial(df_filtered, "Contact", contact_filter)

    if df_filtered.empty:
        st.warning("No listings found for the selected filters.")
    else:
        st.dataframe(df_filtered[DISPLAY_COLS])

        if st.button("📲 Generate WhatsApp Message"):
            message = generate_whatsapp_message(df_filtered)
            st.text_area("WhatsApp Message", value=message, height=300)

if __name__ == "__main__":
    main()