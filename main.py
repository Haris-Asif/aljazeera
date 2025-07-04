import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse
import datetime
import os

# Config
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
START_ROW_INDEX = 10928  # Header is in 10929, data starts from 10930
REQUIRED_COLUMNS = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"]

# --- Load Google Sheets Data ---
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    all_values = sheet.get_all_values()
    header = all_values[START_ROW_INDEX]
    data_rows = all_values[START_ROW_INDEX + 1:]
    df = pd.DataFrame(data_rows, columns=header)
    return df

# --- Utility ---
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = cell_val.replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

def clean_date(val):
    try:
        return pd.to_datetime(val, errors="coerce")
    except:
        return pd.NaT

# --- Contact Management ---
def load_contacts():
    if os.path.exists("contacts.csv"):
        return pd.read_csv("contacts.csv").fillna("")
    return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def save_contact(name, c1, c2, c3):
    df = load_contacts()
    new = pd.DataFrame([[name, c1, c2, c3]], columns=["Name", "Contact1", "Contact2", "Contact3"])
    df = pd.concat([df, new], ignore_index=True)
    df.to_csv("contacts.csv", index=False)

# --- WhatsApp Message Generator ---
def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = row.get("Sector", "").strip()
        size = row.get("Plot Size", "").strip()
        plot_no = row.get("Plot No#", "").strip()
        price = row.get("Demand/Price", "").strip()
        street = row.get("Street#", "").strip()

        if not sector or not size:
            continue

        key = f"{sector}__{size}"
        if key not in grouped:
            grouped[key] = []

        grouped[key].append((plot_no, size, price, street, sector))

    msg = ""
    for key in sorted(grouped.keys()):
        sector, size = key.split("__")
        listings = grouped[key]
        if "I-15" in sector:
            msg += f"*Available Options in {sector} Size: {size}*\n"
            for p, s, d, st, _ in listings:
                msg += f"St: {st} | P: {p} | S: {s} | D: {d}\n"
        else:
            msg += f"*Available Options in {sector} Size: {size}*\n"
            for p, s, d, st, _ in listings:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

# --- Main App ---
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load data
    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Error loading Google Sheet: {e}")
        return

    df = df.fillna("")
    df["Date"] = df["Date"].apply(clean_date)

    # --- Sidebar Filters ---
    with st.sidebar:
        st.subheader("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g., I-14 or I-14/1)")
        plot_size_filter = st.text_input("Plot Size (e.g., 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_number_filter = st.text_input("Contact (03xxxxxxxxx)")
        date_range = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 2 Months"])

        contacts_df = load_contacts()
        contact_names = contacts_df["Name"].tolist()
        selected_contact = st.selectbox("Filter by Saved Contact", ["None"] + contact_names)

    # --- Apply Filters ---
    df_filtered = df.copy()

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].str.contains(plot_no_filter, case=False, na=False)]

    if contact_number_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_number_filter, case=False, na=False)]

    if selected_contact != "None":
        contact_row = contacts_df[contacts_df["Name"] == selected_contact]
        nums = [str(contact_row[col].values[0]) for col in ["Contact1", "Contact2", "Contact3"] if str(contact_row[col].values[0]).strip() != ""]
        if nums:
            pattern = "|".join(map(re.escape, nums))
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(pattern, case=False, na=False)]

    if date_range == "Last 7 Days":
        threshold = pd.to_datetime(datetime.datetime.now() - datetime.timedelta(days=7))
        df_filtered = df_filtered[df_filtered["Date"] >= threshold]
    elif date_range == "Last 2 Months":
        threshold = pd.to_datetime(datetime.datetime.now() - datetime.timedelta(days=60))
        df_filtered = df_filtered[df_filtered["Date"] >= threshold]

    # --- Remove Duplicates ---
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    # --- Display Listings ---
    st.subheader("📋 Filtered Listings")
    display_cols = REQUIRED_COLUMNS + ["Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # --- WhatsApp Message Generator ---
    msg = ""
    send_number = st.text_input("Enter WhatsApp Number (03xxxxxxxxx)")
    if st.button("📤 Generate WhatsApp Message"):
        if df_filtered.empty:
            st.warning("No listings to include.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            st.text_area("📄 WhatsApp Message", msg, height=300)

            if send_number:
                num = send_number.strip().replace(" ", "")
                if num.startswith("03"):
                    num = "92" + num[1:]
                encoded_msg = urllib.parse.quote(msg)
                url = f"https://wa.me/{num}?text={encoded_msg}"
                st.markdown(f"👉 [Click here to send WhatsApp Message](https://wa.me/{num}?text={encoded_msg})", unsafe_allow_html=True)

    # --- Add Contact Section ---
    st.subheader("➕ Add New Contact")
    name = st.text_input("Contact Name")
    c1 = st.text_input("Contact 1 (required)")
    c2 = st.text_input("Contact 2 (optional)")
    c3 = st.text_input("Contact 3 (optional)")
    if st.button("Save Contact"):
        if name and c1:
            save_contact(name, c1, c2, c3)
            st.success(f"Saved {name} to contacts.")
        else:
            st.warning("Name and Contact 1 are required.")

if __name__ == "__main__":
    main()