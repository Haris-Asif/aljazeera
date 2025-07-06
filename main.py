import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from urllib.parse import quote
import re
from datetime import datetime, timedelta

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
REQUIRED_COLUMNS = ["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"]
CONTACTS_FILE = "contacts.csv"

st.set_page_config(page_title="🏡 Al-Jazeera Real Estate Tool", layout="wide")

# Load Google Sheet
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def filter_by_date(df, range_label):
    if "Date" not in df.columns:
        return df
    today = datetime.today()
    if range_label == "Last 7 Days":
        cutoff = today - timedelta(days=7)
    elif range_label == "Last 30 Days":
        cutoff = today - timedelta(days=30)
    elif range_label == "Last 2 Months":
        cutoff = today - timedelta(days=60)
    else:
        return df

    def parse_date(val):
        try:
            return datetime.strptime(str(val).split(",")[0].strip(), "%Y-%m-%d")
        except:
            return None

    df["Parsed_Date"] = df["Date"].apply(parse_date)
    return df[df["Parsed_Date"].notna() & (df["Parsed_Date"] >= cutoff)].drop(columns=["Parsed_Date"])

def normalize_number(num):
    return re.sub(r"\D", "", str(num))

def load_contacts():
    try:
        return pd.read_csv(CONTACTS_FILE)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def find_contact_numbers(contact_df, selected_name):
    row = contact_df[contact_df["Name"] == selected_name]
    if row.empty:
        return []
    nums = []
    for col in ["Contact1", "Contact2", "Contact3"]:
        val = str(row.iloc[0].get(col, "")).strip()
        if val:
            nums.append(normalize_number(val))
    return nums

def sector_matches(user_input, cell_value):
    if not user_input:
        return True
    u = user_input.replace(" ", "").upper()
    c = str(cell_value).replace(" ", "").upper()
    if "/" in u:
        return u == c
    return u in c

def generate_whatsapp_message(df):
    def is_valid_listing(row):
        if not all(row.get(col, "").strip() for col in ["Sector", "Plot No#", "Plot Size", "Demand/Price"]):
            return False
        sector_val = str(row.get("Sector", ""))
        if not re.match(r"I-\d{2}/\d", sector_val):
            return False
        if sector_val in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] and not str(row.get("Street#", "")).strip():
            return False
        return True

    df_clean = df[df.apply(is_valid_listing, axis=1)]
    df_clean = df_clean.drop_duplicates(subset=["Sector", "Plot Size", "Plot No#", "Demand/Price", "Street#"])

    grouped = {}
    for _, row in df_clean.iterrows():
        sector = row["Sector"]
        size = row["Plot Size"]
        group_key = f"{sector}__{size}"
        grouped.setdefault(group_key, []).append(row)

    msg = ""
    for group_key, listings in grouped.items():
        sector, size = group_key.split("__")
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for row in listings:
            if sector.startswith("I-15"):
                msg += f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                msg += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        msg += "\n"
    return msg.strip()

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    contacts_df = load_contacts()

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14 or I-14/1)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_input = st.text_input("Search by Phone (03xxxxxxxxx)")
        selected_contact = st.selectbox("📇 Saved Contacts", [""] + contacts_df["Name"].tolist())
        date_filter = st.selectbox("📅 Date Range", ["All", "Last 7 Days", "Last 30 Days", "Last 2 Months"])

    df_filtered = df.copy()

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    # Search by typed contact
    if contact_input:
        number = normalize_number(contact_input)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.replace("-", "").str.contains(number)]

    # Search by selected contact from dropdown
    if selected_contact:
        numbers = find_contact_numbers(contacts_df, selected_contact)
        if numbers:
            pattern = "|".join(numbers)
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.replace("-", "").str.contains(pattern)]

    # Date filter
    if date_filter != "All":
        df_filtered = filter_by_date(df_filtered, date_filter)

    # Show Filtered Listings
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # WhatsApp Message Section
    st.subheader("📤 Send Listings via WhatsApp")
    phone_input = st.text_input("Enter WhatsApp number (03xxxxxxxxx)")
    if st.button("Generate WhatsApp Message"):
        msg = generate_whatsapp_message(df_filtered)
        if msg and phone_input:
            clean_number = normalize_number(phone_input)
            wa_url = f"https://wa.me/92{clean_number.lstrip('0')}?text={quote(msg)}"
            st.markdown(f"[👉 Click to Send WhatsApp Message](%s)" % wa_url, unsafe_allow_html=True)
        elif not msg:
            st.warning("No valid listings to include in message.")

    # Show Duplicate Listings (for admin/debug)
    st.subheader("🗑️ Discarded Listings (Missing or Duplicates)")
    def is_invalid_or_duplicate(row):
        if not all(row.get(col, "").strip() for col in ["Sector", "Plot No#", "Plot Size", "Demand/Price"]):
            return True
        if not re.match(r"I-\d{2}/\d", str(row["Sector"])):
            return True
        if row["Sector"] in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] and not str(row.get("Street#", "")).strip():
            return True
        return False

    discard_df = df[df.apply(is_invalid_or_duplicate, axis=1)]
    st.dataframe(discard_df[display_cols])

if __name__ == "__main__":
    main()