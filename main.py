import streamlit as st
import pandas as pd
import gspread
import re
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# Page settings
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"

def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def filter_duplicates(df):
    def is_i15_variant(sector):
        return isinstance(sector, str) and sector.strip() in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]

    df["is_i15"] = df["Sector"].apply(is_i15_variant)
    df["Street#"] = df["Street#"].fillna("")

    def row_key(row):
        if row["is_i15"] and not row["Street#"]:
            return None  # Discard listings with missing Street# in I-15/x
        if not isinstance(row["Sector"], str) or "/" not in row["Sector"]:
            return None  # Invalid sector format
        required_fields = ["Sector", "Plot Size", "Plot No#", "Demand/Price"]
        if any(not str(row.get(col, "")).strip() for col in required_fields):
            return None  # Discard listings with missing required fields
        street = row["Street#"] if row["is_i15"] else ""
        return (row["Sector"], row["Plot Size"], row["Plot No#"], street, row["Demand/Price"])

    seen = set()
    keep_rows = []
    discarded = []

    for _, row in df.iterrows():
        key = row_key(row)
        if key is None:
            discarded.append(row)
            continue
        if key not in seen:
            seen.add(key)
            keep_rows.append(row)
        else:
            discarded.append(row)

    return pd.DataFrame(keep_rows), pd.DataFrame(discarded)

def normalize_number(num):
    return re.sub(r"\D", "", str(num))

def search_by_saved_contact(df, contact_df, selected_name):
    contact_row = contact_df[contact_df["Name"] == selected_name]
    if contact_row.empty:
        return df
    nums = []
    for col in ["Contact1", "Contact2", "Contact3"]:
        val = contact_row.iloc[0].get(col, "")
        if pd.notna(val) and str(val).strip():
            nums.append(normalize_number(val))
    if not nums:
        return df

    def contact_matches(cell):
        cleaned_cell = normalize_number(cell)
        return any(n in cleaned_cell for n in nums)

    df_filtered = df[df["Contact"].astype(str).apply(contact_matches)]
    return df_filtered

def filter_by_date(df, date_option):
    if date_option == "All":
        return df
    today = datetime.today()
    if date_option == "Last 7 days":
        threshold = today - timedelta(days=7)
    elif date_option == "Last 2 months":
        threshold = today - timedelta(days=60)
    else:
        return df

    def parse_date(val):
        try:
            return datetime.strptime(val.split(",")[0].strip(), "%Y-%m-%d")
        except:
            return None

    df["ParsedDate"] = df["Date"].apply(parse_date)
    return df[df["ParsedDate"].notnull() & (df["ParsedDate"] >= threshold)]

def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        size = str(row.get("Plot Size", "")).strip()
        plot_no = str(row.get("Plot No#", "")).strip()
        price = str(row.get("Demand/Price", "")).strip()
        street = str(row.get("Street#", "")).strip()

        group_key = f"{sector}__{size}"
        if group_key not in grouped:
            grouped[group_key] = []
        grouped[group_key].append((plot_no, size, price, street, sector))

    msg = ""
    for key in sorted(grouped.keys()):
        sector, size = key.split("__")
        listings = grouped[key]
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, sec in listings:
            if sec.strip() in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load contact list
    try:
        contacts_df = pd.read_csv("contacts.csv")
    except FileNotFoundError:
        contacts_df = pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

    # Load and process data
    try:
        raw_df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"❌ Failed to load Google Sheet: {e}")
        return

    df_cleaned, df_discarded = filter_duplicates(raw_df)

    # Sidebar filters
    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14, I-14/1)")
        size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_filter = st.text_input("Plot No#")
        number_filter = st.text_input("Contact Number")
        selected_contact = st.selectbox("Search by Saved Contact", [""] + contacts_df["Name"].tolist())
        date_range = st.selectbox("Date Range", ["All", "Last 7 days", "Last 2 months"])

    df_filtered = df_cleaned.copy()

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].astype(str).str.contains(sector_filter, case=False, na=False)]

    if size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].astype(str).str.contains(size_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].astype(str).str.contains(street_filter, case=False, na=False)]

    if plot_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_filter, case=False, na=False)]

    if number_filter:
        cleaned_input = normalize_number(number_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: cleaned_input in normalize_number(x))]

    if selected_contact:
        df_filtered = search_by_saved_contact(df_filtered, contacts_df, selected_contact)

    df_filtered = filter_by_date(df_filtered, date_range)

    # Display table
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # WhatsApp message
    st.subheader("📤 Send WhatsApp Message")
    phone_input = st.text_input("Enter WhatsApp Number (03xxxxxxxxx):")
    if st.button("Generate & Send Message"):
        if not phone_input.strip():
            st.warning("Enter a phone number.")
        elif df_filtered.empty:
            st.warning("No listings to include in message.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            encoded_msg = msg.replace(" ", "%20").replace("\n", "%0A")
            number = normalize_number(phone_input)
            url = f"https://wa.me/92{number[-10:]}?text={encoded_msg}"
            st.success("✅ WhatsApp message generated below:")
            st.markdown(f"[📨 Click to send on WhatsApp]({url})", unsafe_allow_html=True)

    # Add Contact
    st.subheader("➕ Add New Contact")
    new_name = st.text_input("Name")
    new_c1 = st.text_input("Contact 1")
    new_c2 = st.text_input("Contact 2")
    new_c3 = st.text_input("Contact 3")

    if st.button("Save Contact"):
        if new_name and new_c1:
            new_row = {"Name": new_name, "Contact1": new_c1, "Contact2": new_c2, "Contact3": new_c3}
            contacts_df = pd.concat([contacts_df, pd.DataFrame([new_row])], ignore_index=True)
            contacts_df.to_csv("contacts.csv", index=False)
            st.success("Contact saved successfully.")
        else:
            st.warning("Name and Contact 1 are required.")

    # Show discarded listings
    if not df_discarded.empty:
        st.subheader("⚠️ Discarded Listings (Duplicates / Incomplete)")
        st.dataframe(df_discarded)

if __name__ == "__main__":
    main()