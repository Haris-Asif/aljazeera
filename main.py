import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Constants
SPREADSHEET_NAME = "RealEstateTool"
LISTINGS_SHEET = "Sheet1"
CONTACTS_SHEET = "Contacts"

# Set page
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Google Sheets connection
def connect_to_sheet(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(sheet_name)
    return pd.DataFrame(sheet.get_all_records())

# Save contact to Google Sheet
def save_contact_to_gsheet(name, c1, c2, c3):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    sheet.append_row([name, c1, c2, c3])

# Cleaning helper
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

# Sector filtering logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# Date filter
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

# WhatsApp message generator
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

    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    msg_parts = []
    current_msg = ""
    for (sector, size), items in sorted(grouped.items()):
        section = f"*Available Options in {sector} Size: {size}*\n"
        for row in items:
            if sector.startswith("I-15/"):
                section += f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                section += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        section += "\n"

        if len(current_msg + section) > 3900:
            msg_parts.append(current_msg.strip())
            current_msg = section
        else:
            current_msg += section
    if current_msg:
        msg_parts.append(current_msg.strip())

    return msg_parts

# Main app
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = connect_to_sheet(LISTINGS_SHEET).fillna("")
    contacts_df = connect_to_sheet(CONTACTS_SHEET).fillna("")

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        selected_name = st.selectbox("📇 Filter by Saved Contact", [""] + sorted(contacts_df["Name"].dropna().unique()))

    df_filtered = df.copy()

    # Contact filter for listing table
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

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        clean_c = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: clean_c in clean_number(x))]

    df_filtered = filter_by_date(df_filtered, date_filter)

    # Show listings
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    col1, col2 = st.columns([3, 2])
    with col1:
        number_input = st.text_input("Enter WhatsApp Number (03xxxxxxxxx)")
    with col2:
        contact_pick = st.selectbox("Or select saved contact to send", [""] + sorted(contacts_df["Name"].dropna().unique()))

    final_number = ""
    if number_input.strip().startswith("03"):
        final_number = clean_number(number_input.strip())
    elif contact_pick:
        row = contacts_df[contacts_df["Name"] == contact_pick]
        if not row.empty:
            raw = str(row["Contact1"].values[0]).strip()
            if raw.startswith("03") and len(raw) == 11:
                final_number = clean_number(raw)
            else:
                st.warning("Saved contact number must be in 03xxxxxxxxx format.")

    if st.button("Generate WhatsApp Message"):
        if not final_number:
            st.error("❌ Enter a valid number or select a valid contact.")
        else:
            messages = generate_whatsapp_message(df_filtered)
            if not messages:
                st.warning("⚠️ No valid listings to include.")
            else:
                st.success("✅ WhatsApp message(s) ready!")
                for i, msg in enumerate(messages):
                    wa_link = f"https://wa.me/92{final_number.lstrip('0')}?text={msg.replace(' ', '%20').replace('\n', '%0A')}"
                    st.markdown(f"[📩 Message {i+1}]({wa_link})", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact_form"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1*", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1 and c1.strip().startswith("03"):
                save_contact_to_gsheet(name, c1.strip(), c2.strip(), c3.strip())
                st.success(f"Contact '{name}' saved to Google Sheet.")
            else:
                st.warning("Name and Contact1 (03xxxxxxxxx) are required.")

if __name__ == "__main__":
    main()