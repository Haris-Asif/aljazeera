import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict

# Constants
SHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"

REQUIRED_COLUMNS = [
    "Date", "Sector", "Street#", "Plot No#", "Plot Size",
    "Demand/Price", "Description/Details", "Contact"
]

@st.cache_data(ttl=21600)  # Cache for 6 hours
def load_data_from_gsheet():
    # Load credentials from Streamlit secrets
    creds_dict = st.secrets["GCP_JSON"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    # Ensure all expected columns exist
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ''
    return df

def normalize_sector(sector_value):
    if isinstance(sector_value, str):
        sector_value = sector_value.upper().replace(" ", "").replace("_", "-")
    return sector_value

def filter_data(df, sector_filter, street_filter, plot_no_filter, plot_size_filter):
    df_filtered = df.copy()

    if sector_filter:
        sector_filter = sector_filter.upper().replace(" ", "")
        if "/" in sector_filter:
            df_filtered = df_filtered[df_filtered['Sector'].str.upper().str.replace(" ", "").str.contains(sector_filter)]
        else:
            df_filtered = df_filtered[df_filtered['Sector'].str.upper().str.replace(" ", "").str.contains(sector_filter + "/")]

    if street_filter:
        df_filtered = df_filtered[df_filtered['Street#'].astype(str).str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered['Plot No#'].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    if plot_size_filter:
        plot_size_filter = plot_size_filter.replace("*", "x").replace("+", "x").lower()
        parts = plot_size_filter.split("x")
        if len(parts) == 2:
            df_filtered = df_filtered[df_filtered['Plot Size'].astype(str).str.contains(parts[0], case=False, na=False)]
            df_filtered = df_filtered[df_filtered['Plot Size'].astype(str).str.contains(parts[1], case=False, na=False)]
        else:
            df_filtered = df_filtered[df_filtered['Plot Size'].astype(str).str.contains(plot_size_filter, case=False, na=False)]

    return df_filtered

def generate_whatsapp_message(df):
    if df.empty:
        return "No listings to generate WhatsApp message."

    seen = set()
    grouped = defaultdict(list)

    for _, row in df.iterrows():
        sector = str(row["Sector"]).strip()
        plot_size = str(row["Plot Size"]).strip()
        plot_no = str(row["Plot No#"]).strip()
        street = str(row["Street#"]).strip()
        price = str(row["Demand/Price"]).strip()

        dedup_key = (sector, plot_size, plot_no, street)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        group_key = f"{sector}|||{plot_size}"
        grouped[group_key].append(row)

    final_message = ""
    for key, listings in grouped.items():
        sector, plot_size = key.split("|||")
        header = f"*Available Options in {sector} Size: {plot_size}*"
        message_lines = [header]

        for row in listings:
            plot_no = str(row["Plot No#"]).strip()
            street = str(row["Street#"]).strip()
            price = str(row["Demand/Price"]).strip()
            size = str(row["Plot Size"]).strip()

            if "I-15" in sector.replace(" ", "").upper():
                line = f"St: {street} | P: {plot_no} | S: {size} | D: {price}"
            else:
                line = f"P: {plot_no} | S: {size} | D: {price}"

            message_lines.append(line)

        final_message += "\n".join(message_lines) + "\n\n"

    return final_message.strip()

def main():
    st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()

    with st.expander("📋 Apply Filters"):
        sector = st.text_input("Sector (e.g., I-14/1 or I-14)", help="Type 'I-14/1' or just 'I-14' to include all its subsectors.")
        street = st.text_input("Street# (e.g., 27A)")
        plot_no = st.text_input("Plot No# (e.g., 123)")
        plot_size = st.text_input("Plot Size (e.g., 25x50)", help="Use format like 25x50, 30x60 etc.")

    df_filtered = filter_data(df, sector, street, plot_no, plot_size)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[REQUIRED_COLUMNS], use_container_width=True)

    st.markdown("---")
    if st.button("📤 Generate WhatsApp Message"):
        whatsapp_text = generate_whatsapp_message(df_filtered)
        st.text_area("WhatsApp Message", whatsapp_text, height=400)

if __name__ == "__main__":
    main()