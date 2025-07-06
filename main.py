import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import urllib.parse
from datetime import datetime, timedelta

# --- Config ---
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_CSV = "contacts.csv"
REQUIRED_COLUMNS = ["Sector", "Plot No#", "Plot Size", "Demand/Price"]
I15_SUBSECTORS = ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]

# --- Load Data ---
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# --- Sector Matching ---
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = cell_val.replace(" ", "").upper()
    return f in c if "/" not in f else f == c

# --- Filter WhatsApp Listings ---
def filter_whatsapp_ready(df):
    def is_valid(row):
        if not all(row.get(col, "").strip() for col in ["Sector", "Plot Size", "Plot No#", "Demand/Price"]):
            return False
        if row["Sector"].strip() in I15_SUBSECTORS and not row.get("Street#", "").strip():
            return False
        return True

    df = df[df.apply(is_valid, axis=1)]

    def dedup_key(row):
        key = (
            row["Sector"],
            row["Plot No#"],
            row["Plot Size"],
            row["Demand/Price"],
        )
        if row["Sector"] in I15_SUBSECTORS:
            key += (row.get("Street#", ""),)
        return key

    df = df.drop_duplicates(subset=df.apply(dedup_key, axis=1))
    return df

# --- WhatsApp Message Generator ---
def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = row["Sector"]
        size = row["Plot Size"]
        key = f"{sector}__{size}"
        grouped.setdefault(key, []).append(row)

    msg = ""
    for group_key in sorted(grouped.keys()):
        sector, size = group_key.split("__")
        listings = grouped[group_key]
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for row in listings:
            if sector in I15_SUBSECTORS:
                msg += f"St: {row.get('Street#', '')} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                msg += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        msg += "\n"
    return msg.strip()

# --- Add & Search Contacts ---
def load_contacts():
    try:
        return pd.read_csv(CONTACTS_CSV)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def save_contact(name, c1, c2, c3):
    contacts = load_contacts()
    new_row = pd.DataFrame([{"Name": name, "Contact1": c1, "Contact2": c2, "Contact3": c3}])
    contacts = pd.concat([contacts, new_row], ignore_index=True)
    contacts.to_csv(CONTACTS_CSV, index=False)

# --- App Entry Point ---
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Google Sheet Error: {e}")
        return

    df = df.fillna("")

    with st.sidebar:
        st.subheader("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14, I-15/1)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact")
        date_range = st.selectbox("Date Filter", ["All", "Last 7 Days", "Last 2 Months"])

        st.subheader("📇 Search Saved Contact")
        contacts = load_contacts()
        contact_names = contacts["Name"].tolist()
        selected_name = st.selectbox("Select Contact", [""] + contact_names)
        if selected_name:
            contact_row = contacts[contacts["Name"] == selected_name]
            nums = [str(contact_row.iloc[0][col]) for col in ["Contact1", "Contact2", "Contact3"] if pd.notna(contact_row.iloc[0][col]) and str(contact_row.iloc[0][col]).strip()]
            if nums:
                pattern = "|".join(map(re.escape, nums))
                df = df[df["Contact"].astype(str).str.contains(pattern, case=False, na=False)]

    df_filtered = df.copy()

    # Apply filters
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

    # Date Filter
    if date_range != "All":
        today = datetime.now()
        df_filtered["Parsed Date"] = pd.to_datetime(df_filtered["Date"].str.split(",").str[0], errors="coerce")
        if date_range == "Last 7 Days":
            threshold = today - timedelta(days=7)
        else:
            threshold = today - timedelta(days=60)
        df_filtered = df_filtered[df_filtered["Parsed Date"] >= threshold]

    # --- Display Listings ---
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]])

    # --- WhatsApp Message & Link ---
    st.subheader("📤 Send WhatsApp Message")
    user_number = st.text_input("Enter WhatsApp Number (e.g. 03XXXXXXXXX)")
    if st.button("Generate WhatsApp Message"):
        df_msg = filter_whatsapp_ready(df_filtered.copy())
        if df_msg.empty:
            st.warning("No valid listings to generate message.")
        else:
            message = generate_whatsapp_message(df_msg)
            st.text_area("Message Preview", message, height=300)
            if user_number:
                wa_number = "92" + user_number.strip()[-10:]  # Pakistani format
                encoded_msg = urllib.parse.quote(message)
                wa_link = f"https://wa.me/{wa_number}?text={encoded_msg}"
                st.markdown(f"[📨 Send to WhatsApp]({wa_link})", unsafe_allow_html=True)

    # --- Add Contact ---
    st.subheader("➕ Add New Contact")
    with st.form("add_contact_form"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact 1*", key="c1")
        c2 = st.text_input("Contact 2 (optional)", key="c2")
        c3 = st.text_input("Contact 3 (optional)", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1:
                save_contact(name, c1, c2, c3)
                st.success("Contact saved!")
            else:
                st.error("Name and Contact 1 are required.")

if __name__ == "__main__":
    main()