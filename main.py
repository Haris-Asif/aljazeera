import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# CONFIG
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")
SPREADSHEET_NAME = "RealEstateTool"
PROPERTIES_SHEET = "Sheet1"
CONTACTS_SHEET = "Contacts"
REQUIRED_COLUMNS = ["Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price"]

# --- UTILITIES ---
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

def parse_date(val):
    try:
        return datetime.strptime(val.strip(), "%Y-%m-%d, %H:%M")
    except:
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d")
        except:
            return None

# --- GOOGLE SHEET ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def load_data_from_gsheet():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(PROPERTIES_SHEET)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def load_contacts():
    try:
        client = get_gsheet_client()
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def save_contact_to_sheet(name, c1, c2, c3):
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    sheet.append_row([name, c1, c2, c3])

# --- FILTERS ---
def filter_by_date(df, days_label):
    if days_label == "All":
        return df
    today = datetime.today()
    days_map = {
        "Last 7 Days": 7,
        "Last 15 Days": 15,
        "Last 30 Days": 30,
        "Last 2 Months": 60
    }
    cutoff = today - timedelta(days=days_map.get(days_label, 0))
    df["ParsedDate"] = df["Date"].apply(parse_date)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

# --- MESSAGE GENERATOR ---
def generate_whatsapp_chunks(df):
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

    # Deduplicate
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

    # Group by (Sector, Size)
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    # Format messages
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

        if len(current_msg) + len(group_text) > 3900:
            messages.append(current_msg.strip())
            current_msg = group_text
        else:
            current_msg += group_text

    if current_msg.strip():
        messages.append(current_msg.strip())

    return messages

# --- MAIN APP ---
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    contacts_df = load_contacts()
    df = df.fillna("")

    # --- Sidebar Filters ---
    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        selected_name = st.selectbox("📇 Saved Contacts (for filter)", [""] + sorted(contacts_df["Name"].dropna().unique()))

    df_filtered = df.copy()

    # Apply filters
    if selected_name:
        contact_row = contacts_df[contacts_df["Name"] == selected_name]
        nums = [clean_number(contact_row[col].values[0]) for col in ["Contact1", "Contact2", "Contact3"]
                if col in contact_row.columns and str(contact_row[col].values[0]).strip()]
        if nums:
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(
                lambda x: any(n in clean_number(x) for n in nums)
            )]

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

    # --- Display Table ---
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    # --- WhatsApp Message ---
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    col1, col2 = st.columns([3, 2])
    with col1:
        number = st.text_input("Enter WhatsApp Number (03xxxxxxxxx)")
    with col2:
        wa_contact = st.selectbox("Or select saved contact to send", [""] + list(contacts_df["Name"].dropna().unique()))

    final_number = ""
    if number and number.strip().startswith("03"):
        final_number = number.strip()
    elif wa_contact:
        row = contacts_df[contacts_df["Name"] == wa_contact]
        if not row.empty:
            raw_number = row["Contact1"].values[0]
            final_number = "03" + str(raw_number) if str(raw_number).startswith("3") else str(raw_number)

    if st.button("Generate WhatsApp Message"):
        if not final_number:
            st.error("❌ Please enter a valid number or select a contact.")
        else:
            msg_chunks = generate_whatsapp_chunks(df_filtered)
            if not msg_chunks:
                st.warning("⚠️ No valid listings to include in WhatsApp message.")
            else:
                wa_number = "92" + clean_number(final_number).lstrip("0")
                for i, chunk in enumerate(msg_chunks):
                    encoded = chunk.replace(' ', '%20').replace('\n', '%0A')
                    url = f"https://wa.me/{wa_number}?text={encoded}"
                    st.markdown(f"[📩 Send Message Part {i+1}]({url})", unsafe_allow_html=True)

    # --- Contact Save Form ---
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1*", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1:
                save_contact_to_sheet(name, c1, c2, c3)
                st.success(f"Contact '{name}' saved to Google Sheet.")
            else:
                st.warning("Name and Contact1 are required.")

if __name__ == "__main__":
    main()