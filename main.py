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

# Clean number
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

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

# Extract all phone numbers from a cell
def extract_numbers(text):
    if not text:
        return []
    parts = re.split(r"[,\s]+", text)
    return [clean_number(p) for p in parts if clean_number(p).startswith("03") or clean_number(p).startswith("923")]

# Group dealer names by contacts
def build_unique_name_map(df):
    contact_name_map = {}
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name") or "").strip()
        contact_field = str(row.get("Extracted Contact") or "")
        numbers = extract_numbers(contact_field)
        for num in numbers:
            if num not in contact_name_map:
                contact_name_map[num] = name
    # Now reduce name list based on unique numbers
    name_groups = {}
    for num, name in contact_name_map.items():
        if name not in name_groups.values():
            name_groups[num] = name
    return sorted(set(name_groups.values())), contact_name_map

# Date filter
def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.now() - timedelta(days=days_map.get(label, 0))

    def parse_date(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            return None

    df["ParsedDate"] = df["Timestamp"].apply(parse_date)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

# Sector matching logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    return f in c

# Generate WhatsApp messages
def generate_whatsapp_messages(df):
    filtered = []
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand", "")).strip()
        street = str(row.get("Street No", "")).strip()

        if "series" in plot_no.lower():
            continue
        if not re.match(r"^[A-Z]-\d+(/\d+)?$", sector):
            continue
        if not (sector and plot_no and plot_size and demand):
            continue
        filtered.append({
            "Sector": sector,
            "Street No": street,
            "Plot No": plot_no,
            "Plot Size": plot_size,
            "Demand": demand
        })

    # Sort by numeric plot number
    def extract_plot_number(pn):
        try:
            return int(re.search(r"\d+", pn).group())
        except:
            return float("inf")

    filtered.sort(key=lambda r: extract_plot_number(r["Plot No"]))

    grouped = {}
    for row in filtered:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    chunks = []
    current_msg = ""
    for (sector, size), items in grouped.items():
        lines = [f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}" for r in items]
        block = f"*Available Options in {sector} Size: {size}*\n" + "\n".join(lines) + "\n\n"
        if len(current_msg + block) > 3900:
            chunks.append(current_msg.strip())
            current_msg = block
        else:
            current_msg += block
    if current_msg:
        chunks.append(current_msg.strip())

    return chunks

# Main app
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_plot_data().fillna("")
    contacts_df = load_contacts()

    # Sidebar filters
    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street No")
        plot_no_filter = st.text_input("Plot No")
        contact_filter = st.text_input("Phone Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        unique_names, contact_name_map = build_unique_name_map(df)
        selected_name = st.selectbox("Dealer Name (from Extracted Name)", [""] + unique_names)

        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_contact = st.selectbox("📇 Saved Contact (for Filtering)", contact_names)

    df_filtered = df.copy()

    # Filter by selected dealer name
    if selected_name:
        selected_contacts = []
        for _, row in df.iterrows():
            if str(row.get("Extracted Name", "")).strip().lower() == selected_name.lower():
                selected_contacts.extend(extract_numbers(row.get("Extracted Contact", "")))
        selected_contacts = set(selected_contacts)
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda val: any(n in extract_numbers(val) for n in selected_contacts)
        )]

    # Filter by saved contact
    if selected_contact:
        row = contacts_df[contacts_df["Name"] == selected_contact]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in row.columns and pd.notna(row[col].values[0]):
                nums.append(clean_number(row[col].values[0]))
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda val: any(n in extract_numbers(val) for n in nums)
        )]

    # Apply other filters
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
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda val: cnum in clean_number(val)
        )]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    selected_name_whatsapp = st.selectbox("📱 Select Contact to Message", contact_names, key="wa_contact")
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