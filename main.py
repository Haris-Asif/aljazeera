import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import re
import urllib.parse

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_FILE = "contacts.csv"
REQUIRED_COLUMNS = ["Sector", "Plot No#", "Plot Size", "Demand/Price", "Street#", "Date"]

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    rows = sheet.get_all_values()[10928:]  # Row 10929 is header
    df = pd.DataFrame(rows[1:], columns=rows[0])
    return df

def standardize_sector(sector_val):
    return str(sector_val).replace(" ", "").upper()

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        plot_no = str(row.get("Plot No#", "")).strip()
        price = str(row.get("Demand/Price", "")).strip()
        street = str(row.get("Street#", "")).strip()

        if not sector or not plot_size:
            continue

        key = f"{sector}__{plot_size}"
        grouped.setdefault(key, []).append((plot_no, plot_size, price, street, sector))

    msg = ""
    for key in sorted(grouped):
        sector, size = key.split("__")
        listings = grouped[key]
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for plot, sz, demand, st, sec in listings:
            if "I-15" in sector:
                msg += f"St: {st} | P: {plot} | S: {sz} | D: {demand}\n"
            else:
                msg += f"P: {plot} | S: {sz} | D: {demand}\n"
        msg += "\n"
    return msg.strip()

def filter_by_date(df, option):
    df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
    today = datetime.datetime.now()
    if option == "Last 7 Days":
        return df[df["Date"] >= today - pd.Timedelta(days=7)]
    elif option == "Last 2 Months":
        return df[df["Date"] >= today - pd.DateOffset(months=2)]
    return df

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load data
    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Failed to load Google Sheet: {e}")
        return
    df = df.fillna("")

    # Sidebar filters
    with st.sidebar:
        st.subheader("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g., I-14 or I-14/1)")
        plot_size_filter = st.text_input("Plot Size (e.g., 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        st.markdown("📆 Filter by Date Added")
        date_range = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 2 Months"])

        st.markdown("---")
        st.subheader("👤 Contact Filters")
        selected_contact = None
        contact_df = None

        try:
            contact_df = pd.read_csv(CONTACTS_FILE)
            contact_name = st.selectbox("Search by Saved Contact", [""] + list(contact_df["Name"].dropna()))
            if contact_name:
                contact_row = contact_df[contact_df["Name"] == contact_name]
                nums = [str(contact_row[col].values[0]).strip() for col in ["Contact1", "Contact2", "Contact3"]
                        if col in contact_row.columns and str(contact_row[col].values[0]).strip() != ""]
                if nums:
                    pattern = "|".join(map(re.escape, nums))
                    df = df[df["Contact"].astype(str).str.contains(pattern, na=False, case=False)]
        except Exception as e:
            st.warning("No contacts.csv found or invalid format.")

    # Apply Filters
    df_filtered = df.copy()
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, na=False, case=False)]

    # Date filter
    df_filtered = filter_by_date(df_filtered, date_range)

    # Drop duplicates
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    # Display listings
    st.subheader("📋 Filtered Listings")
    try:
        display_cols = REQUIRED_COLUMNS + ["Description/Details", "Contact"]
        st.dataframe(df_filtered[display_cols])
    except ValueError:
        st.dataframe(df_filtered)

    # WhatsApp Message
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    if not df_filtered.empty:
        msg = generate_whatsapp_message(df_filtered)
        phone_number = st.text_input("📱 Enter WhatsApp Number (03xxxxxxxxx)")
        if st.button("Generate WhatsApp Link"):
            if phone_number.startswith("03") and len(phone_number) == 11:
                link = f"https://wa.me/92{phone_number[1:]}?text={urllib.parse.quote(msg)}"
                st.markdown(f"[Click here to send on WhatsApp]({link})", unsafe_allow_html=True)
            else:
                st.warning("Please enter valid number in format 03xxxxxxxxx.")
    else:
        st.info("No listings available to generate message.")

    # Add Contact
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    name = st.text_input("Contact Name")
    contact1 = st.text_input("Contact 1")
    contact2 = st.text_input("Contact 2 (optional)")
    contact3 = st.text_input("Contact 3 (optional)")
    if st.button("Save Contact"):
        if name and contact1:
            new_entry = pd.DataFrame([[name, contact1, contact2, contact3]],
                                     columns=["Name", "Contact1", "Contact2", "Contact3"])
            try:
                existing = pd.read_csv(CONTACTS_FILE)
                updated = pd.concat([existing, new_entry], ignore_index=True)
            except:
                updated = new_entry
            updated.to_csv(CONTACTS_FILE, index=False)
            st.success("Contact saved successfully.")
        else:
            st.warning("Name and Contact 1 are required!")

if __name__ == "__main__":
    main()