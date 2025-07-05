import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import re
import os

# Google Sheet Settings
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_FILE = "contacts.csv"

# Streamlit Settings
st.set_page_config("Al-Jazeera Real Estate Tool", layout="wide")
st.title("🏡 Al-Jazeera Real Estate Tool")

# Load contacts
def load_contacts():
    if os.path.exists(CONTACTS_FILE):
        return pd.read_csv(CONTACTS_FILE).fillna("")
    else:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

# Save new contact
def save_contact(name, c1, c2, c3):
    df = load_contacts()
    df.loc[len(df)] = [name, c1, c2, c3]
    df.to_csv(CONTACTS_FILE, index=False)

# Load Google Sheet starting from row 10929
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_values()
    headers = data[10928]  # Row 10929 = index 10928
    rows = data[10929:]
    df = pd.DataFrame(rows, columns=headers)
    return df

# Validate sector format
def is_valid_sector(sector):
    return isinstance(sector, str) and bool(re.match(r"^[A-Z]-\d+/\d+$", sector.strip()))

# Pre-cleaning and deduplication
def clean_and_deduplicate(df):
    discarded = []

    def is_missing(row):
        required_cols = ["Sector", "Plot Size", "Plot No#", "Demand/Price"]
        for col in required_cols:
            if not str(row.get(col, "")).strip():
                return True
        sector = str(row.get("Sector", ""))
        if not is_valid_sector(sector):
            return True
        if sector.startswith("I-15/") and not str(row.get("Street#", "")).strip():
            return True
        return False

    clean_rows = []
    seen = set()

    for _, row in df.iterrows():
        if is_missing(row):
            discarded.append(row)
            continue
        key = (row.get("Sector", ""), row.get("Street#", ""), row.get("Plot No#", ""),
               row.get("Plot Size", ""), row.get("Demand/Price", ""))
        if key not in seen:
            seen.add(key)
            clean_rows.append(row)
        else:
            discarded.append(row)

    clean_df = pd.DataFrame(clean_rows)
    discarded_df = pd.DataFrame(discarded)
    return clean_df.fillna(""), discarded_df.fillna("")

# WhatsApp Message Generation
def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = row["Sector"]
        plot_size = row["Plot Size"]
        plot_no = row["Plot No#"]
        price = row["Demand/Price"]
        street = row.get("Street#", "")

        key = f"{sector}__{plot_size}"
        grouped.setdefault(key, []).append((plot_no, plot_size, price, street, sector))

    msg = ""
    for key, listings in grouped.items():
        sector, size = key.split("__")
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, sec in listings:
            if "I-15" in sec:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

# Contact Filters
def extract_contact_numbers(row):
    return [str(row[c]).strip() for c in ["Contact1", "Contact2", "Contact3"] if str(row[c]).strip()]

# Main App Logic
def main():
    contacts_df = load_contacts()
    selected_contact = None

    # Load Google Sheet
    try:
        raw_df = load_data_from_gsheet()
    except Exception as e:
        st.error(f"❌ Error loading sheet: {e}")
        return

    raw_df.columns = raw_df.columns.str.strip()
    clean_df, discarded_df = clean_and_deduplicate(raw_df)

    with st.sidebar:
        st.header("📋 Filters")
        sector_filter = st.text_input("Sector (e.g., I-14/1)")
        plot_size_filter = st.text_input("Plot Size (e.g., 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Phone Contains")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 30 Days", "Last 2 Months"])
        contact_name = st.selectbox("Filter by Saved Contact", [""] + contacts_df["Name"].tolist())

    df_filtered = clean_df.copy()

    # Apply filters
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].str.upper().str.contains(sector_filter.upper(), na=False)]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, na=False, case=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, na=False, case=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, na=False, case=False)]
    if contact_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_filter, na=False, case=False)]

    # Date Filter
    if date_filter != "All" and "Date" in df_filtered.columns:
        try:
            today = datetime.today()
            if date_filter == "Last 7 Days":
                date_limit = today - timedelta(days=7)
            elif date_filter == "Last 30 Days":
                date_limit = today - timedelta(days=30)
            else:
                date_limit = today - timedelta(days=60)

            def parse_date(d):
                try:
                    return datetime.strptime(d.split(",")[0].strip(), "%Y-%m-%d")
                except:
                    return None

            df_filtered["parsed_date"] = df_filtered["Date"].apply(parse_date)
            df_filtered = df_filtered[df_filtered["parsed_date"].notnull()]
            df_filtered = df_filtered[df_filtered["parsed_date"] >= date_limit]
        except:
            pass

    # Filter by selected contact
    if contact_name:
        row = contacts_df[contacts_df["Name"] == contact_name]
        if not row.empty:
            nums = extract_contact_numbers(row.iloc[0])
            if nums:
                pattern = "|".join(map(re.escape, nums))
                df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(pattern, na=False)]

    df_filtered = df_filtered.fillna("")
    st.subheader("📋 Filtered Listings")
    cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[cols])

    # WhatsApp Message Generation
    st.subheader("📤 Generate WhatsApp Message")
    number = st.text_input("Enter WhatsApp Number (03xxxxxxxxx)")
    if st.button("Generate & Send"):
        if df_filtered.empty:
            st.warning("No listings to include.")
        elif not number.strip():
            st.warning("Please enter a WhatsApp number.")
        else:
            message = generate_whatsapp_message(df_filtered)
            encoded = message.replace("\n", "%0A").replace(" ", "%20")
            number_link = f"https://wa.me/92{number.strip()[1:]}?text={encoded}"
            st.success("✅ Click below to send message:")
            st.markdown(f"[📨 Send via WhatsApp]({number_link})", unsafe_allow_html=True)

    # Discarded Listings Viewer
    with st.expander("🚫 View Discarded Listings"):
        st.warning("These listings were ignored due to missing/duplicate/invalid values.")
        st.dataframe(discarded_df)

    # Add New Contact Form
    st.subheader("➕ Add New Contact")
    with st.form("add_contact_form"):
        cname = st.text_input("Name*", key="cname")
        c1 = st.text_input("Contact 1*", key="c1")
        c2 = st.text_input("Contact 2", key="c2")
        c3 = st.text_input("Contact 3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if cname.strip() and c1.strip():
                save_contact(cname.strip(), c1.strip(), c2.strip(), c3.strip())
                st.success("✅ Contact Saved")
            else:
                st.error("❌ Name & Contact 1 are required")

if __name__ == "__main__":
    main()