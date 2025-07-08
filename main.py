import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Config
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "RealEstateTool"
LISTINGS_SHEET = "Sheet1"
CONTACTS_SHEET = "Contacts"
REQUIRED_COLUMNS = ["Sector", "Plot No#", "Plot Size", "Demand/Price"]

# Authorize and Load Data
def load_sheet_data(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(sheet_name)
    data = sheet.get_all_records()
    return pd.DataFrame(data), sheet

# Helpers
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

def valid_sector_format(sector):
    return bool(re.match(r"^[A-Z]-\d+/\d+$", str(sector).strip().upper()))

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

def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    days = days_map.get(label, 0)
    if days == 0:
        return df
    cutoff = datetime.today() - timedelta(days=days)
    df["ParsedDate"] = df["Date"].apply(parse_date)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

def generate_whatsapp_messages(df):
    valid_rows = []
    for _, row in df.iterrows():
        sector = str(row["Sector"]).strip()
        plot_no = str(row["Plot No#"]).strip()
        size = str(row["Plot Size"]).strip()
        demand = str(row["Demand/Price"]).strip()
        street = str(row.get("Street#", "")).strip()

        if not valid_sector_format(sector):
            continue
        if not (sector and plot_no and size and demand):
            continue
        if sector in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] and not street:
            continue

        valid_rows.append({
            "Sector": sector,
            "Plot No#": plot_no,
            "Plot Size": size,
            "Demand/Price": demand,
            "Street#": street
        })

    # Deduplicate
    seen = set()
    final = []
    for r in valid_rows:
        key = (
            r["Sector"], r["Plot No#"], r["Plot Size"], r["Demand/Price"],
            r["Street#"] if r["Sector"] in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] else ""
        )
        if key not in seen:
            seen.add(key)
            final.append(r)

    # Group by Sector + Size
    grouped = {}
    for row in final:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    # Format messages
    messages = []
    current_msg = ""
    char_limit = 3900  # Just under WhatsApp's ~4096 character limit

    for (sector, size), items in sorted(grouped.items()):
        group_text = f"*Available Options in {sector} Size: {size}*\n"
        for row in items:
            if sector.startswith("I-15/"):
                group_text += f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                group_text += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        group_text += "\n"

        if len(current_msg) + len(group_text) > char_limit:
            messages.append(current_msg.strip())
            current_msg = group_text
        else:
            current_msg += group_text

    if current_msg.strip():
        messages.append(current_msg.strip())

    return messages

# Main app
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df, _ = load_sheet_data(LISTINGS_SHEET)
    contacts_df, contacts_sheet = load_sheet_data(CONTACTS_SHEET)
    df = df.fillna("")
    contacts_df = contacts_df.fillna("")

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        selected_name = st.selectbox("📇 Filter Listings by Saved Contact", [""] + sorted(contacts_df["Name"].dropna().unique()))

    df_filtered = df.copy()

    # Apply contact filter
    if selected_name:
        row = contacts_df[contacts_df["Name"] == selected_name]
        nums = [str(row[col].values[0]).strip() for col in ["Contact1", "Contact2", "Contact3"] if str(row[col].values[0]).strip()]
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(
            lambda val: any(clean_number(n) in clean_number(val) for n in nums)
        )]

    if contact_filter:
        cleaned = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda val: cleaned in clean_number(val))]

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda val: sector_matches(sector_filter, val))]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    df_filtered = filter_by_date(df_filtered, date_filter)

    # Show listings
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    # WhatsApp message
    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    col1, col2 = st.columns([3, 2])
    with col1:
        number_input = st.text_input("Enter WhatsApp Number (03xxxxxxxxx)")
    with col2:
        contact_to_send = st.selectbox("Or select contact to send to", [""] + sorted(contacts_df["Name"].dropna().unique()))

    final_number = ""
    if number_input.strip().startswith("03"):
        final_number = number_input.strip()
    elif contact_to_send:
        row = contacts_df[contacts_df["Name"] == contact_to_send]
        raw = str(row["Contact1"].values[0]).strip()
        final_number = raw if raw.startswith("03") else "03" + raw

    if st.button("Generate WhatsApp Message"):
        if not final_number.startswith("03"):
            st.error("❌ Please enter or select a valid WhatsApp number starting with 03...")
        else:
            messages = generate_whatsapp_messages(df_filtered)
            if not messages:
                st.warning("⚠️ No valid listings to share.")
            else:
                st.success("✅ WhatsApp Message(s) Ready!")
                for i, msg in enumerate(messages, 1):
                    encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                    full_number = "92" + final_number.lstrip("0")
                    link = f"https://wa.me/{full_number}?text={encoded}"
                    st.markdown(f"[📩 Send Message Part {i} on WhatsApp]({link})", unsafe_allow_html=True)

    # Save contact
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1*", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        save = st.form_submit_button("Save Contact")
        if save:
            if name and c1:
                new_row = [name, c1, c2, c3]
                contacts_sheet.append_row(new_row)
                st.success(f"✅ Contact '{name}' saved to Google Sheet.")
            else:
                st.warning("⚠️ Name and Contact1 are required.")

if __name__ == "__main__":
    main()