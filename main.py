import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import urllib.parse
import os

# -------------------- CONFIG --------------------
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CSV_FILE = "contacts.csv"
START_ROW = 10928  # Google Sheet rows start from 1 (header at 10928, data at 10929)

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# -------------------- LOAD GOOGLE SHEET --------------------
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    
    all_rows = sheet.get_all_values()
    if len(all_rows) < START_ROW:
        return pd.DataFrame()  # Nothing yet

    headers = all_rows[START_ROW - 1]
    data = all_rows[START_ROW:]
    df = pd.DataFrame(data, columns=headers)
    return df

# -------------------- UTILITIES --------------------
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = cell_val.replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        plot_no = str(row.get("Plot No#", "")).strip()
        price = str(row.get("Demand/Price", "")).strip()
        street = str(row.get("Street#", "")).strip()

        if "/" not in sector:
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

# -------------------- CONTACT MANAGEMENT --------------------
def load_contacts():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE)
    return pd.DataFrame(columns=["Name", "Contact 1", "Contact 2", "Contact 3"])

def save_contact(name, c1, c2, c3):
    df = load_contacts()
    new_row = {"Name": name, "Contact 1": c1, "Contact 2": c2, "Contact 3": c3}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

# -------------------- MAIN APP --------------------
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load data
    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    if df.empty:
        st.warning("No listings found in sheet.")
        return

    df = df.fillna("")
    df["Date"] = pd.to_datetime(df["Date"].str.split(",").str[0], errors="coerce")

    contacts_df = load_contacts()

    # -------------------- SIDEBAR FILTERS --------------------
    with st.sidebar:
        st.subheader("🔍 Filters")
        st.markdown("**Sector** format: `I-14`, `I-14/1`, etc.")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size (e.g., 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 days", "Last 14 days", "Last 30 days", "Last 60 days"])

        st.markdown("---")
        st.subheader("📇 Saved Contacts")
        selected_contact = st.selectbox("Select Contact", ["None"] + contacts_df["Name"].tolist())
        if selected_contact != "None":
            nums = contacts_df[contacts_df["Name"] == selected_contact][["Contact 1", "Contact 2", "Contact 3"]].values.flatten().tolist()
            contact_filter = next((n for n in nums if n and str(n).strip() != ""), "")
        else:
            contact_filter = st.text_input("Search by Contact Number")

    # -------------------- FILTERING --------------------
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
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_filter, na=False, case=False)]

    # Apply Date Range filter
    if date_filter != "All":
        days = int(date_filter.split()[1])
        cutoff = pd.Timestamp.now() - timedelta(days=days)
        df_filtered = df_filtered[df_filtered["Date"] >= cutoff]

    # Remove duplicates
    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    # -------------------- DISPLAY --------------------
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # -------------------- MESSAGE GENERATION --------------------
    st.subheader("📤 Generate WhatsApp Message")
    if df_filtered.empty:
        st.warning("No listings to generate message.")
    else:
        msg = generate_whatsapp_message(df_filtered)
        num_to_send = st.text_input("Enter WhatsApp Number (e.g. 03XXXXXXXXX):")
        if st.button("Send via WhatsApp"):
            if num_to_send.startswith("03") and len(num_to_send) == 11:
                link = f"https://wa.me/92{num_to_send[1:]}?text={urllib.parse.quote(msg)}"
                st.markdown(f"[📩 Click to Send Message on WhatsApp]({link})", unsafe_allow_html=True)
            else:
                st.error("Please enter a valid 11-digit number starting with 03")

    # -------------------- ADD CONTACT --------------------
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        new_name = st.text_input("Name", key="new_name")
        c1 = st.text_input("Contact 1", key="c1")
        c2 = st.text_input("Contact 2 (optional)", key="c2")
        c3 = st.text_input("Contact 3 (optional)", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if new_name and c1:
                save_contact(new_name, c1, c2, c3)
                st.success(f"Saved contact: {new_name}")
            else:
                st.error("Name and Contact 1 are required.")

if __name__ == "__main__":
    main()