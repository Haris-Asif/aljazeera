import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import re

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_CSV = "contacts.csv"

REQUIRED_COLUMNS = ["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"]
VALID_I15_SECTORS = ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]

def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def filter_by_date(df, date_range):
    if date_range == "All":
        return df

    today = datetime.datetime.today()
    if date_range == "Last 7 Days":
        cutoff = today - datetime.timedelta(days=7)
    elif date_range == "Last 1 Month":
        cutoff = today - datetime.timedelta(days=30)
    elif date_range == "Last 2 Months":
        cutoff = today - datetime.timedelta(days=60)
    else:
        return df

    def parse_date(val):
        try:
            return datetime.datetime.strptime(val.split(",")[0], "%Y-%m-%d")
        except:
            return None

    df["Parsed_Date"] = df["Date"].apply(parse_date)
    return df[df["Parsed_Date"].notna() & (df["Parsed_Date"] >= cutoff)]

def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        plot_no = str(row.get("Plot No#", "")).strip()
        price = str(row.get("Demand/Price", "")).strip()
        street = str(row.get("Street#", "")).strip()

        if not all([sector, plot_size, plot_no, price]):
            continue
        if sector in VALID_I15_SECTORS and not street:
            continue

        group_key = f"{sector}__{plot_size}"
        if group_key not in grouped:
            grouped[group_key] = []

        grouped[group_key].append((plot_no, plot_size, price, street, sector))

    msg = ""
    for group_key in sorted(grouped.keys()):
        sector, size = group_key.split("__")
        listings = grouped[group_key]
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, sec in listings:
            if sec in VALID_I15_SECTORS:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Failed to load Google Sheet: {e}")
        return

    df = df.fillna("")

    # Sidebar Filters
    with st.sidebar:
        st.subheader("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 1 Month", "Last 2 Months"])

        # Load contacts.csv
        contact_df = pd.read_csv(CONTACTS_CSV) if CONTACTS_CSV else pd.DataFrame()
        contact_name = st.selectbox("📇 Select Saved Contact", [""] + sorted(contact_df["Name"].dropna().unique()) if not contact_df.empty else [""])

    df_filtered = df.copy()

    # Apply filters
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].str.contains(sector_filter, case=False, na=False)]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    if contact_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_filter, na=False, case=False)]

    if contact_name:
        contact_row = contact_df[contact_df["Name"] == contact_name]
        if not contact_row.empty:
            nums = []
            for col in ["Contact1", "Contact2", "Contact3"]:
                raw_num = str(contact_row[col].values[0]) if col in contact_row else ""
                if raw_num and raw_num.strip():
                    nums.append(re.sub(r"[^0-9]", "", raw_num))
            if nums:
                pattern = "|".join(map(re.escape, nums))
                df_filtered = df_filtered[
                    df_filtered["Contact"].astype(str).apply(lambda x: re.sub(r"[^0-9]", "", x)).str.contains(pattern, na=False, case=False)
                ]

    df_filtered = filter_by_date(df_filtered, date_filter)

    # Remove duplicate listings
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"])

    # Display
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # WhatsApp section
    st.markdown("---")
    st.subheader("📤 WhatsApp Message")

    wa_number = st.text_input("Enter WhatsApp Number (e.g., 03xxxxxxxxx)")
    if st.button("Generate WhatsApp Message"):
        if df_filtered.empty:
            st.warning("No listings to include.")
        else:
            message = generate_whatsapp_message(df_filtered)
            st.text_area("📄 Message", message, height=300)
            if wa_number:
                wa_link = f"https://wa.me/92{wa_number.lstrip('0')}?text={re.sub(' ', '%20', message)}"
                st.markdown(f"[💬 Click to Send on WhatsApp]({wa_link})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()