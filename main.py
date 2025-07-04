import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"

REQUIRED_DISPLAY_COLS = [
    "Date", "Sector", "Street#", "Plot No#", "Plot Size",
    "Demand/Price", "Description/Details", "Contact"
]

# Load fresh data every time
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    worksheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

def sector_matches(user_input, cell_val):
    if not user_input:
        return True
    user_input = user_input.replace(" ", "").upper()
    cell_val = cell_val.replace(" ", "").upper()
    if "/" in user_input:
        return user_input == cell_val
    return user_input in cell_val

def generate_whatsapp_message(df):
    grouped_msgs = {}
    for _, row in df.iterrows():
        sector = str(row["Sector"]).strip().upper()
        plot_size = str(row["Plot Size"]).strip()
        plot_no = str(row["Plot No#"]).strip()
        price = str(row["Demand/Price"]).strip()
        street = str(row["Street#"]).strip()

        key = f"{sector}__{plot_size}"
        grouped_msgs.setdefault(key, []).append((plot_no, plot_size, price, street))

    message = ""
    for key in sorted(grouped_msgs.keys()):
        sector, size = key.split("__")
        listings = grouped_msgs[key]

        message += f"*Available Options in {sector} Size: {size}*\n"
        for plot_no, plot_size, price, street in listings:
            if "I-15" in sector:
                message += f"St: {street} | P: {plot_no} | S: {plot_size} | D: {price}\n"
            else:
                message += f"P: {plot_no} | S: {plot_size} | D: {price}\n"
        message += "\n"
    return message.strip()

def contact_ui(df):
    st.subheader("➕ Add Contact")
    new_name = st.text_input("Name")
    new_number = st.text_input("Phone Number")
    if st.button("Save Contact"):
        if new_name and new_number:
            st.session_state.contacts[new_name] = new_number
            st.success(f"Saved: {new_name} -> {new_number}")
        else:
            st.warning("Enter both name and number!")

    st.subheader("🔍 Search by Contact")
    search_name = st.text_input("Search Contact Name")
    if search_name:
        if search_name in st.session_state.contacts:
            phone = st.session_state.contacts[search_name]
            results = df[df["Contact"].astype(str).str.contains(phone)]
            st.dataframe(results)
        else:
            st.warning("Contact not found.")

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    if "contacts" not in st.session_state:
        st.session_state.contacts = {}

    try:
        df = load_data_from_gsheet()
        df = df.fillna("")
    except Exception as e:
        st.error(f"Failed to load Google Sheet: {e}")
        return

    with st.sidebar:
        st.subheader("🔎 Filters")
        st.markdown("**Sector (e.g. I-14 or I-14/1)**")
        sector_filter = st.text_input("Sector")
        st.markdown("**Plot Size (e.g. 25x50)**")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact")

    # Filtering
    df_filtered = df.copy()

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, str(x)))]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    if contact_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_filter, case=False, na=False)]

    # Deduplicate before WhatsApp message
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[REQUIRED_DISPLAY_COLS])

    if st.button("📤 Generate WhatsApp Message"):
        if df_filtered.empty:
            st.warning("No listings available for message.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            st.text_area("📄 WhatsApp Message", msg, height=300)

    contact_ui(df)

if __name__ == "__main__":
    main()