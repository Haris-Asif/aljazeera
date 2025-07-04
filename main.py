import streamlit as st
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials
from datetime import datetime

# Google Sheets Setup
SHEET_NAME = "Plots_Sale"
WORKSHEET_NAME = "Al Jazeera Real Estate & Developers"

# Load credentials from Streamlit secrets
@st.cache_data(ttl=21600)
def load_data_from_gsheet():
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Contact database handling
@st.cache_data
def get_saved_contacts():
    return {}

def save_contact(name, phone):
    contacts = st.session_state.get("contacts", {})
    contacts[name] = phone
    st.session_state["contacts"] = contacts

def find_contact(name):
    return st.session_state.get("contacts", {}).get(name, "")

# WhatsApp formatting helper
def generate_whatsapp_message(df):
    df = df.copy()

    # Remove duplicates based on key fields
    df["key"] = df[["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"]].astype(str).agg("|".join, axis=1)
    df = df.drop_duplicates(subset="key")

    grouped = df.groupby(["Sector", "Plot Size"])

    msg = ""
    for (sector, size), group in grouped:
        if not sector or not size:
            continue

        is_i15 = "I-15" in sector.upper()
        header = f"*Available options in {sector} Size: {size}*"
        msg += header + "\n"

        for _, row in group.iterrows():
            plot_no = str(row.get("Plot No#", "")).strip()
            street = str(row.get("Street#", "")).strip()
            demand = str(row.get("Demand/Price", "")).strip()
            size_val = str(row.get("Plot Size", "")).strip()

            if is_i15:
                line = f"St: {street} | P: {plot_no} | S: {size_val} | D: {demand}"
            else:
                line = f"P: {plot_no} | S: {size_val} | D: {demand}"
            msg += line + "\n"

        msg += "\n"
    return msg.strip()

# Filter function
def apply_filters(df, sector_input, street_input, plot_no_input, size_input):
    df_filtered = df.copy()

    if sector_input:
        sector_input = sector_input.strip()
        if "/" in sector_input:
            df_filtered = df_filtered[df_filtered["Sector"].str.strip().str.upper() == sector_input.upper()]
        else:
            df_filtered = df_filtered[df_filtered["Sector"].str.contains(sector_input.replace("-", ""), case=False, na=False)]

    if street_input:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_input, case=False, na=False)]

    if plot_no_input:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_input, case=False, na=False)]

    if size_input:
        size_parts = size_input.lower().replace("*", "x").replace("+", "x").split("x")
        if len(size_parts) == 2:
            df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(size_parts[0], na=False) &
                                      df_filtered["Plot Size"].str.contains(size_parts[1], na=False)]
        else:
            df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(size_input, case=False, na=False)]

    return df_filtered

# Streamlit UI
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()

    with st.sidebar:
        st.header("🔍 Filters")

        sector_input = st.text_input("Sector (e.g., I-14, I-14/1)", help="Type I-14/1 for exact match or I-14 to match all subsectors")
        street_input = st.text_input("Street# (e.g., 27A)")
        plot_no_input = st.text_input("Plot No#")
        size_input = st.text_input("Plot Size (e.g., 25x50)")

        filtered_df = apply_filters(df, sector_input, street_input, plot_no_input, size_input)

        st.markdown("📥 Save Contact")
        contact_name = st.text_input("Name")
        contact_phone = st.text_input("Phone")
        if st.button("➕ Add Contact"):
            if contact_name and contact_phone:
                save_contact(contact_name, contact_phone)
                st.success(f"Contact '{contact_name}' saved!")

    st.subheader("📋 Filtered Listings")
    st.dataframe(filtered_df)

    st.subheader("📲 Generate WhatsApp Message")
    if st.button("Generate Message"):
        if not filtered_df.empty:
            msg = generate_whatsapp_message(filtered_df)
            st.text_area("📩 WhatsApp Message", value=msg, height=400)
        else:
            st.warning("No listings found to generate message.")

    st.sidebar.markdown("---")
    st.sidebar.header("🔎 Search Contact")
    search_name = st.sidebar.text_input("Search by Name")
    if st.sidebar.button("🔍 Find"):
        phone = find_contact(search_name)
        if phone:
            st.sidebar.success(f"📞 {search_name}: {phone}")
        else:
            st.sidebar.error("Contact not found!")

if __name__ == "__main__":
    main()
