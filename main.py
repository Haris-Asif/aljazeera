# main.py

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# Google Sheet config
SPREADSHEET_ID = '1EXeS9dsKQn4MQaXrb8YEI6CF0wfsh0ANTskOfublZb4'
WORKSHEET_NAME = 'Plots_Sale'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

@st.cache_data(ttl=3600)
def load_data_from_gsheet():
    creds_dict = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(credentials)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def main():
    st.set_page_config(page_title="🏡 Al-Jazeera Real Estate Tool", layout="wide")
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    df.columns = [col.strip() for col in df.columns]

    # Sidebar Filters
    st.sidebar.header("🔎 Filters")
    sector_filter = st.sidebar.text_input("Sector (e.g. I-14 or I-14/1)", help="Type I-14 to match I-14/1, I-14/2 etc.")
    plot_size_filter = st.sidebar.text_input("Plot Size (e.g. 25x50)", help="Enter in format 25x50")
    street_filter = st.sidebar.text_input("Street#")
    plot_no_filter = st.sidebar.text_input("Plot No#")
    contact_filter = st.sidebar.text_input("Contact")

    # Apply filters
    df_filtered = df.copy()

    def contains_all(value, parts):
        return all(part.lower() in str(value).lower() for part in parts)

    if sector_filter:
        if '/' in sector_filter:
            df_filtered = df_filtered[df_filtered['Sector'].str.lower() == sector_filter.lower()]
        else:
            parts = sector_filter.replace('-', ' ').split()
            df_filtered = df_filtered[df_filtered['Sector'].apply(lambda x: contains_all(x, parts))]

    if plot_size_filter:
        parts = plot_size_filter.lower().replace('x', ' ').replace('+', ' ').replace('*', ' ').split()
        df_filtered = df_filtered[df_filtered['Plot Size'].apply(lambda x: contains_all(x, parts))]

    if street_filter:
        df_filtered = df_filtered[df_filtered['Street#'].astype(str).str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered['Plot No#'].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    if contact_filter:
        df_filtered = df_filtered[df_filtered['Contact'].astype(str).str.contains(contact_filter, case=False, na=False)]

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered)

    # Add Contact
    st.subheader("➕ Add Contact")
    with st.form("contact_form"):
        contact_name = st.text_input("Contact Name")
        contact_number = st.text_input("Phone Number")
        submitted = st.form_submit_button("Save Contact")
        if submitted and contact_name and contact_number:
            if 'contacts' not in st.session_state:
                st.session_state['contacts'] = {}
            st.session_state['contacts'][contact_name.strip()] = contact_number.strip()
            st.success("Contact saved!")

    # Search Contact
    st.subheader("🔍 Search Contact")
    search_name = st.text_input("Search by Contact Name")
    if search_name and 'contacts' in st.session_state:
        result = st.session_state['contacts'].get(search_name.strip())
        if result:
            st.success(f"{search_name.strip()} → {result}")
        else:
            st.warning("Contact not found.")

    # WhatsApp Message
    st.subheader("💬 Generate WhatsApp Message")
    if st.button("Generate Message"):
        seen_keys = set()
        messages = []

        def get_sector_parts(sector_val):
            return sector_val.strip().split('/') if '/' in sector_val else [sector_val.strip(), ""]

        for (sector, size), group in df_filtered.groupby(['Sector', 'Plot Size']):
            subsector_group = {}
            for _, row in group.iterrows():
                s = str(row.get("Sector")).strip()
                size = str(row.get("Plot Size")).strip()
                plot = str(row.get("Plot No#", ""))
                street = str(row.get("Street#", ""))
                price = str(row.get("Demand/Price", ""))

                key = (s, street, plot, size)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                sec, sub = get_sector_parts(s)
                full_sec = f"{sec}/{sub}" if sub else sec

                header = f"*Available Options in {full_sec} Size: {size}*"
                line = ""

                if "I-15" in sec:
                    line += f"St: {street} | "
                line += f"P: {plot} | S: {size} | D: {price}"

                if header not in subsector_group:
                    subsector_group[header] = []
                subsector_group[header].append(line)

            for h, lines in subsector_group.items():
                messages.append(h)
                messages.extend(lines)

        final_message = "\n".join(messages)
        st.text_area("📤 WhatsApp Message", final_message, height=400)

if __name__ == "__main__":
    main()