import streamlit as st
import pandas as pd
import urllib.parse
import re
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

PROPERTIES_FILE = 'properties.csv'
CONTACTS_FILE = 'contacts.csv'
GOOGLE_SHEET_NAME = 'Al Jazeera Real Estate & Developers'
GOOGLE_WORKSHEET_NAME = 'Plots_Sale'
SYNC_INTERVAL_HOURS = 6

# ---------------------- Normalization Helpers ----------------------

def normalize_phone(phone):
    digits = re.sub(r'\D', '', str(phone))
    if digits.startswith('92') and len(digits) == 12:
        return digits[-10:]
    elif digits.startswith('03') and len(digits) == 11:
        return digits[-10:]
    elif len(digits) >= 10:
        return digits[-10:]
    return digits

def normalize_size(size_str):
    if not isinstance(size_str, str):
        return ''
    return re.sub(r'\s*[*+xX/]\s*', 'x', size_str.strip().lower())

def normalize_sector(sector):
    if not isinstance(sector, str):
        return ''
    sector = sector.lower()
    for target in ['i14', 'i15', 'i16']:
        if target in re.sub(r'[^a-zA-Z0-9]', '', sector):
            return 'i-' + target[-2:]
    return sector

def normalize_subsector(subsector):
    if not isinstance(subsector, str):
        return ''
    digits = re.findall(r'\b[1-4]\b', subsector)
    return digits[0] if digits else ''

# ---------------------- Google Sheet Sync ----------------------

@st.cache_data(ttl=60 * 60 * SYNC_INTERVAL_HOURS)
def sync_properties_from_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open(GOOGLE_SHEET_NAME).worksheet(GOOGLE_WORKSHEET_NAME)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.to_csv(PROPERTIES_FILE, index=False)
    return df

# ---------------------- Contact Management ----------------------

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

# ---------------------- Streamlit App ----------------------

def main():
    st.set_page_config(layout="wide")
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = sync_properties_from_google_sheet()
    df.fillna('', inplace=True)
    df['NormalizedSector'] = df['Sector'].apply(normalize_sector)
    df['NormalizedSubsector'] = df['Subsector'].apply(normalize_subsector)
    df['NormalizedSize'] = df['Plot Size'].apply(normalize_size)

    # -------------------- Contact Form --------------------
    with st.expander("➕ Add Contact Manually"):
        with st.form("contact_form", clear_on_submit=True):
            name = st.text_input("Name*", key="contact_name")
            c1 = st.text_input("Contact 1*", key="c1")
            c2 = st.text_input("Contact 2", key="c2")
            c3 = st.text_input("Contact 3", key="c3")
            submitted = st.form_submit_button("Save Contact")
            if submitted:
                if name and c1:
                    save_contact(name, c1, c2, c3)
                    st.success(f"✅ Contact '{name}' saved.")
                else:
                    st.error("❌ Name and Contact 1 are required.")

    # -------------------- Filters --------------------
    st.sidebar.title("🔍 Filters")
    contact_df = load_contacts()
    name_list = sorted(contact_df['Name'].dropna().unique())
    selected_name = st.sidebar.selectbox("Select Dealer", [""] + name_list)
    typed_name = st.sidebar.text_input("Or type dealer name")
    sector_input = st.sidebar.text_input("Sector (e.g. I-14)")
    subsector_input = st.sidebar.text_input("Subsector (e.g. 1)")
    size_input = st.sidebar.text_input("Plot Size (e.g. 25x50)")
    street_input = st.sidebar.text_input("Street#")
    plot_input = st.sidebar.text_input("Plot#")

    effective_name = typed_name.strip() or selected_name
    filtered = df.copy()

    if sector_input:
        sn = normalize_sector(sector_input)
        filtered = filtered[filtered['NormalizedSector'] == sn]

    if subsector_input:
        ss = normalize_subsector(subsector_input)
        filtered = filtered[filtered['NormalizedSubsector'] == ss]

    if effective_name:
        numbers = get_contacts_by_name(effective_name)
        if numbers:
            def row_has_number(row):
                text = " ".join(str(x) for x in row)
                return any(normalize_phone(num) in re.sub(r'\D', '', text) for num in numbers)
            filtered = filtered[filtered.apply(row_has_number, axis=1)]

    if street_input:
        filtered = filtered[filtered['Street#'].astype(str).str.contains(street_input.strip(), case=False)]

    if plot_input:
        filtered = filtered[filtered['Plot No#'].astype(str).str.contains(plot_input.strip(), case=False)]

    if size_input:
        norm_size = normalize_size(size_input)
        filtered = filtered[filtered['NormalizedSize'] == norm_size]

    st.subheader("📋 Filtered Listings")
    st.dataframe(filtered[['Date', 'Sector', 'Subsector', 'Plot No#', 'Street#', 'Plot Size', 'Demand/Price', 'Contact', 'Name of Dealer']])

    # -------------------- WhatsApp Message --------------------
    st.subheader("📤 Share via WhatsApp")
    with st.expander("Create WhatsApp Message"):
        phone_input = st.text_input("Enter WhatsApp Number (e.g., 03001234567)")
        if st.button("Generate WhatsApp Message"):
            if not phone_input:
                st.warning("⚠️ Enter recipient number.")
                return

            normalized_num = "92" + phone_input.lstrip("0")
            grouped_msg = []
            seen = set()

            for (sector, subsector, size), group in filtered.groupby(['NormalizedSector', 'NormalizedSubsector', 'NormalizedSize']):
                display_sector = sector.upper().replace("I", "I-").replace("--", "-")
                block_label = f"{display_sector}/{subsector}" if subsector else display_sector
                header = f"*Available options in {block_label} - Size: {size}:*"
                rows = []
                for _, row in group.iterrows():
                    key = f"{row['Plot Size']}_{row['Street#']}_{row['Sector']}_{row['Subsector']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    if display_sector.startswith("I-15"):
                        rows.append(f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}")
                    else:
                        rows.append(f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}")
                if rows:
                    grouped_msg.append(header + '\n' + '\n'.join(rows))

            full_msg = "\n\n".join(grouped_msg)
            encoded = urllib.parse.quote(full_msg)
            wa_url = f"https://wa.me/{normalized_num}?text={encoded}"
            st.success("✅ WhatsApp message generated!")
            st.markdown(f"[📨 Send Message]({wa_url})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
