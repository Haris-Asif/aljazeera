import streamlit as st
import pandas as pd
import urllib.parse
import re
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---------------------------- CONFIG ----------------------------
SHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_FILE = "contacts.csv"
PROPERTIES_FILE = "properties.csv"

# ------------------------ NORMALIZERS ------------------------

def normalize_sector(sector):
    if not isinstance(sector, str):
        return ""
    sector = sector.lower()
    match = re.search(r'i\s*[-/]?\s*(1[456])', sector)
    return f"I-{match.group(1)}" if match else sector.strip().upper()

def normalize_subsector(subsector):
    if not isinstance(subsector, str):
        return ""
    match = re.search(r'([1-4])\b', subsector)
    return match.group(1) if match else ""

def normalize_size(size_str):
    if not isinstance(size_str, str):
        return ""
    return re.sub(r'\s*[*+xX/]\s*', 'x', size_str.strip().lower())

def normalize_phone(phone):
    digits = re.sub(r'\D', '', str(phone))
    if digits.startswith('92') and len(digits) == 12:
        return digits[-10:]
    elif digits.startswith('03') and len(digits) == 11:
        return digits[-10:]
    elif len(digits) >= 10:
        return digits[-10:]
    return digits

# ------------------------ GOOGLE SHEET SYNC ------------------------

@st.cache_data(ttl=21600)  # every 6 hours
def sync_properties_from_google_sheet():
    creds_dict = st.secrets["GCP_JSON"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    df["Normalized Sector"] = df["Sector"].apply(normalize_sector)
    df["Normalized Subsector"] = df["Subsector"].apply(normalize_subsector)
    df["Normalized Size"] = df["Plot Size"].apply(normalize_size)

    df.fillna('', inplace=True)
    df.to_csv(PROPERTIES_FILE, index=False)
    return df

# ------------------------ CONTACT MANAGEMENT ------------------------

def load_contacts():
    if os.path.exists(CONTACTS_FILE):
        return pd.read_csv(CONTACTS_FILE)
    return pd.DataFrame(columns=['Name', 'Contact1', 'Contact2', 'Contact3'])

def save_contact(name, c1, c2, c3):
    df = load_contacts()
    new_row = pd.DataFrame([{
        'Name': name.strip(),
        'Contact1': c1.strip(),
        'Contact2': c2.strip(),
        'Contact3': c3.strip()
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(CONTACTS_FILE, index=False)

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

# ------------------------ STREAMLIT APP ------------------------

def main():
    st.set_page_config(layout="wide")
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = sync_properties_from_google_sheet()
    contacts_df = load_contacts()

    # ---------------------- CONTACT ENTRY ----------------------
    with st.expander("➕ Add Contact"):
        with st.form("add_contact_form", clear_on_submit=True):
            name = st.text_input("Contact Name", key="name")
            c1 = st.text_input("Contact 1", key="c1")
            c2 = st.text_input("Contact 2", key="c2")
            c3 = st.text_input("Contact 3", key="c3")
            if st.form_submit_button("Save"):
                if name and c1:
                    save_contact(name, c1, c2, c3)
                    st.success(f"✅ Contact '{name}' saved.")
                else:
                    st.error("Name and Contact 1 are required.")

    # ---------------------- FILTERS ----------------------
    st.sidebar.title("🔍 Filters")
    sector_input = st.sidebar.text_input("Sector (e.g., I-14)").strip()
    subsector_input = st.sidebar.text_input("Subsector (1-4)").strip()
    size_input = st.sidebar.text_input("Plot Size").strip().lower()
    dealer_input = st.sidebar.selectbox("Dealer", [""] + sorted(contacts_df["Name"].dropna().unique().tolist()))
    street_input = st.sidebar.text_input("Street#").strip()

    df_filtered = df.copy()

    if sector_input:
        normalized_sector = normalize_sector(sector_input)
        df_filtered = df_filtered[df_filtered["Normalized Sector"] == normalized_sector]

    if subsector_input:
        normalized_sub = normalize_subsector(subsector_input)
        df_filtered = df_filtered[df_filtered["Normalized Subsector"] == normalized_sub]

    if size_input:
        norm_size = normalize_size(size_input)
        df_filtered = df_filtered[df_filtered["Normalized Size"] == norm_size]

    if dealer_input:
        numbers = get_contacts_by_name(dealer_input)
        def has_contact(row):
            full_text = " ".join(str(x) for x in row.values)
            return any(normalize_phone(num) in re.sub(r'\D', '', full_text) for num in numbers)
        df_filtered = df_filtered[df_filtered.apply(has_contact, axis=1)]

    if street_input:
        df_filtered = df_filtered[df_filtered['Street#'].astype(str).str.lower().str.contains(street_input.lower())]

    # ---------------------- DISPLAY ----------------------
    st.subheader("📋 Filtered Listings")
    display_cols = ['Date', 'Sector', 'Subsector', 'Plot No#', 'Street#', 'Plot Size', 'Demand/Price', 'Contact', 'Name of Dealer', 'Description/Details']
    st.dataframe(df_filtered[display_cols])

    # ---------------------- WHATSAPP GENERATION ----------------------
    st.subheader("📤 Send WhatsApp Message")
    phone_input = st.text_input("📱 Recipient Phone (e.g., 03001234567)")
    if st.button("Generate WhatsApp Message"):
        if not phone_input:
            st.warning("Please enter recipient phone number.")
            return

        send_df = df_filtered.copy()
        send_df["Norm Size"] = send_df["Plot Size"].apply(normalize_size)
        send_df["SectorKey"] = send_df["Normalized Sector"] + "/" + send_df["Normalized Subsector"]

        seen = set()
        msg_blocks = []

        for (sector_key, size), group in send_df.groupby(["SectorKey", "Norm Size"]):
            rows = []
            for _, row in group.iterrows():
                key = f"{row['SectorKey']}|{row['Plot No#']}|{row['Street#']}|{row['Norm Size']}"
                if key in seen:
                    continue
                seen.add(key)

                prefix = f"St: {row['Street#']} | " if row["Normalized Sector"] == "I-15" else ""
                rows.append(f"{prefix}P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}")

            if rows:
                msg_blocks.append(f"*Available options in {sector_key} - Size: {size}:*\n" + "\n".join(rows))

        final_msg = "\n\n".join(msg_blocks)
        wa_url = f"https://wa.me/92{phone_input.strip()[-10:]}?text={urllib.parse.quote(final_msg)}"
        st.success("✅ Message generated.")
        st.markdown(f"[📨 Send on WhatsApp]({wa_url})", unsafe_allow_html=True)

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    main()
