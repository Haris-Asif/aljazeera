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

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# ---------------- AUTH ---------------- #
def login():
    st.sidebar.title("🔐 Login")
    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")
    if username == "aljazeera" and password == "H@ri$_980":
        return True
    else:
        st.sidebar.warning("Enter valid credentials to continue.")
        return False

# ---------------- UTILS ---------------- #
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text):
    text = str(text or "")
    parts = re.split(r"[,\s]+", text)
    return [clean_number(p) for p in parts if clean_number(p)]

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
    df["SheetRowNum"] = [i + 2 for i in range(len(df))]
    return df

def load_contacts():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    return pd.DataFrame(sheet.get_all_records())

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

def build_dealer_name_map(df):
    contact_to_name = {}
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name", "")).strip()
        contacts = extract_numbers(row.get("Extracted Contact", ""))
        for num in contacts:
            if num not in contact_to_name:
                contact_to_name[num] = name
    unique_names = sorted(set(contact_to_name.values()))
    return unique_names, contact_to_name

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    return f in c if "/" not in f else f == c

def generate_whatsapp_messages(df):
    filtered = []
    seen = set()
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No", "")).strip()
        size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand", "")).strip()

        if "series" in plot_no.lower():
            continue
        if not (sector and plot_no and size and demand):
            continue
        key = (sector, plot_no, size)
        if key in seen:
            continue
        seen.add(key)

        filtered.append({
            "Sector": sector,
            "Plot No": plot_no,
            "Plot Size": size,
            "Demand": demand
        })

    def plot_sort_key(val):
        try:
            return int(re.search(r"\d+", val).group())
        except:
            return float('inf')

    grouped = {}
    for row in filtered:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    chunks, current_msg = [], ""
    for (sector, size), items in grouped.items():
        sorted_items = sorted(items, key=lambda x: plot_sort_key(x["Plot No"]))
        lines = [f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}" for r in sorted_items]
        block = f"*Available Options in {sector} Size: {size}*\n" + "\n".join(lines) + "\n\n"
        if len(current_msg + block) > 3900:
            chunks.append(current_msg.strip())
            current_msg = block
        else:
            current_msg += block
    if current_msg:
        chunks.append(current_msg.strip())
    return chunks

# ---------------- MAIN ---------------- #
def main():
    if not login():
        st.stop()

    st.title("🏡 Al-Jazeera Real Estate Tool")
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    dealer_names, contact_to_name = build_dealer_name_map(df)

    with st.sidebar:
        st.header("🔍 Filters")
        sector = st.text_input("Sector")
        size = st.text_input("Plot Size")
        street = st.text_input("Street No")
        plot_no = st.text_input("Plot No")
        contact_filter = st.text_input("Phone Number")
        date_range = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        dealer_name = st.selectbox("Dealer Name", [""] + dealer_names)
        saved_contact = st.selectbox("📇 Saved Contacts", [""] + sorted(contacts_df["Name"].dropna().unique()))

    df_filtered = df.copy()

    # Dealer Name filter
    if dealer_name:
        numbers = [num for num, name in contact_to_name.items() if name == dealer_name]
        if numbers:
            df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(lambda x: any(n in clean_number(x) for n in numbers))]

    # Saved Contact filter
    if saved_contact:
        row = contacts_df[contacts_df["Name"] == saved_contact]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in row.columns:
                nums.extend(extract_numbers(row[col].values[0]))
        if nums:
            df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(lambda x: any(n in clean_number(x) for n in nums))]

    if sector:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector, x))]
    if size:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(size, case=False, na=False)]
    if street:
        df_filtered = df_filtered[df_filtered["Street No"].str.contains(street, case=False, na=False)]
    if plot_no:
        df_filtered = df_filtered[df_filtered["Plot No"].str.contains(plot_no, case=False, na=False)]
    if contact_filter:
        cnum = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(lambda x: cnum in clean_number(x))]

    df_filtered = filter_by_date(df_filtered, date_range)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")
    contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
    selected_wa = st.selectbox("📱 Select Contact to Message", contact_names, key="wa_contact")
    manual_number = st.text_input("Or Enter WhatsApp Number (e.g. 0300xxxxxxx)")

    if st.button("Generate WhatsApp Message"):
        number = ""
        if manual_number:
            number = clean_number(manual_number)
        elif selected_wa:
            row = contacts_df[contacts_df["Name"] == selected_wa]
            nums = [clean_number(row[c].values[0]) for c in ["Contact1", "Contact2", "Contact3"]
                    if c in row.columns and pd.notna(row[c].values[0])]
            number = nums[0] if nums else ""

        if not number:
            st.error("❌ Invalid number.")
            return
        if len(number) == 10 and number.startswith("3"):
            wa_number = "92" + number
        elif len(number) == 11 and number.startswith("03"):
            wa_number = "92" + number[1:]
        elif len(number) == 12 and number.startswith("92"):
            wa_number = number
        else:
            st.error("❌ Invalid number format.")
            return

        msgs = generate_whatsapp_messages(df_filtered)
        if not msgs:
            st.warning("⚠️ No valid listings.")
        else:
            for i, msg in enumerate(msgs):
                encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                link = f"https://wa.me/{wa_number}?text={encoded}"
                st.markdown(f"[📩 Send Message {i+1}]({link})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()