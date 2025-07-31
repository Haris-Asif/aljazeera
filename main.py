import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# ------------------------ LOGIN AUTHENTICATION ------------------------
def login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("🔐 Al-Jazeera Real Estate Login")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")

            if submitted:
                if username == "aljazeera" and password == "H@ri$_980":
                    st.session_state.logged_in = True
                    st.experimental_rerun()
                else:
                    st.error("❌ Invalid username or password.")
        return False
    return True

# ------------------------ CLEANING UTILS ------------------------
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text):
    text = str(text or "")
    parts = re.split(r"[,\s]+", text)
    return [clean_number(p) for p in parts if clean_number(p).startswith("03") or clean_number(p).startswith("923")]

# ------------------------ GOOGLE SHEETS SETUP ------------------------
SPREADSHEET_NAME = "Al-Jazeera"
PLOTS_SHEET = "Plots"
CONTACTS_SHEET = "Contacts"

def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def load_plot_data():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    df["SheetRowNum"] = [i + 2 for i in range(len(df))]  # Account for header
    return df

def load_contacts():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# ------------------------ FILTERING & MAPPING ------------------------
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

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# ------------------------ GROUPED NAME CONTACT ------------------------
def build_unique_name_map(df):
    name_map = {}
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name") or "").strip()
        contacts = extract_numbers(row.get("Extracted Contact", ""))
        for num in contacts:
            if num not in name_map:
                name_map[num] = name
    unique_names = sorted(set(name_map.values()))
    return unique_names, name_map

# ------------------------ WHATSAPP MESSAGE BUILDER ------------------------
def generate_whatsapp_messages(df):
    filtered = []
    for _, row in df.iterrows():
        plot_no = str(row.get("Plot No", "")).strip()
        if "series" in plot_no.lower():
            continue

        sector = str(row.get("Sector", "")).strip()
        size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand", "")).strip()

        if not (sector and plot_no and size and demand):
            continue

        filtered.append({
            "Sector": sector,
            "Plot No": plot_no,
            "Plot Size": size,
            "Demand": demand
        })

    # Sort by plot number
    def extract_plot_number(val):
        try:
            return int(re.search(r"\d+", str(val)).group())
        except:
            return float("inf")

    filtered.sort(key=lambda x: extract_plot_number(x["Plot No"]))

    # Group and format
    grouped = {}
    for row in filtered:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    chunks = []
    current = ""
    for (sector, size), items in grouped.items():
        block = f"*Available Options in {sector} Size: {size}*\n"
        lines = [f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}" for r in items]
        section = block + "\n".join(lines) + "\n\n"
        if len(current + section) > 3900:
            chunks.append(current.strip())
            current = section
        else:
            current += section

    if current:
        chunks.append(current.strip())

    return chunks

# ------------------------ MAIN APP ------------------------
def main():
    if not login():
        return

    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_plot_data().fillna("")
    contacts_df = load_contacts()

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street No")
        plot_no_filter = st.text_input("Plot No")
        contact_filter = st.text_input("Phone Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        # Dealer names from grouped contacts
        all_numbers = {}
        for _, row in df.iterrows():
            name = str(row.get("Extracted Name", "")).strip()
            numbers = extract_numbers(row.get("Extracted Contact", ""))
            for n in numbers:
                if n not in all_numbers:
                    all_numbers[n] = name
        dealer_options = sorted(set(all_numbers.values()))
        selected_dealer = st.selectbox("Dealer Name (Grouped)", [""] + dealer_options)

        saved_contacts = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_contact = st.selectbox("📇 Saved Contact (Grouped)", saved_contacts)

    df_filtered = df.copy()

    # Apply dealer grouping filter
    if selected_dealer:
        selected_numbers = [k for k, v in all_numbers.items() if v == selected_dealer]
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(n in clean_number(str(x)) for n in selected_numbers)
        )]

    # Apply saved contact filter
    if selected_contact:
        row = contacts_df[contacts_df["Name"] == selected_contact]
        contact_nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in row.columns:
                contact_nums.extend(extract_numbers(row[col].values[0]))
        if contact_nums:
            df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
                lambda x: any(n in clean_number(str(x)) for n in contact_nums)
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
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(lambda x: cnum in clean_number(str(x)))]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    selected_name_whatsapp = st.selectbox("📱 Select Contact to Message", saved_contacts, key="wa_contact")
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