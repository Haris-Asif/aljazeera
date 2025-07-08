import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Streamlit UI setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Constants
SPREADSHEET_NAME = "RealEstateTool"
LISTINGS_SHEET = "Sheet1"
CONTACTS_SHEET = "Contacts"
REQUIRED_COLS = ["Sector", "Plot Size", "Plot No#", "Demand/Price"]
I15_SECTORS = ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]

# Utilities
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

def is_valid_number(num):
    return re.match(r"^03\d{9}$", num)

def load_data(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(sheet_name)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

def filter_by_date(df, days_label):
    if days_label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.today() - timedelta(days=days_map.get(days_label, 0))

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
        if not all([sector, plot_no, plot_size, demand]):
            continue
        if sector in I15_SECTORS and not street:
            continue

        filtered.append({
            "Sector": sector,
            "Plot No#": plot_no,
            "Plot Size": plot_size,
            "Demand/Price": demand,
            "Street#": street
        })

    seen = set()
    unique = []
    for row in filtered:
        key = (
            row["Sector"],
            row["Plot No#"],
            row["Plot Size"],
            row["Demand/Price"],
            row["Street#"] if row["Sector"] in I15_SECTORS else ""
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)

    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    messages = []
    current_msg = ""
    for (sector, size), items in sorted(grouped.items()):
        block = f"*Available Options in {sector} Size: {size}*\n"
        for r in items:
            if sector.startswith("I-15/"):
                block += f"St: {r['Street#']} | P: {r['Plot No#']} | S: {r['Plot Size']} | D: {r['Demand/Price']}\n"
            else:
                block += f"P: {r['Plot No#']} | S: {r['Plot Size']} | D: {r['Demand/Price']}\n"
        block += "\n"
        if len(current_msg + block) > 3900:
            messages.append(current_msg.strip())
            current_msg = block
        else:
            current_msg += block
    if current_msg:
        messages.append(current_msg.strip())

    return messages

# Main app
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data(LISTINGS_SHEET).fillna("")
    contacts_df = load_data(CONTACTS_SHEET).fillna("")

    # Sidebar filters
    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14 or I-14/1)")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        selected_contact_name = st.selectbox("📇 Filter by Saved Contact", [""] + contacts_df["Name"].dropna().unique().tolist())

    df_filtered = df.copy()

    # Apply saved contact filter
    if selected_contact_name:
        contact_row = contacts_df[contacts_df["Name"] == selected_contact_name]
        if not contact_row.empty:
            nums = [clean_number(contact_row.iloc[0][col]) for col in ["Contact1", "Contact2", "Contact3"] if pd.notna(contact_row.iloc[0][col])]
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: any(n in clean_number(x) for n in nums))]

    # Apply manual filters
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

    # Show data
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    col1, col2 = st.columns([2, 2])
    with col1:
        manual_number = st.text_input("Enter WhatsApp Number (03xxxxxxxxx)")
    with col2:
        wa_contact_name = st.selectbox("Or Select a Contact", [""] + contacts_df["Name"].dropna().tolist())

    final_number = ""
    if manual_number and is_valid_number(manual_number):
        final_number = manual_number
    elif wa_contact_name:
        contact_row = contacts_df[contacts_df["Name"] == wa_contact_name]
        if not contact_row.empty:
            candidate = str(contact_row.iloc[0]["Contact1"]).strip()
            if is_valid_number(candidate):
                final_number = candidate
            else:
                st.error(f"❌ Saved number is invalid: {candidate}")
        else:
            st.warning("⚠️ Selected contact not found.")
    else:
        st.info("ℹ️ Please enter or select a valid WhatsApp number.")

    if st.button("Generate WhatsApp Message") and final_number:
        msgs = generate_whatsapp_messages(df_filtered)
        if not msgs:
            st.warning("⚠️ No valid listings to include in message.")
        else:
            st.success("✅ Message(s) ready!")
            for idx, m in enumerate(msgs):
                link = f"https://wa.me/92{final_number[1:]}?text={m.replace(' ', '%20').replace('\n', '%0A')}"
                st.markdown(f"[📩 Send Message {idx+1}]({link})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()