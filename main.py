import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import urllib.parse
import os

# Google Sheets setup
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"

# Streamlit setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Contact CSV file path
CONTACTS_FILE = "contacts.csv"

# WhatsApp-required fields
REQUIRED_WHATSAPP_FIELDS = ["Sector", "Plot No#", "Plot Size", "Demand/Price"]

def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return df

def load_contacts():
    if os.path.exists(CONTACTS_FILE):
        return pd.read_csv(CONTACTS_FILE)
    return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def save_contact(name, c1, c2, c3):
    contacts_df = load_contacts()
    new_row = {"Name": name, "Contact1": c1, "Contact2": c2, "Contact3": c3}
    contacts_df = pd.concat([contacts_df, pd.DataFrame([new_row])], ignore_index=True)
    contacts_df.to_csv(CONTACTS_FILE, index=False)

def is_valid_sector(val):
    return isinstance(val, str) and "-" in val and "/" in val

def filter_by_date(df, range_label):
    if "Date" not in df.columns:
        return df
    df["ParsedDate"] = pd.to_datetime(df["Date"], errors="coerce")
    now = datetime.now()
    if range_label == "Last 7 days":
        cutoff = now - timedelta(days=7)
    elif range_label == "Last 2 months":
        cutoff = now - timedelta(days=60)
    else:
        return df
    return df[df["ParsedDate"] >= cutoff]

def generate_whatsapp_message(df):
    message_dict = {}
    for _, row in df.iterrows():
        sector = row.get("Sector", "")
        plot_size = row.get("Plot Size", "")
        plot_no = row.get("Plot No#", "")
        demand = row.get("Demand/Price", "")
        street = row.get("Street#", "")

        if not (sector and plot_size and plot_no and demand):
            continue
        if "I-15/" in sector and not street:
            continue

        key = f"{sector}__{plot_size}"
        if key not in message_dict:
            message_dict[key] = []
        message_dict[key].append((plot_no, plot_size, demand, street, sector))

    msg = ""
    for key in sorted(message_dict.keys()):
        sector, size = key.split("__")
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for plot_no, s, d, street, sec in message_dict[key]:
            if "I-15/" in sec:
                msg += f"St: {street} | P: {plot_no} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {plot_no} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load contacts
    contacts_df = load_contacts()

    # Load all data
    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Error loading Google Sheet: {e}")
        return

    # Sidebar filters
    with st.sidebar:
        st.header("📋 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1)")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        date_range = st.selectbox("Date Range", ["All", "Last 7 days", "Last 2 months"])

        # Saved contact dropdown
        contact_name = st.selectbox("Saved Contact", [""] + list(contacts_df["Name"].unique()))
        contact_filter = ""
        if contact_name:
            contact_row = contacts_df[contacts_df["Name"] == contact_name]
            if not contact_row.empty:
                nums = []
                for col in ["Contact1", "Contact2", "Contact3"]:
                    val = str(contact_row.iloc[0].get(col, "")).strip()
                    if val:
                        nums.append(val)
                if nums:
                    contact_filter = "|".join(nums)

    # Filter logic
    df_filtered = df.copy()

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].astype(str).str.contains(sector_filter, case=False, na=False)]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].astype(str).str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].astype(str).str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(
            lambda val: any(num in val for num in contact_filter.split("|"))
        )]
    if date_range and date_range != "All":
        df_filtered = filter_by_date(df_filtered, date_range)

    # Drop duplicate listings for WhatsApp message
    df_msg = df_filtered.copy()
    df_msg = df_msg.drop_duplicates(subset=["Sector", "Plot Size", "Plot No#", "Street#", "Demand/Price"])

    # Display results
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # WhatsApp Message
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")
    user_number = st.text_input("Enter WhatsApp number (e.g. 03xxxxxxxxx)")
    if st.button("Generate Message"):
        if df_msg.empty:
            st.warning("No listings to include.")
        elif not user_number.strip():
            st.warning("Please enter a number.")
        else:
            msg = generate_whatsapp_message(df_msg)
            encoded_msg = urllib.parse.quote(msg)
            formatted_number = user_number.strip().replace(" ", "")
            if formatted_number.startswith("03"):
                formatted_number = "92" + formatted_number[1:]
            link = f"https://wa.me/{formatted_number}?text={encoded_msg}"
            st.success("Click below to open WhatsApp:")
            st.markdown(f"[📨 Send to {user_number}]({link})", unsafe_allow_html=True)

    # Add Contact
    st.markdown("---")
    st.subheader("➕ Add Contact")
    new_name = st.text_input("Name")
    c1 = st.text_input("Contact 1")
    c2 = st.text_input("Contact 2 (optional)")
    c3 = st.text_input("Contact 3 (optional)")
    if st.button("Save Contact"):
        if new_name and c1:
            save_contact(new_name, c1, c2, c3)
            st.success("Contact saved. Refresh to see in dropdown.")
        else:
            st.warning("Name and Contact 1 are required.")

if __name__ == "__main__":
    main()