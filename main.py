import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import urllib.parse
import os

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
REQUIRED_COLUMNS = ["Sector", "Plot No#", "Plot Size", "Demand/Price", "Street#", "Date"]

def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

    header_row = 10929
    data_start_row = header_row + 1

    all_rows = sheet.get_all_values()
    headers = sheet.row_values(header_row)
    data_rows = all_rows[data_start_row - 1:]
    data_rows = [row for row in data_rows if len(row) >= len(headers)]

    df = pd.DataFrame(data_rows, columns=headers)
    return df

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = cell_val.replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.split(",")[0], "%Y-%m-%d")
    except:
        return None

def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = row.get("Sector", "").strip()
        plot_size = row.get("Plot Size", "").strip()
        plot_no = row.get("Plot No#", "").strip()
        price = row.get("Demand/Price", "").strip()
        street = row.get("Street#", "").strip()

        if not sector or not plot_size:
            continue

        sector_key = sector.split("/")[0].upper()
        full_group = f"{sector}__{plot_size}"

        if full_group not in grouped:
            grouped[full_group] = []
        grouped[full_group].append((plot_no, plot_size, price, street, sector))

    msg = ""
    for group_key in sorted(grouped.keys()):
        sector, size = group_key.split("__")
        listings = grouped[group_key]
        if "I-15" in sector:
            msg += f"*Available Options in {sector} Size: {size}*\n"
            for p, s, d, st_, _ in listings:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
        else:
            msg += f"*Available Options in {sector} Size: {size}*\n"
            for p, s, d, _, _ in listings:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

def add_contact_ui():
    st.subheader("➕ Add New Contact")
    new_name = st.text_input("Name")
    new_num1 = st.text_input("Phone Number 1")
    new_num2 = st.text_input("Phone Number 2 (Optional)")
    new_num3 = st.text_input("Phone Number 3 (Optional)")

    if st.button("Save Contact"):
        if new_name and new_num1:
            new_row = pd.DataFrame([[new_name, new_num1, new_num2, new_num3]], columns=["Name", "Contact1", "Contact2", "Contact3"])
            if os.path.exists("contacts.csv"):
                existing = pd.read_csv("contacts.csv")
                updated = pd.concat([existing, new_row], ignore_index=True)
            else:
                updated = new_row
            updated.to_csv("contacts.csv", index=False)
            st.success("Contact saved.")
        else:
            st.warning("Name and at least one number required.")

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Failed to load Google Sheet: {e}")
        return

    df = df.fillna("")
    df["ParsedDate"] = df["Date"].apply(parse_date)

    with st.sidebar:
        st.subheader("🔍 Filters")
        st.markdown("**Sector**: I-14, I-15/1, etc.")
        sector_filter = st.text_input("Sector")

        st.markdown("**Plot Size**: e.g. 25x50")
        plot_size_filter = st.text_input("Plot Size")

        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")

        # Date Range Filter
        date_range = st.selectbox("Added Within", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 60 Days"])
        if date_range != "All":
            days = int(date_range.split()[1])
            date_cutoff = datetime.now() - timedelta(days=days)
            df = df[df["ParsedDate"].apply(lambda x: x and x >= date_cutoff)]

        # Load contact dropdown
        contact_filter = ""
        if os.path.exists("contacts.csv"):
            contacts_df = pd.read_csv("contacts.csv")
            selected_name = st.selectbox("Select Saved Contact", [""] + contacts_df["Name"].tolist())
            if selected_name:
                row = contacts_df[contacts_df["Name"] == selected_name].iloc[0]
                nums = [str(row.get(c, "")) for c in ["Contact1", "Contact2", "Contact3"]]
                contact_filter = next((n for n in nums if n.strip()), "")

    # Apply filters
    df_filtered = df.copy()

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    if contact_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(str(contact_filter), na=False, case=False)]

    # Drop Duplicates
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    st.subheader("📋 Filtered Listings")
    try:
        st.dataframe(df_filtered[REQUIRED_COLUMNS + ["Description/Details", "Contact"]])
    except:
        st.dataframe(df_filtered)

    if st.button("📤 Generate WhatsApp Message"):
        if df_filtered.empty:
            st.warning("No listings found.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            st.text_area("📄 Message", msg, height=300)

            st.markdown("---")
            phone = st.text_input("📱 Enter WhatsApp Number (03xxxxxxxxx)")
            if phone.startswith("03") and len(phone) == 11:
                phone_intl = "92" + phone[1:]
                encoded_msg = urllib.parse.quote(msg)
                wa_link = f"https://wa.me/{phone_intl}?text={encoded_msg}"
                st.markdown(f"[✅ Send WhatsApp Message]({wa_link})", unsafe_allow_html=True)

    st.markdown("---")
    add_contact_ui()

if __name__ == "__main__":
    main()