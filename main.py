import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_SHEET = "Contacts"

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Load Google Sheet data (Plots)
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

    all_data = sheet.get_all_values()
    headers = all_data[0]
    data_rows = all_data[1:]

    for row in data_rows:
        while len(row) < len(headers):
            row.append("")
        if len(row) > len(headers):
            row[:] = row[:len(headers)]

    df = pd.DataFrame(data_rows, columns=headers)
    df["SheetRowNum"] = [i + 2 for i in range(len(df))]
    return df

# Load Contacts from separate sheet
def load_contacts():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)

    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Utility
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    return f in c if "/" not in f else f == c

def extract_plot_number(val):
    try:
        return int(re.search(r"\d+", str(val)).group())
    except:
        return float("inf")

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

    message_chunks = []
    current_msg = ""

    for (sector, size), items in sorted(grouped.items()):
        sorted_items = sorted(items, key=lambda x: extract_plot_number(x["Plot No#"]))
        header = f"*Available Options in {sector} Size: {size}*\n"
        lines = []
        for row in sorted_items:
            if "I-15/" in sector:
                line = f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}"
            else:
                line = f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}"
            lines.append(line)

        block = header + "\n".join(lines) + "\n\n"
        if len(current_msg + block) > 3900:
            message_chunks.append(current_msg.strip())
            current_msg = block
        else:
            current_msg += block

    if current_msg:
        message_chunks.append(current_msg.strip())

    return message_chunks

def filter_by_date(df, label):
    if label == "All":
        return df
    today = datetime.today()
    days_map = {
        "Last 7 Days": 7,
        "Last 15 Days": 15,
        "Last 30 Days": 30,
        "Last 2 Months": 60
    }
    days = days_map.get(label, 0)
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

# --- Main App ---
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet().fillna("")
    contacts_df = load_contacts()

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        dealer_filter = ""
        dealer_names = sorted(df["Dealer name"].dropna().unique()) if "Dealer name" in df.columns else []
        if dealer_names:
            dealer_filter = st.selectbox("Dealer name", [""] + dealer_names)

        st.markdown("---")
        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_name = st.selectbox("📇 Filter Listings by Saved Contact", contact_names)

    df_filtered = df.copy()

    # Filter by selected contact
    if selected_name:
        contact_row = contacts_df[contacts_df["Name"] == selected_name]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            val = contact_row[col].values[0] if col in contact_row.columns else ""
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
        cnum = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: cnum in clean_number(x))]
    if dealer_filter and "Dealer name" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["Dealer name"].astype(str).str.contains(dealer_filter, case=False, na=False)]

    df_filtered = filter_by_date(df_filtered, date_filter)

    # Show Listings
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    wa_contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
    wa_selected_name = st.selectbox("Select a Contact Name", wa_contact_names, key="wa_contact_name")

    wa_contact_numbers = []
    if wa_selected_name:
        wa_row = contacts_df[contacts_df["Name"] == wa_selected_name]
        for col in ["Contact1", "Contact2", "Contact3"]:
            val = wa_row[col].values[0] if col in wa_row.columns else ""
            if pd.notna(val) and str(val).strip():
                wa_contact_numbers.append(clean_number(val))

    wa_selected_number = st.selectbox("Select Number from Contact", wa_contact_numbers if wa_contact_numbers else [""])
    manual_number = st.text_input("Or Enter WhatsApp Number Manually (e.g. 03001234567)", key="manual_input")

    if st.button("Generate WhatsApp Message"):
        raw_number = manual_number.strip() if manual_number.strip() else wa_selected_number
        final_number = clean_number(raw_number)

        if len(final_number) == 11 and final_number.startswith("03"):
            wa_number = "92" + final_number[1:]
            chunks = generate_whatsapp_messages(df_filtered)
            if not chunks:
                st.warning("⚠️ No valid listings.")
            else:
                for i, msg in enumerate(chunks):
                    encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                    link = f"https://wa.me/{wa_number}?text={encoded}"
                    st.markdown(f"[📩 Send Message {i+1}]({link})", unsafe_allow_html=True)
        else:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")

if __name__ == "__main__":
    main()