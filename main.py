import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# Google Sheet configuration
SPREADSHEET_ID = "1EXeS9dsKQn4MQaXrb8YEI6CF0wfsh0ANTskOfublZb4"
WORKSHEET_NAME = "Plots_Sale"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Columns used
REQUIRED_COLUMNS = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]

def load_data_from_gsheet():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    return df

def filter_sector(df, user_sector):
    if not user_sector:
        return df
    user_sector = user_sector.strip().upper()
    if "/" in user_sector:
        return df[df["Sector"].str.upper().str.strip() == user_sector]
    else:
        return df[df["Sector"].str.upper().str.contains(user_sector.replace(" ", ""), na=False)]

def filter_plot_size(df, user_size):
    if not user_size:
        return df
    parts = user_size.replace(" ", "").split("x")
    if len(parts) == 2:
        return df[df["Plot Size"].str.replace(" ", "").str.contains(parts[0]) & df["Plot Size"].str.replace(" ", "").str.contains(parts[1])]
    return df

def generate_whatsapp_message(filtered):
    if filtered.empty:
        return "No data found for the selected filters."

    seen = set()
    message = []

    grouped = filtered.groupby(["Sector", "Plot Size"], dropna=False)
    for (sector, size), group in grouped:
        if not isinstance(sector, str) or not isinstance(size, str):
            continue
        entries = []
        for _, row in group.iterrows():
            key = f"{row['Sector']}_{row['Street#']}_{row['Plot No#']}_{row['Plot Size']}_{row['Demand/Price']}"
            if key in seen:
                continue
            seen.add(key)

            plot = row['Plot No#'] or ''
            street = row['Street#'] or ''
            size = row['Plot Size'] or ''
            demand = row['Demand/Price'] or ''

            if sector.startswith("I-15"):
                entry = f"St: {street} | P: {plot} | S: {size} | D: {demand}"
            else:
                entry = f"P: {plot} | S: {size} | D: {demand}"
            entries.append(entry)

        if entries:
            message.append(f"*Available options in {sector} Size: {size}*")
            message.extend(entries)

    return "\n".join(message)

def main():
    st.set_page_config(page_title="🏡 Al-Jazeera Real Estate Tool", layout="wide")
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load Google Sheet data
    df = load_data_from_gsheet()

    # Sidebar filters
    st.sidebar.header("🔍 Filter Listings")
    sector_filter = st.sidebar.text_input("Sector (e.g. I-14, I-14/1, I-15)", "")
    street_filter = st.sidebar.text_input("Street#", "")
    plot_filter = st.sidebar.text_input("Plot No#", "")
    size_filter = st.sidebar.text_input("Plot Size (e.g. 25x50)", "")
    contact_filter = st.sidebar.text_input("Contact", "")

    # Apply filters
    df_filtered = filter_sector(df, sector_filter)
    df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False) if street_filter else True]
    df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_filter, case=False, na=False) if plot_filter else True]
    df_filtered = filter_plot_size(df_filtered, size_filter)
    df_filtered = df_filtered[df_filtered["Contact"].str.contains(contact_filter, case=False, na=False) if contact_filter else True]

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[REQUIRED_COLUMNS], use_container_width=True)

    # WhatsApp message generation
    if st.button("📤 Generate WhatsApp Message"):
        msg = generate_whatsapp_message(df_filtered)
        st.text_area("📱 WhatsApp Message", value=msg, height=400)

    # Contact save/search
    st.markdown("### ➕ Add Contact")
    with st.form("add_contact_form"):
        plot_number = st.text_input("Plot No#")
        contact_name = st.text_input("Contact Name")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if plot_number and contact_name:
                st.success(f"Saved contact for Plot No# {plot_number}: {contact_name}")
            else:
                st.warning("Please enter both Plot No# and Contact.")

    st.markdown("### 🔍 Search by Contact")
    search_contact = st.text_input("Search Contact")
    if search_contact:
        contact_results = df[df["Contact"].str.contains(search_contact, case=False, na=False)]
        st.dataframe(contact_results[REQUIRED_COLUMNS], use_container_width=True)

if __name__ == "__main__":
    main()