import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import urllib.parse
import os

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_FILE = "contacts.csv"
COLUMN_ROW = 10929  # Row with column headers
REQUIRED_COLUMNS = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]

# Load Google Sheet (no cache)
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    raw_data = sheet.get_all_values()
    if len(raw_data) < COLUMN_ROW:
        st.error(f"Sheet has fewer than {COLUMN_ROW} rows.")
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    headers = raw_data[COLUMN_ROW - 1]
    data = raw_data[COLUMN_ROW:]
    df = pd.DataFrame(data, columns=headers)
    return df

def standardize_sector(sector_val):
    if isinstance(sector_val, str):
        val = sector_val.replace(" ", "").upper()
        return val
    return ""

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = cell_val.replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

def parse_date_safe(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d , %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except:
            continue
    return None

def add_contact_ui():
    st.subheader("➕ Add Contact")
    new_name = st.text_input("Name")
    new_contact1 = st.text_input("Contact 1")
    new_contact2 = st.text_input("Contact 2 (Optional)")
    new_contact3 = st.text_input("Contact 3 (Optional)")
    if st.button("Save Contact"):
        if new_name and new_contact1:
            contact_df = pd.read_csv(CONTACTS_FILE) if os.path.exists(CONTACTS_FILE) else pd.DataFrame(columns=["Name", "Contact 1", "Contact 2", "Contact 3"])
            new_entry = pd.DataFrame([[new_name, new_contact1, new_contact2, new_contact3]], columns=contact_df.columns)
            contact_df = pd.concat([contact_df, new_entry], ignore_index=True)
            contact_df.to_csv(CONTACTS_FILE, index=False)
            st.success(f"Saved contact: {new_name}")
        else:
            st.warning("Name and Contact 1 are required.")

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
        sector_key = sector.split("/")[0].upper()
        full_group = f"{sector}__{plot_size}"
        if full_group not in grouped:
            grouped[full_group] = []
        grouped[full_group].append((plot_no, plot_size, price, street, sector))

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
            for p, s, d, _, _ in listings:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load Google Sheet
    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Failed to load Google Sheet: {e}")
        return

    df = df.fillna("")
    df = df[df.columns.intersection(REQUIRED_COLUMNS)]
    df["DateParsed"] = df["Date"].apply(parse_date_safe)

    # Load contacts.csv
    contacts_df = pd.read_csv(CONTACTS_FILE) if os.path.exists(CONTACTS_FILE) else pd.DataFrame(columns=["Name", "Contact 1", "Contact 2", "Contact 3"])

    # Sidebar Filters
    with st.sidebar:
        st.subheader("🔍 Filters")
        contact_names = contacts_df["Name"].tolist()
        selected_contact_name = st.selectbox("Select Saved Contact", [""] + contact_names)
        contact_filter = ""
        if selected_contact_name:
            contact_row = contacts_df[contacts_df["Name"] == selected_contact_name]
            nums = contact_row[["Contact 1", "Contact 2", "Contact 3"]].values.flatten().tolist()
            contact_filter = next((n for n in nums if n.strip() != ""), "")

        sector_filter = st.text_input("Sector (e.g. I-14 or I-14/1)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")

        date_filter = st.selectbox("Date Range", ["All", "Last 7 days", "Last 30 days", "Last 60 days"])
        today = datetime.today()

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
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_filter, na=False, case=False)]

    if date_filter != "All":
        days_map = {"Last 7 days": 7, "Last 30 days": 30, "Last 60 days": 60}
        days = days_map.get(date_filter, 0)
        cutoff = today - timedelta(days=days)
        df_filtered = df_filtered[df_filtered["DateParsed"].apply(lambda d: d and d >= cutoff)]

    # Drop duplicates
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    # Show listings
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[REQUIRED_COLUMNS])

    # WhatsApp message
    if st.button("📤 Generate WhatsApp Message"):
        if df_filtered.empty:
            st.warning("No listings to include.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            st.text_area("📄 WhatsApp Message", msg, height=300)

            st.subheader("📲 Send WhatsApp Message")
            send_number = st.text_input("Enter WhatsApp Number (03xxxxxxxxx)")
            if send_number:
                send_number = send_number.strip().replace(" ", "")
                if send_number.startswith("03"):
                    send_number = "92" + send_number[1:]
                encoded_msg = urllib.parse.quote(msg)
                whatsapp_url = f"https://wa.me/{send_number}?text={encoded_msg}"
                st.markdown(f"[Send Message]({whatsapp_url})", unsafe_allow_html=True)

    # Add new contact
    st.divider()
    add_contact_ui()

if __name__ == "__main__":
    main()