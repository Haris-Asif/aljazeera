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

# Setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Utility
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text):
    text = str(text or "")
    parts = re.split(r"[,\s]+", text)
    return [clean_number(p) for p in parts if clean_number(p)]

# Google Sheets client
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# Load plot data
def load_plot_data():
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
    df = pd.DataFrame(sheet.get_all_records())
    df["SheetRowNum"] = [i + 2 for i in range(len(df))]
    return df

# Load contacts
def load_contacts():
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    return pd.DataFrame(sheet.get_all_records())

# Filter recent
def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.now() - timedelta(days=days_map.get(label, 0))

    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            return None

    df["ParsedDate"] = df["Timestamp"].apply(try_parse)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

# Build dealer name map
def build_name_map(df):
    contact_to_name = {}
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name")).strip()
        contacts = extract_numbers(row.get("Extracted Contact"))
        for c in contacts:
            if c and c not in contact_to_name:
                contact_to_name[c] = name

    name_groups = {}
    for c, name in contact_to_name.items():
        name_groups.setdefault(name, set()).add(c)

    merged = {}
    for name, numbers in name_groups.items():
        for c in numbers:
            merged[c] = name

    name_set = {}
    for _, row in df.iterrows():
        numbers = extract_numbers(row.get("Extracted Contact"))
        for c in numbers:
            if c in merged:
                name_set[merged[c]] = True

    return sorted(name_set.keys()), merged

# WhatsApp messages
def generate_whatsapp_messages(df):
    filtered = []
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No", "")).strip()
        size = str(row.get("Plot Size", "")).strip()
        price = str(row.get("Demand", "")).strip()
        street = str(row.get("Street No", "")).strip()

        if not (sector and plot_no and size and price):
            continue
        if "I-15/" in sector and not street:
            continue
        if "series" in plot_no.lower():
            continue

        filtered.append({
            "Sector": sector,
            "Plot No": plot_no,
            "Plot Size": size,
            "Demand": price,
            "Street No": street
        })

    seen = set()
    unique = []
    for row in filtered:
        key = (row["Sector"], row["Plot No"], row["Plot Size"], row["Demand"])
        if key not in seen:
            seen.add(key)
            unique.append(row)

    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    def get_sort_key(val):
        try:
            return int(re.search(r"\d+", val).group())
        except:
            return float("inf")

    messages = []
    current = ""

    for (sector, size), listings in grouped.items():
        listings = sorted(listings, key=lambda x: get_sort_key(x["Plot No"]))
        lines = []
        for r in listings:
            if sector.startswith("I-15/"):
                lines.append(f"St: {r['Street No']} | P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")
            else:
                lines.append(f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")
        block = f"*Available Options in {sector} Size: {size}*\n" + "\n".join(lines) + "\n\n"
        if len(current + block) > 3900:
            messages.append(current.strip())
            current = block
        else:
            current += block

    if current:
        messages.append(current.strip())
    return messages

# Sanitize for table
def safe_dataframe(df):
    try:
        df = df.copy()
        df = df.drop(columns=["ParsedDate"], errors="ignore")
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
        return df
    except Exception as e:
        st.error(f"⚠️ Error displaying table: {e}")
        return pd.DataFrame()

# --- Main ---
def main():
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

        dealer_names, contact_to_name = build_name_map(df)
        selected_dealer = st.selectbox("Dealer Name (by contact)", [""] + dealer_names)

        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names)

    df_filtered = df.copy()

    if selected_dealer:
        selected_contacts = [c for c, name in contact_to_name.items() if name == selected_dealer]
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(c in clean_number(x) for c in selected_contacts))]

    if selected_saved:
        row = contacts_df[contacts_df["Name"] == selected_saved]
        selected_contacts = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            selected_contacts.extend(extract_numbers(row.get(col, "")))
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(n in clean_number(x) for n in selected_contacts))]

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].astype(str).str.upper().str.replace(" ", "").str.contains(sector_filter.replace(" ", "").upper())]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street No"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No"].str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        cnum = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Extracted Contact"].astype(str).apply(lambda x: cnum in clean_number(x))]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(safe_dataframe(df_filtered))

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
            numbers = [clean_number(row[c].values[0]) for c in ["Contact1", "Contact2", "Contact3"]
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

        messages = generate_whatsapp_messages(df_filtered)
        if not messages:
            st.warning("⚠️ No valid listings to include.")
        else:
            for i, msg in enumerate(messages):
                encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                link = f"https://wa.me/{wa_number}?text={encoded}"
                st.markdown(f"[📩 Send Message {i+1}]({link})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()