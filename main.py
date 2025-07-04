import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
REQUIRED_COLS = ["Sector", "Plot No#", "Plot Size", "Demand/Price"]

# Load fresh data each time
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

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

def add_contact_ui(df):
    st.subheader("➕ Add Contact")
    new_name = st.text_input("Name")
    new_number = st.text_input("Phone Number")
    if st.button("Save Contact"):
        if new_name and new_number:
            st.session_state["contacts"][new_name] = new_number
            st.success(f"Saved contact: {new_name} -> {new_number}")
        else:
            st.warning("Enter both name and number!")

    st.subheader("🔍 Search Listings by Contact")
    search_name = st.text_input("Search by Contact Name")
    if search_name and search_name in st.session_state["contacts"]:
        search_number = st.session_state["contacts"][search_name]
        results = df[df["Contact"].astype(str).str.contains(search_number, na=False)]
        st.write(f"Results for {search_name}:")
        st.dataframe(results)
    elif search_name:
        st.warning("Contact not found.")

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
            for p, s, d, st_, _ in listings:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    if "contacts" not in st.session_state:
        st.session_state["contacts"] = {}

    # Load Google Sheet
    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Failed to load Google Sheet: {e}")
        return

    df = df.fillna("")

    with st.sidebar:
        st.subheader("🔍 Filters")
        st.markdown("Sector format: `I-14`, `I-14/1`, etc.")
        sector_filter = st.text_input("Sector")
        st.markdown("e.g. `25x50`, `30x60`")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")

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

    # Remove duplicate listings by Sector + Plot No# + Plot Size + Street# + Price
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    # Display listings
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # Generate WhatsApp Message
    if st.button("📤 Generate WhatsApp Message"):
        if df_filtered.empty:
            st.warning("No listings to include.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            st.text_area("📄 WhatsApp Message", msg, height=300)

    # Contact Feature
    add_contact_ui(df)

if __name__ == "__main__":
    main()