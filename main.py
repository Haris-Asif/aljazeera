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

# Google Sheet Integration
def load_sheet(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(sheet_name)
    return pd.DataFrame(sheet.get_all_records())

# Sector filter logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# Clean phone number
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

# Format WhatsApp messages
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

    # Group listings
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    # Split into messages if needed
    messages = []
    current_msg = ""
    for (sector, size), items in sorted(grouped.items()):
        header = f"*Available Options in {sector} Size: {size}*\n"
        block = ""
        for row in items:
            if sector.startswith("I-15/"):
                block += f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                block += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        block += "\n"

        if len(current_msg + header + block) >= 3900:
            messages.append(current_msg.strip())
            current_msg = ""

        current_msg += header + block

    if current_msg:
        messages.append(current_msg.strip())

    return messages

# Filter by Date
def filter_by_date(df, label):
    if label == "All":
        return df
    days = {
        "Last 7 Days": 7,
        "Last 15 Days": 15,
        "Last 30 Days": 30,
        "Last 2 Months": 60
    }.get(label, 0)
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

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_sheet(LISTINGS_SHEET)
    df.fillna("", inplace=True)

    contacts_df = load_sheet(CONTACTS_SHEET)

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        st.markdown("---")
        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_name = st.selectbox("📇 Saved Contacts", contact_names)

    df_filtered = df.copy()

    # Filter by saved contact (for listings)
    if selected_name:
        row = contacts_df[contacts_df["Name"] == selected_name]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in row.columns:
                val = row[col].values[0]
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
        contact_clean = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: contact_clean in clean_number(x))]

    df_filtered = filter_by_date(df_filtered, date_filter)

    # Show Filtered Listings
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    # WhatsApp Message
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")
    col1, col2 = st.columns([3, 2])
    with col1:
        number_input = st.text_input("Enter WhatsApp Number (e.g. 03xxxxxxxxx)")
    with col2:
        contact_pick = st.selectbox("Or select saved contact", [""] + list(contacts_df["Name"].dropna().unique()))

    final_number = ""
    if number_input and number_input.strip().startswith("03"):
        final_number = number_input.strip()
    elif contact_pick:
        row = contacts_df[contacts_df["Name"] == contact_pick]
        if not row.empty:
            raw = str(row["Contact1"].values[0])
            if raw.startswith("03"):
                final_number = raw

    if st.button("Generate WhatsApp Message"):
        if not final_number:
            st.error("❌ Please provide a valid number or contact.")
        else:
            msgs = generate_whatsapp_messages(df_filtered)
            if not msgs:
                st.warning("⚠️ No valid listings to include.")
            else:
                for idx, m in enumerate(msgs, 1):
                    link = f"https://wa.me/92{final_number[1:]}?text={m.replace(' ', '%20').replace('\n', '%0A')}"
                    st.markdown(f"[📩 Message {idx}]({link})", unsafe_allow_html=True)

    # Add New Contact
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1*", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1 and c1.strip().startswith("03"):
                try:
                    sheet = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(
                        st.secrets["gcp_service_account"],
                        ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                    )).open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
                    sheet.append_row([name, c1.strip(), c2.strip(), c3.strip()])
                    st.success(f"Contact '{name}' saved.")
                except Exception as e:
                    st.error("Failed to save contact.")
            else:
                st.warning("Name and Contact1 starting with 03 are required.")

if __name__ == "__main__":
    main()