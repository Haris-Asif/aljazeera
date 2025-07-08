import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Constants
SPREADSHEET_NAME = "RealEstateTool"
LISTINGS_SHEET = "Sheet1"
CONTACTS_SHEET = "Contacts"

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Google Sheet Loader
def load_data(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    worksheet = client.open(SPREADSHEET_NAME).worksheet(sheet_name)
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

# Clean phone number
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

# Sector matching logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    return f in c if "/" not in f else f == c

# WhatsApp message generator
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
            row["Sector"], row["Plot No#"], row["Plot Size"],
            row["Demand/Price"],
            row["Street#"] if row["Sector"] in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] else ""
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)

    # Group by (Sector, Plot Size)
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    # Build message chunks
    messages = []
    current_msg = ""
    for (sector, size), items in sorted(grouped.items()):
        group_text = f"*Available Options in {sector} Size: {size}*\n"
        for row in items:
            if sector.startswith("I-15/"):
                group_text += f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                group_text += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        group_text += "\n"

        if len(current_msg + group_text) > 3900:
            messages.append(current_msg.strip())
            current_msg = group_text
        else:
            current_msg += group_text

    if current_msg.strip():
        messages.append(current_msg.strip())

    return messages

# Date filter
def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {
        "Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60
    }
    days = days_map.get(label, 0)
    if not days:
        return df
    cutoff = datetime.today() - timedelta(days=days)

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

# App main
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    df = load_data(LISTINGS_SHEET).fillna("")
    contacts_df = load_data(CONTACTS_SHEET).fillna("")

    # Sidebar filters
    with st.sidebar:
        st.header("🔍 Filters")
        sector = st.text_input("Sector")
        size = st.text_input("Plot Size")
        street = st.text_input("Street#")
        plot_no = st.text_input("Plot No#")
        contact_text = st.text_input("Contact")
        date_range = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        filter_contact_name = st.selectbox("📇 Saved Contacts", [""] + sorted(contacts_df["Name"].dropna().unique()))

    df_filtered = df.copy()

    # Apply filters
    if filter_contact_name:
        row = contacts_df[contacts_df["Name"] == filter_contact_name]
        nums = [clean_number(str(row[c].values[0])) for c in ["Contact1", "Contact2", "Contact3"] if c in row and pd.notna(row[c].values[0])]
        if nums:
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: any(n in clean_number(x) for n in nums))]

    if sector:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector, x))]
    if size:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(size, na=False)]
    if street:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street, na=False)]
    if plot_no:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no, na=False)]
    if contact_text:
        c_clean = clean_number(contact_text)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: c_clean in clean_number(x))]

    df_filtered = filter_by_date(df_filtered, date_range)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    # WhatsApp Section
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    col1, col2 = st.columns([2, 2])
    with col1:
        manual_number = st.text_input("Enter WhatsApp Number (03xxxxxxxxx)")
    with col2:
        send_contact = st.selectbox("Or select saved contact", [""] + sorted(contacts_df["Name"].dropna().unique()))

    final_number = ""
    if manual_number.startswith("03") and len(manual_number) == 11 and manual_number.isdigit():
        final_number = manual_number
    elif send_contact:
        row = contacts_df[contacts_df["Name"] == send_contact]
        raw = str(row["Contact1"].values[0]).strip()
        if raw.startswith("03") and len(raw) == 11 and raw.isdigit():
            final_number = raw

    if st.button("Generate WhatsApp Message"):
        if not final_number:
            st.error("❌ Please enter or select a valid number starting with 03.")
        else:
            msgs = generate_whatsapp_messages(df_filtered)
            if not msgs:
                st.warning("⚠️ No valid listings found to share.")
            else:
                wa_num = "92" + final_number[1:]
                for i, msg in enumerate(msgs, 1):
                    link = f"https://wa.me/{wa_num}?text={msg.replace(' ', '%20').replace('\n', '%0A')}"
                    st.markdown(f"[📩 Message {i}]({link})", unsafe_allow_html=True)

    # Contact form
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("contact_form"):
        name = st.text_input("Name*", key="c_name")
        c1 = st.text_input("Contact1*", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        if st.form_submit_button("Save Contact"):
            if name and c1 and c1.startswith("03") and len(c1) == 11:
                client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]))
                sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
                sheet.append_row([name, c1, c2, c3])
                st.success(f"✅ Contact '{name}' saved.")
            else:
                st.error("❌ Contact1 must start with 03 and be 11 digits.")

if __name__ == "__main__":
    main()