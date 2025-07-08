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

# Clean phone numbers for matching (remove dashes etc)
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

# Debug function to investigate saved contact issues
def debug_contact_number(row):
    if row.empty:
        return "❌ No contact row found."
    raw_number = str(row["Contact1"].values[0]).strip()
    debug_msg = f"Retrieved number: '{raw_number}'\n"
    if not raw_number:
        debug_msg += "⚠️ Number is empty.\n"
    elif not re.fullmatch(r"03\d{9}", raw_number):
        debug_msg += "❌ Number is not in valid 03xxxxxxxxx format.\n"
    else:
        debug_msg += "✅ Number is valid.\n"
    return debug_msg

# Format WhatsApp message
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

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet(LISTINGS_SHEET)
    df = df.fillna("")
    contacts_df = load_data_from_gsheet(CONTACTS_SHEET)

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

    # Saved contact filter (for filtering listings)
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
        debug = debug_contact_number(row)
        st.code(debug, language="text")

        if not row.empty:
            raw_number = str(row["Contact1"].values[0]).strip()
            if re.fullmatch(r"03\d{9}", raw_number):
                final_number = raw_number

    if st.button("Generate WhatsApp Message"):
        if not final_number:
            st.error("❌ Please provide a valid number or contact.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            if not msg:
                st.warning("⚠️ No valid listings to include in WhatsApp message.")
            else:
                wa_number = "92" + final_number[1:]  # Remove leading 0 and add 92
                link = f"https://wa.me/{wa_number}?text={msg.replace(' ', '%20').replace('\n', '%0A')}"
                st.success("✅ Message Ready!")
                st.markdown(f"[📩 Send Message on WhatsApp]({link})", unsafe_allow_html=True)

    # Contact form
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1* (e.g. 03xxxxxxxxx)", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and re.fullmatch(r"03\d{9}", c1.strip()):
                new_row = pd.DataFrame([[name, c1.strip(), c2.strip(), c3.strip()]], columns=["Name", "Contact1", "Contact2", "Contact3"])
                existing = load_data_from_gsheet(CONTACTS_SHEET)
                updated_df = pd.concat([existing, new_row], ignore_index=True)

                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds_dict = st.secrets["gcp_service_account"]
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                client = gspread.authorize(creds)
                sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
                sheet.clear()
                sheet.update([updated_df.columns.values.tolist()] + updated_df.values.tolist())
                st.success(f"Contact '{name}' saved successfully.")
            else:
                st.warning("⚠️ Name and valid Contact1 (starting with 03) are required.")

if __name__ == "__main__":
    main()