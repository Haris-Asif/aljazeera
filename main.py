import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "RealEstateTool"
PROPERTIES_SHEET = "Sheet1"
CONTACTS_SHEET = "Contacts"
REQUIRED_COLUMNS = ["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"]

# Load data from Google Sheet
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    sheet = client.open(SPREADSHEET_NAME).worksheet(PROPERTIES_SHEET)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Load contacts from Contacts sheet in Google Sheets
def load_contacts_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    contacts_sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    contacts = contacts_sheet.get_all_records()
    return pd.DataFrame(contacts)

# Clean phone numbers (remove non-digit characters)
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

# Sector filter logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# Filter by date
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

# WhatsApp message generation
def generate_whatsapp_messages(df):
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

    # Group by (Sector, Plot Size)
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    # Split message groups if WhatsApp character limit is exceeded
    chunks = []
    current_msg = ""
    for (sector, size), listings in sorted(grouped.items()):
        header = f"*Available Options in {sector} Size: {size}*\n"
        body = ""
        for l in listings:
            if sector.startswith("I-15/"):
                body += f"St: {l['Street#']} | P: {l['Plot No#']} | S: {l['Plot Size']} | D: {l['Demand/Price']}\n"
            else:
                body += f"P: {l['Plot No#']} | S: {l['Plot Size']} | D: {l['Demand/Price']}\n"
        group_text = header + body + "\n"
        if len(current_msg) + len(group_text) >= 3900:  # keep margin for encoding
            chunks.append(current_msg.strip())
            current_msg = ""
        current_msg += group_text
    if current_msg:
        chunks.append(current_msg.strip())

    return chunks

# Main app
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    contacts_df = load_contacts_from_gsheet()
    df = df.fillna("")

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        selected_name = st.selectbox("📇 Saved Contacts (Filter Listings)", [""] + list(contacts_df["Name"].dropna().unique()))

    df_filtered = df.copy()

    # Filter by selected contact numbers
    if selected_name:
        contact_row = contacts_df[contacts_df["Name"] == selected_name]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in contact_row.columns:
                val = contact_row[col].values[0]
                if pd.notna(val) and str(val).strip():
                    nums.append(clean_number(val))
        if nums:
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: any(n in clean_number(x) for n in nums))]

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

    df_filtered = filter_by_date(df_filtered, date_filter)

    # Show filtered data
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    # WhatsApp messaging
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    col1, col2 = st.columns([3, 2])
    with col1:
        number = st.text_input("Enter WhatsApp Number (e.g. 03xxxxxxxxx)")
    with col2:
        wa_contact = st.selectbox("Or select saved contact", [""] + list(contacts_df["Name"].dropna().unique()))

    final_number = ""
    if number and number.strip().startswith("03"):
        final_number = number.strip()
    elif wa_contact:
        row = contacts_df[contacts_df["Name"] == wa_contact]
        if not row.empty:
            raw_number = row["Contact1"].values[0]
            final_number = "03" + str(raw_number) if raw_number.startswith("3") else str(raw_number)

    if st.button("Generate WhatsApp Message"):
        if not final_number:
            st.error("❌ Please enter a valid number or select a saved contact.")
        else:
            chunks = generate_whatsapp_messages(df_filtered)
            if not chunks:
                st.warning("⚠️ No valid listings to include in WhatsApp message.")
            else:
                wa_number = "92" + clean_number(final_number).lstrip("0")
                for i, msg in enumerate(chunks):
                    encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                    link = f"https://wa.me/{wa_number}?text={encoded}"
                    st.markdown(f"[📩 Send Message Part {i+1}]({link})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()