import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_CSV = "contacts.csv"
DATA_START_ROW = 1  # Column names on 10928, data starts from 10929
REQUIRED_COLUMNS = ["Sector", "Plot Size", "Plot No#", "Street#", "Demand/Price"]

# Load Google Sheet Data
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    records = sheet.get_all_values()
    header = records[DATA_START_ROW - 1]
    data = records[DATA_START_ROW:]
    df = pd.DataFrame(data, columns=header)
    return df

# Clean and deduplicate listings
def preprocess_data(df):
    df = df.copy()
    df = df.replace("", pd.NA).dropna(subset=REQUIRED_COLUMNS)

    # Keep only valid sector format (e.g., I-14/1)
    df = df[df["Sector"].str.match(r"^[A-Z]-\d+/\d+$", na=False)]

    # Convert Demand/Price to numeric safely
    df["Demand/Price"] = df["Demand/Price"].astype(str).str.replace(",", "").str.extract(r"(\d+)").astype(float)

    # Identify duplicates
    df["dup_key"] = df["Sector"].str.strip() + "_" + df["Plot Size"].str.strip() + "_" + \
                    df["Plot No#"].str.strip() + "_" + df["Street#"].str.strip()

    df_sorted = df.sort_values("Demand/Price", ascending=True)
    df_unique = df_sorted.drop_duplicates("dup_key", keep="first")

    df_duplicates = df_sorted[df_sorted.duplicated("dup_key", keep="first")]

    df_unique = df_unique.drop(columns=["dup_key"])
    df_duplicates = df_duplicates.drop(columns=["dup_key"])
    return df_unique.reset_index(drop=True), df_duplicates.reset_index(drop=True)

# WhatsApp message generation
def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        plot_no = str(row.get("Plot No#", "")).strip()
        price = str(int(row.get("Demand/Price", 0)))
        street = str(row.get("Street#", "")).strip()
        key = f"{sector}__{plot_size}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((plot_no, plot_size, price, street, sector))

    msg = ""
    for group_key in sorted(grouped.keys()):
        sector, size = group_key.split("__")
        listings = grouped[group_key]
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, _ in listings:
            line = f""
            if "I-15" in sector and st_:
                line += f"St: {st_} | "
            line += f"P: {p} | S: {s} | D: {d}\n"
            msg += line
        msg += "\n"
    return msg.strip()

# UI for contacts
def add_contact_ui():
    st.subheader("➕ Add Contact")
    with st.form("contact_form"):
        name = st.text_input("Contact Name", "")
        c1 = st.text_input("Contact1", "")
        c2 = st.text_input("Contact2", "")
        c3 = st.text_input("Contact3", "")
        submitted = st.form_submit_button("Save")
        if submitted and name and c1:
            new_entry = pd.DataFrame([[name, c1, c2, c3]], columns=["Name", "Contact1", "Contact2", "Contact3"])
            try:
                existing = pd.read_csv(CONTACTS_CSV)
                existing = pd.concat([existing, new_entry], ignore_index=True)
            except:
                existing = new_entry
            existing.to_csv(CONTACTS_CSV, index=False)
            st.success("Contact saved!")

def load_contacts():
    try:
        return pd.read_csv(CONTACTS_CSV)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

# Main app
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df_raw = load_data_from_gsheet()
    df, df_duplicates = preprocess_data(df_raw)

    # Sidebar Filters
    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_number_filter = st.text_input("Contact (manual)")
        contact_df = load_contacts()
        contact_names = contact_df["Name"].tolist()
        selected_contact = st.selectbox("📇 Filter by Saved Contact", [""] + contact_names)
        date_range = st.selectbox("🗓️ Date Filter", ["All", "Last 7 Days", "Last 30 Days", "Last 60 Days"])

    df_filtered = df.copy()
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].str.contains(sector_filter, case=False, na=False)]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]
    if contact_number_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_number_filter, na=False)]

    if selected_contact:
        contact_row = contact_df[contact_df["Name"] == selected_contact]
        nums = [str(contact_row[col].values[0]) for col in ["Contact1", "Contact2", "Contact3"]
                if col in contact_row and str(contact_row[col].values[0]).strip() != ""]
        if nums:
            import re
            pattern = "|".join(map(re.escape, nums))
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(pattern, na=False, case=False)]

    if date_range != "All":
        days = 7 if "7" in date_range else (30 if "30" in date_range else 60)
        cutoff = datetime.now() - timedelta(days=days)
        def parse_date(date_str):
            try:
                return pd.to_datetime(date_str.split(",")[0].strip())
            except:
                return None
        df_filtered["parsed_date"] = df_filtered["Date"].apply(parse_date)
        df_filtered = df_filtered[df_filtered["parsed_date"] >= cutoff]
        df_filtered = df_filtered.drop(columns=["parsed_date"])

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]])

    if st.button("📤 Generate WhatsApp Message"):
        if df_filtered.empty:
            st.warning("No listings available to generate message.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            st.text_area("📄 Message Preview", msg, height=300)
            number = st.text_input("📱 Enter WhatsApp number (03XXXXXXXXX):")
            if number:
                num = number.strip().replace(" ", "").replace("+92", "0")
                if num.startswith("03"):
                    num = "92" + num[1:]
                wa_link = f"https://wa.me/{num}?text={msg.replace(' ', '%20').replace('|', '%7C').replace('\n', '%0A')}"
                st.markdown(f"[✅ Send Message on WhatsApp]({wa_link})", unsafe_allow_html=True)

    with st.expander("📂 View Discarded/Duplicate Listings"):
        if df_duplicates.empty:
            st.info("No duplicates or discarded listings.")
        else:
            st.dataframe(df_duplicates)

    st.markdown("---")
    add_contact_ui()

if __name__ == "__main__":
    main()