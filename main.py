import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheet settings
SPREADSHEET_NAME = "Al-Jazeera"
PLOTS_SHEET = "Plots"
CONTACTS_SHEET = "Contacts"

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Utilities
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# Load plot listings
def load_plot_data():
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    df["SheetRowNum"] = [i + 2 for i in range(len(df))]  # header at row 1
    return df

# Load contacts
def load_contacts():
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Filter by date
def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.now() - timedelta(days=days_map[label])
    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            return None
    df["ParsedDate"] = df["Timestamp"].apply(try_parse)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

# Match sector logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# Generate WhatsApp message chunks
def generate_whatsapp_messages(df):
    filtered = []
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand", "")).strip()
        street = str(row.get("Street No", "")).strip()

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

    message_chunks = []
    current_msg = ""

    for (sector, size), items in grouped.items():
        lines = [f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}" for r in items]
        block = f"*Available Options in {sector} Size: {size}*\n" + "\n".join(lines) + "\n\n"
        if len(current_msg + block) > 3900:
            message_chunks.append(current_msg.strip())
            current_msg = block
        else:
            current_msg += block

    if current_msg:
        message_chunks.append(current_msg.strip())

    return message_chunks

# App
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

        # Names from listing
        listing_names = sorted(set(df["Sender Name"].dropna().unique()).union(set(df["Extracted Name"].dropna().unique())))
        selected_name = st.selectbox("Sender/Extracted Name", [""] + listing_names)

        # Saved contacts
        saved_contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_contact_filter = st.selectbox("📇 Saved Contact (for filtering)", saved_contact_names)

    df_filtered = df.copy()

    # Filter by selected name
    if selected_name:
        df_filtered = df_filtered[
            (df_filtered["Sender Name"] == selected_name) | (df_filtered["Extracted Name"] == selected_name)
        ]

    # Filter by saved contact numbers
    if selected_contact_filter:
        row = contacts_df[contacts_df["Name"] == selected_contact_filter]
        numbers = [clean_number(row[c].values[0]) for c in ["Contact1", "Contact2", "Contact3"]
                   if c in row.columns and pd.notna(row[c].values[0])]
        if numbers:
            df_filtered = df_filtered[df_filtered.apply(
                lambda r: any(n in clean_number(str(r.get("Sender Number", "")) + str(r.get("Extracted Contact", ""))) for n in numbers),
                axis=1
            )]

    # Manual filters
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
        df_filtered = df_filtered[df_filtered.apply(
            lambda r: cnum in clean_number(str(r.get("Sender Number", "")) + str(r.get("Extracted Contact", ""))),
            axis=1
        )]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    # WhatsApp
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    selected_contact_msg = st.selectbox("📱 Select Contact to Message", saved_contact_names, key="wa_contact")
    manual_number = st.text_input("Or Enter WhatsApp Number (e.g. 0300xxxxxxx)")

    if st.button("Generate WhatsApp Message"):
        cleaned = ""
        if manual_number:
            cleaned = clean_number(manual_number)
        elif selected_contact_msg:
            row = contacts_df[contacts_df["Name"] == selected_contact_msg]
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