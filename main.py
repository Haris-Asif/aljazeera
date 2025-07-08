import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Config
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_ID = "1EXeS9dsKQn4MQaXrb8YEI6CF0wfsh0ANTskOfublZb4"
LISTINGS_WS = "Plots_Sale"
CONTACTS_WS = "Contacts"

# Load Google Sheets
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

def load_data_from_gsheet():
    client = get_gsheet_client()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(LISTINGS_WS)
    data = sheet.get_all_records()
    return pd.DataFrame(data).fillna("")

def load_contacts():
    client = get_gsheet_client()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(CONTACTS_WS)
    data = sheet.get_all_records()
    return pd.DataFrame(data).fillna("")

def save_contact_to_gsheet(name, c1, c2, c3):
    client = get_gsheet_client()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(CONTACTS_WS)
    sheet.append_row([name, c1, c2, c3])

# Utility functions
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f.split("-")[0] in c

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
    days = days_map.get(days_label, 0)
    if days == 0:
        return df

    cutoff = today - timedelta(days=days)

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

# WhatsApp message generation
def generate_whatsapp_message(df):
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

    if not unique:
        return ""

    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

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

    if current_msg:
        messages.append(current_msg.strip())

    return messages

# Main App
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    contacts_df = load_contacts()

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        st.markdown("---")
        selected_name = st.selectbox("📇 Saved Contact (to filter data)", [""] + list(contacts_df["Name"].dropna().unique()))

    df_filtered = df.copy()

    if selected_name:
        contact_row = contacts_df[contacts_df["Name"] == selected_name]
        nums = [str(contact_row[col].values[0]).strip() for col in ["Contact1", "Contact2", "Contact3"]
                if col in contact_row and str(contact_row[col].values[0]).strip()]
        nums_cleaned = [clean_number(n) for n in nums]

        if nums_cleaned:
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(
                lambda x: any(n in clean_number(x) for n in nums_cleaned)
            )]

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, na=False, case=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, na=False, case=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, na=False, case=False)]

    if contact_filter:
        clean = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: clean in clean_number(x))]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    # WhatsApp Message Section
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    col1, col2 = st.columns([3, 2])
    with col1:
        manual_number = st.text_input("Enter WhatsApp Number (e.g. 03xxxxxxxxx)")
    with col2:
        selected_contact = st.selectbox("Or select contact to send to", [""] + list(contacts_df["Name"].dropna().unique()))

    final_number = ""
    if manual_number.strip().startswith("03") and len(clean_number(manual_number)) == 11:
        final_number = clean_number(manual_number)
    elif selected_contact:
        row = contacts_df[contacts_df["Name"] == selected_contact]
        if not row.empty:
            raw_number = str(row["Contact1"].values[0])
            if raw_number.startswith("03"):
                final_number = clean_number(raw_number)

    if st.button("Generate WhatsApp Message"):
        if not final_number:
            st.error("❌ Please provide a valid number starting with 03 or select a valid contact.")
        else:
            msgs = generate_whatsapp_message(df_filtered)
            if not msgs:
                st.warning("⚠️ No valid listings to include.")
            else:
                for i, msg in enumerate(msgs, 1):
                    wa_number = "92" + final_number[1:]
                    encoded_msg = msg.replace(" ", "%20").replace("\n", "%0A")
                    link = f"https://wa.me/{wa_number}?text={encoded_msg}"
                    st.markdown(f"🔗 [Part {i} - Send WhatsApp Message]({link})", unsafe_allow_html=True)

    # Contact Save Form
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact_form"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1* (e.g. 03xxxxxxxxx)", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1 and c1.startswith("03"):
                save_contact_to_gsheet(name, c1, c2, c3)
                st.success("✅ Contact saved successfully.")
            else:
                st.warning("Name and Contact1 (03xxxxxxxxx) are required.")

if __name__ == "__main__":
    main()