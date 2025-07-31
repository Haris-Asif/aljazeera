import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Constants
SPREADSHEET_NAME = "Al-Jazeera"
PLOTS_SHEET = "Plots"
CONTACTS_SHEET = "Contacts"

USERNAME = "aljazeera"
PASSWORD = "H@ri$_980"

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Authentication
def login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        with st.form("login_form"):
            st.subheader("🔐 Login Required")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                if username == USERNAME and password == PASSWORD:
                    st.session_state.logged_in = True
                    st.experimental_rerun()
                else:
                    st.error("❌ Invalid credentials")
        return False
    return True

# Google Sheets Auth
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# Load plot data
def load_plot_data():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
    df = pd.DataFrame(sheet.get_all_records())
    df["SheetRowNum"] = [i + 2 for i in range(len(df))]
    return df.fillna("")

# Load contacts
def load_contacts():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    return pd.DataFrame(sheet.get_all_records()).fillna("")

def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text):
    parts = re.split(r"[,\s]+", str(text or ""))
    return [clean_number(p) for p in parts if clean_number(p).startswith("03") or clean_number(p).startswith("923")]

def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    days = days_map.get(label, 0)
    cutoff = datetime.now() - timedelta(days=days)

    def try_parse(val):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d, %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(val.strip(), fmt)
            except:
                continue
        return None

    df["ParsedDate"] = df["Timestamp"].apply(try_parse)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

def get_dealer_name_mapping(df):
    name_map = {}
    contact_to_name = {}

    for _, row in df.iterrows():
        name = row.get("Extracted Name", "").strip()
        contacts = extract_numbers(row.get("Extracted Contact", ""))
        for num in contacts:
            if num not in contact_to_name:
                contact_to_name[num] = name

    unique_name_map = {}
    for num, name in contact_to_name.items():
        if name not in unique_name_map.values():
            unique_name_map[num] = name

    return unique_name_map

def generate_whatsapp_messages(df):
    filtered = []
    for _, row in df.iterrows():
        plot_no = str(row.get("Plot No", "")).strip()
        if "series" in plot_no.lower():
            continue

        sector = str(row.get("Sector", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand", "")).strip()

        filtered.append({
            "Sector": sector,
            "Plot No": plot_no,
            "Plot Size": plot_size,
            "Demand": demand
        })

    # Sort by Plot No numeric part
    def plot_sort(val):
        m = re.search(r"\d+", val.get("Plot No", ""))
        return int(m.group()) if m else 9999999

    filtered = sorted(filtered, key=plot_sort)

    grouped = {}
    for row in filtered:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    chunks = []
    current_msg = ""

    for (sector, size), items in grouped.items():
        header = f"*Available Options in {sector} Size: {size}*\n"
        lines = [f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}" for r in items]
        block = header + "\n".join(lines) + "\n\n"

        if len(current_msg + block) > 3900:
            chunks.append(current_msg.strip())
            current_msg = block
        else:
            current_msg += block

    if current_msg:
        chunks.append(current_msg.strip())

    return chunks

def main():
    if not login():
        return

    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_plot_data()
    contacts_df = load_contacts()

    name_map = get_dealer_name_mapping(df)
    dealer_names = sorted(set(name_map.values()))

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        plot_no_filter = st.text_input("Plot No")
        contact_filter = st.text_input("Phone Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        dealer_filter = st.selectbox("Dealer Name", [""] + dealer_names)

        saved_contact = st.selectbox("📇 Saved Contact", [""] + sorted(contacts_df["Name"].dropna().unique()))

    df_filtered = df.copy()

    # Dealer filter (via contact match)
    if dealer_filter:
        matched_numbers = [num for num, name in name_map.items() if name == dealer_filter]
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda val: any(num in clean_number(val) for num in matched_numbers)
        )]

    # Saved Contact filter
    if saved_contact:
        row = contacts_df[contacts_df["Name"] == saved_contact]
        numbers = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            numbers.extend(extract_numbers(row[col].values[0]) if col in row.columns else [])
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda val: any(num in clean_number(val) for num in numbers)
        )]

    # Additional filters
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].str.contains(sector_filter, case=False, na=False)]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No"].str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        clean = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(lambda val: clean in clean_number(val))]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    wa_contact = st.selectbox("📱 Select Contact to Message", [""] + sorted(contacts_df["Name"].dropna().unique()), key="wa_contact")
    manual_number = st.text_input("Or Enter WhatsApp Number (e.g. 0300xxxxxxx)")

    if st.button("Generate WhatsApp Message"):
        number = ""
        if manual_number:
            number = clean_number(manual_number)
        elif wa_contact:
            row = contacts_df[contacts_df["Name"] == wa_contact]
            for col in ["Contact1", "Contact2", "Contact3"]:
                if col in row.columns and pd.notna(row[col].values[0]):
                    number = clean_number(row[col].values[0])
                    if number:
                        break

        if not number:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
            return

        if number.startswith("03") and len(number) == 11:
            wa_number = "92" + number[1:]
        elif number.startswith("3") and len(number) == 10:
            wa_number = "92" + number
        elif number.startswith("92") and len(number) == 12:
            wa_number = number
        else:
            st.error("❌ Invalid number format.")
            return

        chunks = generate_whatsapp_messages(df_filtered)
        if not chunks:
            st.warning("⚠️ No valid listings to include.")
        else:
            for i, msg in enumerate(chunks):
                encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                link = f"https://wa.me/{wa_number}?text={encoded}"
                st.markdown(f"[📩 Send Message {i+1}]({link})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()