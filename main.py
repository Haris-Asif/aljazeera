import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "RealEstateTool"
LISTINGS_SHEET = "Sheet1"
CONTACTS_SHEET = "Contacts"

# Load data from Google Sheet
def load_data_from_gsheet(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(sheet_name)
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

# Clean phone numbers for matching
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

# Filter listings to generate WhatsApp message
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

    # Group and format
    msg = ""
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    for (sector, size), items in sorted(grouped.items()):
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for row in items:
            if sector.startswith("I-15/"):
                msg += f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                msg += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        msg += "\n"

    return msg.strip()

# Filter by date range
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

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet(LISTINGS_SHEET).fillna("")
    contacts_df = load_data_from_gsheet(CONTACTS_SHEET).fillna("")

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        st.markdown("---")
        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_name = st.selectbox("📇 Saved Contacts", contact_names)

    df_filtered = df.copy()

    # Filter by saved contact
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

    # WhatsApp Message Section
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    col1, col2 = st.columns([3, 2])
    with col1:
        number_input = st.text_input("Enter WhatsApp Number (e.g. 03xxxxxxxxx)")
    with col2:
        contact_pick = st.selectbox("Or select saved contact", [""] + list(contacts_df["Name"].dropna().unique()))

    final_number = ""

    if number_input and number_input.strip().startswith("03") and len(clean_number(number_input)) == 11:
        final_number = clean_number(number_input)
    elif contact_pick:
        contact_row = contacts_df[contacts_df["Name"] == contact_pick]
        if not contact_row.empty:
            contact1 = str(contact_row.iloc[0]["Contact1"]).strip()
            if contact1.startswith("03") and len(contact1) == 11 and contact1.isdigit():
                final_number = contact1
            else:
                st.warning("⚠️ Contact1 must be a valid 11-digit number starting with 03.")

    if st.button("Generate WhatsApp Message"):
        if not final_number:
            st.error("❌ Please provide a valid number or contact.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            if not msg:
                st.warning("⚠️ No valid listings to include in WhatsApp message.")
            else:
                wa_link = f"https://wa.me/92{final_number[1:]}?text={msg.replace(' ', '%20').replace('\n', '%0A')}"
                st.success("✅ Message Ready!")
                st.markdown(f"[📩 Send Message on WhatsApp]({wa_link})", unsafe_allow_html=True)

    # Contact save form
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1 (03xxxxxxxxx)*", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1 and c1.startswith("03") and len(clean_number(c1)) == 11:
                new_row = [name, c1, c2, c3]
                try:
                    gc = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]))
                    sh = gc.open(SPREADSHEET_NAME)
                    ws = sh.worksheet(CONTACTS_SHEET)
                    ws.append_row(new_row)
                    st.success(f"Contact '{name}' saved to Google Sheet.")
                except Exception as e:
                    st.error(f"❌ Failed to save contact: {e}")
            else:
                st.warning("⚠️ Name and valid Contact1 (03xxxxxxxxx) are required.")

if __name__ == "__main__":
    main()