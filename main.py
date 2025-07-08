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

# Load data from Google Sheets
def load_data_from_gsheet(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(sheet_name)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Clean phone number
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

# Generate WhatsApp Message
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

    if not unique:
        return []

    # Group and generate messages
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    all_msgs = []
    current_msg = ""
    char_limit = 3900  # 4096 safe buffer
    for (sector, size), items in sorted(grouped.items()):
        group_header = f"*Available Options in {sector} Size: {size}*\n"
        lines = ""
        for row in items:
            if sector.startswith("I-15/"):
                lines += f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                lines += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        group_block = group_header + lines + "\n"
        if len(current_msg) + len(group_block) > char_limit:
            all_msgs.append(current_msg.strip())
            current_msg = group_block
        else:
            current_msg += group_block
    if current_msg.strip():
        all_msgs.append(current_msg.strip())
    return all_msgs

# Main App
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
        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_contact = st.selectbox("📇 Saved Contacts (for filtering)", contact_names)

    df_filtered = df.copy()

    if selected_contact:
        row = contacts_df[contacts_df["Name"] == selected_contact]
        numbers = [str(row[col].values[0]) for col in ["Contact1", "Contact2", "Contact3"] if col in row and str(row[col].values[0]).strip()]
        nums_clean = [clean_number(n) for n in numbers]
        if nums_clean:
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: any(n in clean_number(x) for n in nums_clean))]

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

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    col1, col2 = st.columns([3, 2])
    with col1:
        number_input = st.text_input("Enter WhatsApp Number (e.g. 03xxxxxxxxx)")
    with col2:
        send_contact = st.selectbox("Or select saved contact to send", [""] + list(contacts_df["Name"].dropna().unique()))

    final_number = ""
    if number_input and number_input.strip().startswith("03"):
        final_number = number_input.strip()
    elif send_contact:
        row = contacts_df[contacts_df["Name"] == send_contact]
        if not row.empty:
            raw = str(row["Contact1"].values[0]).strip()
            final_number = raw  # Already in 03xxxxxxxxx format

    if st.button("Generate WhatsApp Message"):
        if not final_number or not final_number.startswith("03"):
            st.error("❌ Please enter or select a valid number starting with 03...")
        else:
            messages = generate_whatsapp_messages(df_filtered)
            if not messages:
                st.warning("⚠️ No valid listings to include in WhatsApp message.")
            else:
                st.success("✅ WhatsApp Message(s) Ready:")
                for idx, msg in enumerate(messages, 1):
                    wa_number = "92" + final_number[1:]  # convert 03xxxxxxxxx → 92xxxxxxxxxx
                    msg_encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                    link = f"https://wa.me/{wa_number}?text={msg_encoded}"
                    st.markdown(f"[📩 Send Message {idx} on WhatsApp]({link})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()