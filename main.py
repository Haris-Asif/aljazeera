import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_FILE = "contacts.csv"

# Load Google Sheet data
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Normalize plot size
def normalize_plot_size(size):
    if pd.isna(size): return ""
    return re.sub(r"[+xX*]", "x", str(size).strip())

# Check for valid sector
def is_valid_sector(sector):
    if not isinstance(sector, str): return False
    return bool(re.fullmatch(r"[A-Z]-\d{2}/\d", sector.strip().upper()))

# Remove duplicates (based on all 5 fields)
def deduplicate_data(df):
    df["Plot Size"] = df["Plot Size"].apply(normalize_plot_size)
    df = df[df["Sector"].apply(is_valid_sector)]
    df = df.dropna(subset=["Sector", "Plot No#", "Plot Size", "Demand/Price"])

    # For I-15 subsectors, Street# must not be missing
    df = df[~(
        df["Sector"].astype(str).str.upper().isin(["I-15/1", "I-15/2", "I-15/3", "I-15/4"]) & 
        (df["Street#"].astype(str).str.strip() == "")
    )]

    # Remove duplicates
    df = df.drop_duplicates(subset=["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"])
    return df

# Filter for WhatsApp only (exclude listings with missing required fields)
def filter_whatsapp_ready(df):
    df = df.copy()
    required = ["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"]
    def is_valid(row):
        sector = row["Sector"]
        if not is_valid_sector(sector): return False
        if sector.upper() in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] and not row["Street#"]:
            return False
        return all(pd.notna(row[col]) and str(row[col]).strip() != "" for col in required)
    return df[df.apply(is_valid, axis=1)]

# Generate WhatsApp message
def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_size = normalize_plot_size(row.get("Plot Size", ""))
        plot_no = str(row.get("Plot No#", "")).strip()
        price = str(row.get("Demand/Price", "")).strip()
        street = str(row.get("Street#", "")).strip()

        key = f"{sector}__{plot_size}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((plot_no, plot_size, price, street, sector))

    msg = ""
    for group_key in sorted(grouped.keys()):
        sector, size = group_key.split("__")
        listings = grouped[group_key]
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, sec in listings:
            if sector.upper() in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

# Sidebar contact list
def load_contacts():
    try:
        return pd.read_csv(CONTACTS_FILE)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def save_contact(name, c1, c2, c3):
    contacts = load_contacts()
    new_entry = pd.DataFrame([{"Name": name, "Contact1": c1, "Contact2": c2, "Contact3": c3}])
    contacts = pd.concat([contacts, new_entry], ignore_index=True)
    contacts.to_csv(CONTACTS_FILE, index=False)

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load full data
    df_raw = load_data_from_gsheet()
    df_raw = df_raw.fillna("")
    df = deduplicate_data(df_raw.copy())

    # Sidebar
    st.sidebar.subheader("🔍 Filters")
    sector_filter = st.sidebar.text_input("Sector (e.g. I-14 or I-14/1)")
    plot_size_filter = st.sidebar.text_input("Plot Size (e.g. 25x50)")
    street_filter = st.sidebar.text_input("Street#")
    plot_no_filter = st.sidebar.text_input("Plot No#")
    contact_text_filter = st.sidebar.text_input("Contact Number")

    # Date filter
    date_options = ["All", "Last 7 days", "Last 15 days", "Last 1 month", "Last 2 months"]
    selected_date = st.sidebar.selectbox("Filter by Date", date_options)

    if selected_date != "All":
        days = {
            "Last 7 days": 7,
            "Last 15 days": 15,
            "Last 1 month": 30,
            "Last 2 months": 60
        }.get(selected_date, 0)

        cutoff = datetime.now() - timedelta(days=days)

        def parse_date(val):
            try:
                return datetime.strptime(val.strip(), "%Y-%m-%d , %H:%M")
            except:
                try:
                    return datetime.strptime(val.strip(), "%Y-%m-%d")
                except:
                    return None

        df["parsed_date"] = df["Date"].apply(parse_date)
        df = df[df["parsed_date"].notna() & (df["parsed_date"] >= cutoff)]

    # Contact dropdown filter
    contacts = load_contacts()
    selected_name = st.sidebar.selectbox("📇 Select Saved Contact", [""] + contacts["Name"].tolist())
    df_filtered = df.copy()

    if selected_name:
        contact_row = contacts[contacts["Name"] == selected_name]
        nums = [str(contact_row.iloc[0][col]) for col in ["Contact1", "Contact2", "Contact3"]
                if pd.notna(contact_row.iloc[0][col]) and str(contact_row.iloc[0][col]).strip()]
        if nums:
            pattern = "|".join(map(re.escape, nums))
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(pattern, case=False, na=False)]

    # Apply other filters
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].astype(str).str.contains(sector_filter, case=False, na=False)]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].astype(str).str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].astype(str).str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]
    if contact_text_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_text_filter, case=False, na=False)]

    # Display filtered listings
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # WhatsApp message generation
    st.subheader("📤 Generate WhatsApp Message")
    number_input = st.text_input("Enter WhatsApp Number (03xxxxxxxxx):")
    if st.button("Generate Message"):
        df_msg = filter_whatsapp_ready(df_filtered)
        if df_msg.empty:
            st.warning("No valid listings to include.")
        else:
            msg = generate_whatsapp_message(df_msg)
            st.text_area("Generated Message", msg, height=300)
            if number_input.startswith("03") and len(number_input) == 11:
                wa_number = "92" + number_input[1:]
                wa_url = f"https://wa.me/{wa_number}?text={re.sub(r' ', '%20', msg)}"
                st.markdown(f"[📲 Click to Send WhatsApp Message]({wa_url})", unsafe_allow_html=True)
            else:
                st.warning("Please enter a valid number starting with 03...")

    # Add contact
    st.subheader("➕ Add New Contact")
    new_name = st.text_input("Contact Name")
    new_c1 = st.text_input("Contact 1")
    new_c2 = st.text_input("Contact 2 (optional)")
    new_c3 = st.text_input("Contact 3 (optional)")
    if st.button("Save Contact"):
        if new_name and new_c1:
            save_contact(new_name, new_c1, new_c2, new_c3)
            st.success("Contact saved. Refresh app to see in list.")
        else:
            st.error("Name and Contact 1 are required.")

if __name__ == "__main__":
    main()