import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "RealEstateTool"
WORKSHEET_NAME = "Sheet1"
CONTACTS_CSV = "contacts.csv"
REQUIRED_COLUMNS = ["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"]

# Load data from Google Sheet
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Sector filter logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# Clean phone numbers for matching (remove dashes etc)
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

# WhatsApp message formatter
def generate_whatsapp_message(df):
    filtered = []

    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No#", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand/Price", "")).strip()
        street = str(row.get("Street#", "")).strip()

        if not re.match(r"^[A-Z]-\d+/\d+$", sector):
            continue
        if not (sector and plot_no and plot_size and demand):
            continue
        if sector in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] and not street:
            continue

        filtered.append({
            "Sector": sector,
            "Street#": street,
            "Plot No#": plot_no,
            "Plot Size": plot_size,
            "Demand/Price": demand
        })

    # Remove duplicates
    seen = set()
    unique = []
    for row in filtered:
        key = (
            row["Sector"],
            row["Plot No#"],
            row["Plot Size"],
            row["Demand/Price"],
            row["Street#"] if row["Sector"] in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] else ""
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)

    # Group by (Sector, Plot Size) and sort by Plot No#
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    msg = ""
    for (sector, size), items in sorted(grouped.items()):
        # Sort by numeric part of Plot No# if possible
        def extract_plot_number(val):
            try:
                return int(re.search(r"\d+", str(val)).group())
            except:
                return float('inf')
        sorted_items = sorted(items, key=lambda x: extract_plot_number(x["Plot No#"]))

        msg += f"*Available Options in {sector} Size: {size}*\n"
        for row in sorted_items:
            if "I-15/" in sector:
                msg += f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                msg += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        msg += "\n"

    return msg.strip()

# Apply date range filter
def filter_by_date(df, days_label):
    if days_label == "All":
        return df
    today = datetime.today()
    days_map = {
        "Last 7 Days": 7,
        "Last 15 Days": 15,
        "Last 30 Days": 30,
        "Last 2 Months": 60
    }
    days = days_map.get(days_label, 0)
    if days == 0:
        return df

    cutoff = today - timedelta(days=days)

    def parse_date(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d, %H:%M")
        except:
            try:
                return datetime.strptime(val.strip(), "%Y-%m-%d")
            except:
                return None

    df["ParsedDate"] = df["Date"].apply(parse_date)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

# Load contacts
def load_contacts():
    try:
        return pd.read_csv(CONTACTS_CSV)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

# Main App
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    df = df.fillna("")

    contacts_df = load_contacts()

    # Sidebar Filters
    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        # Dealer Name Autocomplete (if column exists)
        dealer_filter = ""
        if "Dealer Name" in df.columns:
            dealer_names = sorted(df["Dealer Name"].dropna().unique())
            dealer_filter = st.selectbox("Dealer Name", [""] + dealer_names)

        st.markdown("---")
        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_name = st.selectbox("📇 Saved Contacts", contact_names)

    df_filtered = df.copy()

    # Saved contact filter
    if selected_name:
        contact_row = contacts_df[contacts_df["Name"] == selected_name]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in contact_row.columns:
                val = contact_row[col].values[0]
                if pd.notna(val) and str(val).strip():
                    nums.append(clean_number(val))

        if nums:
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(
                lambda x: any(n in clean_number(x) for n in nums)
            )]

    # Other filters
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    if contact_filter:
        contact_clean = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: contact_clean in clean_number(x))]

    if dealer_filter and "Dealer Name" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["Dealer Name"].astype(str).str.contains(dealer_filter, case=False, na=False)]

    df_filtered = filter_by_date(df_filtered, date_filter)

    # Display Filtered Listings
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    number = st.text_input("Enter WhatsApp Number (e.g. 03xxxxxxxxx)")
    if st.button("Generate WhatsApp Message"):
        if not number or not number.strip().startswith("03"):
            st.error("❌ Please enter a valid number starting with 03...")
        else:
            msg = generate_whatsapp_message(df_filtered)
            if not msg:
                st.warning("⚠️ No valid listings to include in WhatsApp message.")
            else:
                wa_number = "92" + clean_number(number).lstrip("0")
                link = f"https://wa.me/{wa_number}?text={msg.replace(' ', '%20').replace('\n', '%0A')}"
                st.success("✅ Message Ready!")
                st.markdown(f"[📩 Send Message on WhatsApp]({link})", unsafe_allow_html=True)

    # Add Contact Form
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1*", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1:
                new_row = pd.DataFrame([[name, c1, c2, c3]], columns=["Name", "Contact1", "Contact2", "Contact3"])
                updated_df = pd.concat([contacts_df, new_row], ignore_index=True)
                updated_df.to_csv(CONTACTS_CSV, index=False)
                st.success(f"Contact '{name}' saved.")
            else:
                st.warning("Name and Contact1 are required.")

if __name__ == "__main__":
    main()