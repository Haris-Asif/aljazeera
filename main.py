import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import re
import os

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_FILE = "contacts.csv"

st.set_page_config("Al-Jazeera Real Estate Tool", layout="wide")
st.title("🏡 Al-Jazeera Real Estate Tool")

# Load contacts
def load_contacts():
    if os.path.exists(CONTACTS_FILE):
        return pd.read_csv(CONTACTS_FILE).fillna("")
    else:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

# Save new contact
def save_contact(name, c1, c2, c3):
    df = load_contacts()
    df.loc[len(df)] = [name, c1, c2, c3]
    df.to_csv(CONTACTS_FILE, index=False)

# Load data from Google Sheet (starts from row 1)
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Validate sector format
def is_valid_sector(sector):
    return isinstance(sector, str) and bool(re.match(r"^[A-Z]-\d+/\d+$", sector.strip()))

# Extract contact numbers from contact row
def extract_contact_numbers(row):
    return [str(row[c]).strip() for c in ["Contact1", "Contact2", "Contact3"] if str(row[c]).strip()]

# Deduplication and validation logic
def clean_and_deduplicate(df):
    discarded = []

    def should_discard(row):
        # Check missing required fields
        required = ["Sector", "Plot Size", "Plot No#", "Demand/Price"]
        for col in required:
            if not str(row.get(col, "")).strip():
                return True
        sector = str(row.get("Sector", ""))
        if not is_valid_sector(sector):
            return True
        # Check for Street# if Sector starts with I-15/
        if sector.startswith("I-15/") and not str(row.get("Street#", "")).strip():
            return True
        return False

    clean_rows = []
    seen = set()

    for _, row in df.iterrows():
        if should_discard(row):
            discarded.append(row)
            continue

        key = (
            row.get("Sector", ""),
            row.get("Street#", ""),
            row.get("Plot No#", ""),
            row.get("Plot Size", ""),
            row.get("Demand/Price", "")
        )

        if key not in seen:
            seen.add(key)
            clean_rows.append(row)
        else:
            discarded.append(row)

    return pd.DataFrame(clean_rows).fillna(""), pd.DataFrame(discarded).fillna("")

# Generate WhatsApp message
def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = row["Sector"]
        plot_size = row["Plot Size"]
        plot_no = row["Plot No#"]
        price = row["Demand/Price"]
        street = row.get("Street#", "")

        group_key = f"{sector}__{plot_size}"
        grouped.setdefault(group_key, []).append((plot_no, plot_size, price, street, sector))

    msg = ""
    for key in grouped:
        sector, size = key.split("__")
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, sec in grouped[key]:
            if "I-15" in sec:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

# Main app
def main():
    contacts_df = load_contacts()

    try:
        raw_df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"❌ Error loading data: {e}")
        return

    raw_df.columns = raw_df.columns.str.strip()
    clean_df, discarded_df = clean_and_deduplicate(raw_df)

    with st.sidebar:
        st.header("🔎 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_text_filter = st.text_input("Contact (Contains)")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 30 Days", "Last 2 Months"])
        selected_name = st.selectbox("Saved Contact", [""] + contacts_df["Name"].tolist())

    df_filtered = clean_df.copy()

    # Apply filters
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].str.upper().str.contains(sector_filter.upper(), na=False)]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, na=False, case=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, na=False, case=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, na=False, case=False)]
    if contact_text_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_text_filter, na=False, case=False)]

    # Filter by date
    if date_filter != "All" and "Date" in df_filtered.columns:
        today = datetime.today()
        if date_filter == "Last 7 Days":
            since = today - timedelta(days=7)
        elif date_filter == "Last 30 Days":
            since = today - timedelta(days=30)
        else:
            since = today - timedelta(days=60)

        def parse_date(date_str):
            try:
                return datetime.strptime(date_str.split(",")[0].strip(), "%Y-%m-%d")
            except:
                return None

        df_filtered["parsed_date"] = df_filtered["Date"].apply(parse_date)
        df_filtered = df_filtered[df_filtered["parsed_date"].notnull()]
        df_filtered = df_filtered[df_filtered["parsed_date"] >= since]

    # Filter by saved contact
    if selected_name:
        row = contacts_df[contacts_df["Name"] == selected_name]
        if not row.empty:
            nums = extract_contact_numbers(row.iloc[0])
            if nums:
                pattern = "|".join(map(re.escape, nums))
                df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(pattern, na=False)]

    # Show filtered data
    st.subheader("📋 Filtered Listings")
    columns = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[columns])

    # WhatsApp message creation
    st.subheader("📤 Generate WhatsApp Message")
    number = st.text_input("Enter WhatsApp Number (e.g. 03xxxxxxxxx)")
    if st.button("Generate & Send"):
        if df_filtered.empty:
            st.warning("No listings to send.")
        elif not number.strip():
            st.warning("Enter a WhatsApp number.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            link = f"https://wa.me/92{number.strip()[1:]}?text={msg.replace(' ', '%20').replace('\n', '%0A')}"
            st.success("Click below to open WhatsApp:")
            st.markdown(f"[💬 Send WhatsApp Message]({link})", unsafe_allow_html=True)

    # Discarded rows
    with st.expander("🚫 View Discarded Listings"):
        st.dataframe(discarded_df)

    # Add new contact
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        cname = st.text_input("Name*", key="cname")
        c1 = st.text_input("Contact 1*", key="c1")
        c2 = st.text_input("Contact 2", key="c2")
        c3 = st.text_input("Contact 3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if cname.strip() and c1.strip():
                save_contact(cname.strip(), c1.strip(), c2.strip(), c3.strip())
                st.success("✅ Contact Saved")
            else:
                st.warning("Name and Contact 1 are required!")

if __name__ == "__main__":
    main()