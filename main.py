import streamlit as st
import pandas as pd
import urllib.parse
import re
import json
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

PROPERTIES_FILE = 'properties.csv'
CONTACTS_FILE = 'contacts.csv'

# --- Normalize Helpers ---
def normalize_size(size):
    if pd.isna(size):
        return ""
    return re.sub(r'\s*[*+xX/]\s*', 'x', str(size).strip().lower())

def normalize_sector(value):
    if pd.isna(value):
        return ""
    value = re.sub(r'[^a-zA-Z0-9]', '', str(value)).lower()
    if 'i14' in value:
        return 'i-14'
    elif 'i15' in value:
        return 'i-15'
    elif 'i16' in value:
        return 'i-16'
    return ""

def normalize_subsector(value):
    if pd.isna(value):
        return ""
    match = re.search(r'\b([1-4])\b', str(value))
    return match.group(1) if match else ""

# --- Google Sheets Integration ---
@st.cache_data(ttl=21600)  # refresh every 6 hours
def sync_properties_from_google_sheet():
    creds_dict = json.loads(st.secrets["GCP_JSON"])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    SHEET_NAME = "Al Jazeera Real Estate & Developers"
    WORKSHEET_NAME = "Plots_Sale"

    sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    df.to_csv(PROPERTIES_FILE, index=False)
    return df

# --- Contact Management ---
def load_contacts():
    try:
        return pd.read_csv(CONTACTS_FILE)
    except:
        return pd.DataFrame(columns=['Name', 'Contact1', 'Contact2', 'Contact3'])

def save_contact(name, contact1, contact2, contact3):
    df = load_contacts()
    new_entry = pd.DataFrame([{
        'Name': name.strip(),
        'Contact1': contact1.strip(),
        'Contact2': contact2.strip(),
        'Contact3': contact3.strip()
    }])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(CONTACTS_FILE, index=False)

def normalize_phone(phone):
    digits = re.sub(r'\D', '', str(phone))
    if digits.startswith('92') and len(digits) == 12:
        return digits[-10:]
    elif digits.startswith('03') and len(digits) == 11:
        return digits[-10:]
    elif len(digits) >= 10:
        return digits[-10:]
    return digits

def get_contacts_by_name(name_input):
    df = load_contacts()
    name_input = name_input.strip().lower()
    matches = df[df['Name'].str.lower().str.contains(name_input)]
    numbers = set()
    for _, row in matches.iterrows():
        for num in [row['Contact1'], row['Contact2'], row['Contact3']]:
            if pd.notna(num) and str(num).strip():
                numbers.add(normalize_phone(num))
    return numbers

# --- Main App ---
def main():
    st.set_page_config(layout="wide")
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # --- Sync & Load ---
    df = sync_properties_from_google_sheet()
    df.fillna('', inplace=True)

    # Normalize columns
    df["NormalizedSector"] = df["Sector"].apply(normalize_sector)
    df["NormalizedSubsector"] = df["Subsector"].apply(normalize_subsector)
    df["NormalizedSize"] = df["Plot Size"].apply(normalize_size)

    # --- Sidebar Filters ---
    st.sidebar.title("🔍 Filters")
    contacts = load_contacts()
    dealer_list = sorted(contacts['Name'].dropna().unique())
    selected_dealer = st.sidebar.selectbox("Select Dealer", [""] + dealer_list)
    manual_dealer = st.sidebar.text_input("Or type Dealer Name").strip()
    sector_input = st.sidebar.text_input("Sector (e.g., I-14)").strip().lower()
    subsector_input = st.sidebar.text_input("Subsector (e.g., 1)").strip()
    street_input = st.sidebar.text_input("Street#").strip().lower()
    size_input = st.sidebar.text_input("Plot Size").strip().lower()
    plot_input = st.sidebar.text_input("Plot#").strip().lower()

    df_filtered = df.copy()

    # Sector Filter
    if sector_input:
        target = normalize_sector(sector_input)
        df_filtered = df_filtered[df_filtered['NormalizedSector'] == target]

    # Subsector Filter
    if subsector_input:
        df_filtered = df_filtered[df_filtered['NormalizedSubsector'] == subsector_input]

    # Dealer Filter
    dealer_final = manual_dealer or selected_dealer
    if dealer_final:
        contact_numbers = get_contacts_by_name(dealer_final)
        if contact_numbers:
            def row_match(row):
                combined = " ".join(str(x) for x in row)
                return any(normalize_phone(num) in re.sub(r'\D', '', combined) for num in contact_numbers)
            df_filtered = df_filtered[df_filtered.apply(row_match, axis=1)]

    if street_input:
        df_filtered = df_filtered[df_filtered['Street#'].astype(str).str.lower().str.contains(street_input)]

    if size_input:
        df_filtered = df_filtered[df_filtered['NormalizedSize'] == normalize_size(size_input)]

    if plot_input:
        df_filtered = df_filtered[df_filtered['Plot No#'].astype(str).str.lower().str.contains(plot_input)]

    # --- Display Filtered Results ---
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[['Date', 'Sector', 'Subsector', 'Plot No#', 'Street#', 'Plot Size', 'Demand/Price', 'Contact', 'Name of Dealer']])

    # --- Add Contact ---
    with st.expander("➕ Add Contact"):
        with st.form("add_contact_form", clear_on_submit=True):
            name = st.text_input("Name", key="name")
            c1 = st.text_input("Contact 1", key="c1")
            c2 = st.text_input("Contact 2", key="c2")
            c3 = st.text_input("Contact 3", key="c3")
            if st.form_submit_button("Save"):
                if name and c1:
                    save_contact(name, c1, c2, c3)
                    st.success("✅ Contact saved successfully.")
                else:
                    st.warning("❗ Name and Contact 1 are required.")

    # --- WhatsApp Message Generator ---
    st.subheader("📤 Send WhatsApp Message")
    phone_input = st.text_input("Enter number (e.g., 03001234567)")

    if st.button("Generate WhatsApp Message"):
        if not phone_input:
            st.warning("⚠️ Please enter phone number.")
        else:
            msg_df = df_filtered.copy()
            if msg_df.empty:
                st.warning("No listings found.")
            else:
                msg_df['GroupKey'] = msg_df['NormalizedSector'] + "/" + msg_df['NormalizedSubsector'] + "||" + msg_df['NormalizedSize']
                grouped = msg_df.drop_duplicates(subset=['NormalizedSector', 'NormalizedSubsector', 'NormalizedSize', 'Plot No#', 'Street#'])

                result = []
                for (groupkey), group_df in grouped.groupby('GroupKey'):
                    sector_part, size_part = groupkey.split("||")
                    if not sector_part or not size_part:
                        continue
                    header = f"*Available options in {sector_part}/{group_df['NormalizedSubsector'].iloc[0]} - Size: {size_part}*"
                    listings = []
                    for _, row in group_df.iterrows():
                        sector = normalize_sector(row['Sector'])
                        line = ""
                        if sector == "i-15":
                            line = f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}"
                        else:
                            line = f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}"
                        listings.append(line)
                    result.append(header + "\n" + "\n".join(listings))

                message = "\n\n".join(result)
                number = "92" + phone_input.strip().lstrip("0")
                encoded = urllib.parse.quote(message)
                url = f"https://wa.me/{number}?text={encoded}"

                st.success("✅ WhatsApp message generated!")
                st.markdown(f"[📨 Send Message]({url})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
