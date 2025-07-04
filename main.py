import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
GSHEET_HEADER_ROW = 10929  # This is where the header row is
CONTACTS_FILE = "contacts.csv"

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Load contacts
def load_contacts():
    try:
        return pd.read_csv(CONTACTS_FILE).fillna("")
    except:
        return pd.DataFrame(columns=["Name", "Contact 1", "Contact 2", "Contact 3"])

# Add new contact to CSV
def save_contact(name, c1, c2, c3):
    contacts = load_contacts()
    if name.strip() == "" or c1.strip() == "":
        return False, "Name and Contact 1 are required."
    new_row = pd.DataFrame([[name.strip(), c1.strip(), c2.strip(), c3.strip()]], columns=contacts.columns)
    contacts = pd.concat([contacts, new_row], ignore_index=True)
    contacts.to_csv(CONTACTS_FILE, index=False)
    return True, "Contact saved."

# Google Sheets loading
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_values()
    headers = data[GSHEET_HEADER_ROW - 1]
    rows = data[GSHEET_HEADER_ROW:]
    df = pd.DataFrame(rows, columns=headers)
    return df

# Sector matching
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = cell_val.replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# WhatsApp formatting
def format_phone(p):
    p = str(p).strip()
    if p.startswith("03") and len(p) == 11:
        return "+92" + p[1:]
    return ""

# WhatsApp message creation
def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        plot_no = str(row.get("Plot No#", "")).strip()
        price = str(row.get("Demand/Price", "")).strip()
        street = str(row.get("Street#", "")).strip()

        if "/" not in sector:
            continue
        group_key = f"{sector}__{plot_size}"
        if group_key not in grouped:
            grouped[group_key] = []
        grouped[group_key].append((plot_no, plot_size, price, street, sector))

    msg = ""
    for group_key in sorted(grouped.keys()):
        sector, size = group_key.split("__")
        listings = grouped[group_key]
        if "I-15" in sector:
            msg += f"*Available Options in {sector} Size: {size}*\n"
            for p, s, d, st_, _ in listings:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
        else:
            msg += f"*Available Options in {sector} Size: {size}*\n"
            for p, s, d, st_, _ in listings:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

# MAIN APP
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load Data
    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Failed to load Google Sheet: {e}")
        return

    df = df.fillna("")

    # Sidebar Filters
    with st.sidebar:
        st.subheader("🔍 Filters")
        st.markdown("Sector format: `I-14`, `I-14/1`, etc.")
        sector_filter = st.text_input("Sector")
        st.markdown("e.g. `25x50`, `30x60`")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")

        # Dropdown from contacts.csv
        st.markdown("### 📇 Saved Contacts")
        contacts_df = load_contacts()
        if not contacts_df.empty:
            selected_contact = st.selectbox("Select Contact", [""] + contacts_df["Name"].tolist())
            if selected_contact:
                nums = contacts_df[contacts_df["Name"] == selected_contact].iloc[0].tolist()[1:]
                contact_filter = next((n for n in nums if n.strip() != ""), "")

        st.markdown("---")
        st.subheader("➕ Add New Contact")
        name = st.text_input("Name")
        c1 = st.text_input("Contact 1")
        c2 = st.text_input("Contact 2 (optional)")
        c3 = st.text_input("Contact 3 (optional)")
        if st.button("Save Contact"):
            success, msg = save_contact(name, c1, c2, c3)
            if success:
                st.success(msg)
            else:
                st.warning(msg)

    # Apply filters
    df_filtered = df.copy()
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_filter, case=False, na=False)]

    # Deduplicate
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    # Show Data
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # WhatsApp send block
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    phone_input = st.text_input("Enter Number (03xxxxxxxxx format)")
    if st.button("Send on WhatsApp"):
        if df_filtered.empty:
            st.warning("No listings to send.")
        elif not phone_input.startswith("03") or len(phone_input) != 11:
            st.warning("Invalid number format.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            encoded_msg = urllib.parse.quote(msg)
            international = format_phone(phone_input)
            if international:
                link = f"https://wa.me/{international[1:]}?text={encoded_msg}"
                st.markdown(f"[📲 Click here to send message on WhatsApp]({link})", unsafe_allow_html=True)
            else:
                st.warning("Invalid number format for WhatsApp.")

if __name__ == "__main__":
    main()