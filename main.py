import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse
import os

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
START_ROW = 10928  # Row where headers start

CONTACTS_CSV = "contacts.csv"

# Load Google Sheets data starting from a specific row
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    all_rows = sheet.get_all_values()
    header = all_rows[START_ROW - 1]
    data = all_rows[START_ROW:]
    df = pd.DataFrame(data, columns=header)
    return df

# Sector matching logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = cell_val.replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# WhatsApp message generator
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
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, sec in listings:
            if "I-15" in sec:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

# Save contact to CSV
def save_contact(name, contact1, contact2, contact3):
    df = pd.DataFrame([[name, contact1, contact2, contact3]], columns=["Name", "Contact1", "Contact2", "Contact3"])
    if os.path.exists(CONTACTS_CSV):
        df.to_csv(CONTACTS_CSV, mode='a', header=False, index=False)
    else:
        df.to_csv(CONTACTS_CSV, index=False)

# Load contacts
def load_contacts():
    if os.path.exists(CONTACTS_CSV):
        return pd.read_csv(CONTACTS_CSV)
    return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load Google Sheet
    try:
        df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"❌ Failed to load Google Sheet: {e}")
        return

    df = df.fillna("")

    with st.sidebar:
        st.subheader("🔍 Filters")
        st.markdown("Sector format: `I-14`, `I-14/1`, etc.")
        sector_filter = st.text_input("Sector")
        st.markdown("e.g. `25x50`, `30x60`")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")

        st.subheader("📇 Search by Saved Contact")
        contacts_df = load_contacts()
        selected_contact = st.selectbox("Select Contact", [""] + contacts_df["Name"].tolist())
        if selected_contact:
            numbers = contacts_df[contacts_df["Name"] == selected_contact][["Contact1", "Contact2", "Contact3"]].values.flatten()
            contact_filter = "|".join([str(n) for n in numbers if pd.notna(n)])

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
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_filter, case=False, na=False)]

    df_filtered = df_filtered.drop_duplicates(subset=["Sector", "Plot No#", "Plot Size", "Street#", "Demand/Price"])

    # Show filtered listings
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # WhatsApp message generation
    st.subheader("📤 Generate WhatsApp Message")
    if st.button("Generate Message"):
        if df_filtered.empty:
            st.warning("No listings to include.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            st.text_area("Generated WhatsApp Message", msg, height=300)

            phone_number = st.text_input("📞 WhatsApp Number (e.g., 923001234567)")
            if phone_number:
                encoded_msg = urllib.parse.quote(msg)
                wa_link = f"https://wa.me/{phone_number}?text={encoded_msg}"
                st.markdown(f"[Send to WhatsApp]({wa_link})", unsafe_allow_html=True)

    # Add contact form
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact 1*", key="c1")
        c2 = st.text_input("Contact 2", key="c2")
        c3 = st.text_input("Contact 3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1:
                save_contact(name, c1, c2, c3)
                st.success(f"Contact '{name}' saved.")
            else:
                st.warning("Name and Contact 1 are required.")

if __name__ == "__main__":
    main()