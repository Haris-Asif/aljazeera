import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_CSV = "contacts.csv"
REQUIRED_COLUMNS = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Load fresh data from Google Sheet
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records(head=10929)  # Data starts after row 10928
    df = pd.DataFrame(data)

    # Fix: Parse 'Date' column safely
    df["Date"] = pd.to_datetime(df["Date"].astype(str).str.split(",").str[0].str.strip(), errors="coerce")
    return df

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = str(filter_val).strip().upper()
    c = str(cell_val).strip().upper()
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

        if "/" not in sector:
            continue
        sector_key = sector.split("/")[0].upper()
        key = f"{sector}__{plot_size}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((plot_no, plot_size, price, street, sector))

    msg = ""
    for key in sorted(grouped.keys()):
        sector, size = key.split("__")
        listings = grouped[key]
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

def load_contacts():
    try:
        df = pd.read_csv(CONTACTS_CSV)
        return df
    except:
        return pd.DataFrame(columns=["Name", "Contact 1", "Contact 2", "Contact 3"])

def save_contact(name, c1, c2, c3):
    df = load_contacts()
    new_row = {"Name": name, "Contact 1": c1, "Contact 2": c2, "Contact 3": c3}
    df = df.append(new_row, ignore_index=True)
    df.to_csv(CONTACTS_CSV, index=False)

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()

    with st.sidebar:
        st.subheader("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14 or I-14/1)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")

        # Load contact list
        contacts_df = load_contacts()
        contact_names = [""] + contacts_df["Name"].tolist()
        selected_contact_name = st.selectbox("Select Contact Name", contact_names)

        contact_filter = ""
        if selected_contact_name:
            row = contacts_df[contacts_df["Name"] == selected_contact_name].iloc[0]
            nums = [str(row.get(c, "")).strip() for c in ["Contact 1", "Contact 2", "Contact 3"]]
            contact_filter = next((n for n in nums if n), "")

        # Date range filter
        date_filter = st.selectbox("Filter by Date Added", ["", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 60 Days"])

    # Apply filters
    df_filtered = df.copy()

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].astype(str).str.contains(plot_size_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].astype(str).str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    if contact_filter:
        contact_filter = str(contact_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_filter, na=False, case=False)]

    if date_filter:
        days_map = {
            "Last 7 Days": 7,
            "Last 15 Days": 15,
            "Last 30 Days": 30,
            "Last 60 Days": 60
        }
        days = days_map.get(date_filter, 0)
        cutoff = pd.Timestamp.today() - pd.Timedelta(days=days)
        df_filtered = df_filtered[df_filtered["Date"] >= cutoff]

    # Drop duplicates based on key columns
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    # Display results
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[REQUIRED_COLUMNS + ["Description/Details", "Contact"]])

    # WhatsApp message
    if st.button("📤 Generate WhatsApp Message"):
        if df_filtered.empty:
            st.warning("No listings to include.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            st.success("Message generated!")

            # Input WhatsApp number
            number = st.text_input("Enter WhatsApp Number (03xxxxxxxxx):")
            if number.startswith("03") and len(number) == 11:
                intl = f"92{number[1:]}"
                link = f"https://wa.me/{intl}?text={msg.replace(' ', '%20').replace('\n', '%0A')}"
                st.markdown(f"[Click to Send on WhatsApp 🚀]({link})", unsafe_allow_html=True)
            else:
                st.info("Enter number in 03xxxxxxxxx format")

    # Add Contact
    st.subheader("➕ Add New Contact")
    name = st.text_input("Name")
    c1 = st.text_input("Contact 1")
    c2 = st.text_input("Contact 2 (optional)")
    c3 = st.text_input("Contact 3 (optional)")
    if st.button("Save Contact"):
        if name and c1:
            save_contact(name, c1, c2, c3)
            st.success(f"Contact '{name}' saved.")
        else:
            st.warning("Name and Contact 1 are required.")

if __name__ == "__main__":
    main()