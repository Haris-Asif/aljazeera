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

# Clean number
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text):
    return [clean_number(part) for part in re.split(r"[,\s\-]+", str(text)) if clean_number(part)]

# Google Sheets client
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# Load plot data
def load_plot_data():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    df["SheetRowNum"] = [i + 2 for i in range(len(df))]  # Account for header
    return df

# Load contacts
def load_contacts():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Login
def login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.get("authenticated"):
        return True

    if "login_attempt" not in st.session_state:
        st.session_state.login_attempt = False

    with st.form("Login"):
        st.subheader("🔐 Login Required")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if username == USERNAME and password == PASSWORD:
                st.session_state.authenticated = True
                st.session_state.login_attempt = True
            else:
                st.error("Invalid credentials")

    if st.session_state.get("login_attempt"):
        st.session_state.login_attempt = False
        st.experimental_rerun()

    return False

# Filter by recent date
def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    days = days_map.get(label, 0)
    cutoff = datetime.now() - timedelta(days=days)

    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            return None

    df["ParsedDate"] = df["Timestamp"].apply(try_parse)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

# Group similar names based on contact
def get_contact_name_map(df):
    contact_to_name = {}
    name_order = {}

    for idx, row in df.iterrows():
        name = str(row.get("Extracted Name", "")).strip()
        contact_field = row.get("Extracted Contact", "")
        numbers = extract_numbers(contact_field)

        for num in numbers:
            if num not in contact_to_name:
                contact_to_name[num] = name
                name_order[name] = idx  # preserve order

    grouped = {}
    for num, name in contact_to_name.items():
        grouped.setdefault(name, set()).add(num)

    final_map = {}
    for name, nums in grouped.items():
        for n in nums:
            final_map[n] = name

    return final_map

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# WhatsApp message generation
def generate_whatsapp_messages(df):
    filtered = []
    seen_keys = set()

    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand", "")).strip()
        street = str(row.get("Street No", "")).strip()

        if not sector or not plot_no or not plot_size or not demand:
            continue
        if sector.startswith("I-15/") and not street:
            continue
        if "series" in plot_no.lower():
            continue

        key = (sector, plot_no, plot_size, demand)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        filtered.append({
            "Sector": sector,
            "Street No": street,
            "Plot No": plot_no,
            "Plot Size": plot_size,
            "Demand": demand
        })

    def extract_plot_number(val):
        match = re.search(r"\d+", val)
        return int(match.group()) if match else float("inf")

    grouped = {}
    for row in filtered:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    message_chunks = []
    current_msg = ""

    for (sector, size), items in sorted(grouped.items()):
        sorted_items = sorted(items, key=lambda x: extract_plot_number(x["Plot No"]))
        header = f"*Available Options in {sector} Size: {size}*\n"
        lines = []

        for r in sorted_items:
            if sector in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]:
                line = f"St: {r['Street No']} | P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}"
            else:
                line = f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}"
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

# Main app
def main():
    if not login():
        return

    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    contact_name_map = get_contact_name_map(df)

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street No")
        plot_no_filter = st.text_input("Plot No")
        contact_filter = st.text_input("Phone Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        dealer_names = sorted(set(contact_name_map.values()))
        selected_dealer = st.selectbox("Dealer Name (Grouped)", [""] + dealer_names)

        saved_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_saved = st.selectbox("📇 Saved Contacts (for Filtering)", saved_names)

    df_filtered = df.copy()

    if selected_dealer:
        selected_contacts = [num for num, name in contact_name_map.items() if name == selected_dealer]
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda val: any(n in clean_number(val) for n in selected_contacts if n)
        )]

    if selected_saved:
        row = contacts_df[contacts_df["Name"] == selected_saved]
        selected_contacts = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            selected_contacts.extend(extract_numbers(row[col].values[0]) if col in row.columns else [])
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda val: any(n in clean_number(val) for n in selected_contacts if n)
        )]

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street No"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No"].str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        cnum = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(lambda x: cnum in clean_number(x))]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    selected_name_whatsapp = st.selectbox("📱 Select Contact to Message", saved_names, key="wa_contact")
    manual_number = st.text_input("Or Enter WhatsApp Number (e.g. 0300xxxxxxx)")

    if st.button("Generate WhatsApp Message"):
        cleaned = ""

        if manual_number:
            cleaned = clean_number(manual_number)
        elif selected_name_whatsapp:
            row = contacts_df[contacts_df["Name"] == selected_name_whatsapp]
            numbers = [clean_number(str(row[c].values[0])) for c in ["Contact1", "Contact2", "Contact3"]
                       if c in row.columns and pd.notna(row[c].values[0])]
            cleaned = numbers[0] if numbers else ""

        if not cleaned:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
            return

        if len(cleaned) == 10 and cleaned.startswith("3"):
            wa_number = "92" + cleaned
        elif len(cleaned) == 11 and cleaned.startswith("03"):
            wa_number = "92" + cleaned[1:]
        elif len(cleaned) == 12 and cleaned.startswith("92"):
            wa_number = cleaned
        else:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
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