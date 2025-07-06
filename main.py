import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
from datetime import datetime, timedelta

# ---- CONFIG ----
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_FILE = "contacts.csv"
REQUIRED_FIELDS_FOR_MESSAGE = ["Sector", "Plot Size", "Plot No#", "Demand/Price"]
SECTOR_WITH_REQUIRED_STREET = ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# ---- LOAD SHEET DATA ----
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# ---- FILTER HELPERS ----
def sector_matches(filter_val, cell_val):
    if not filter_val: return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f: return f == c
    return f in c

def normalize_number(number):
    return re.sub(r"[^\d]", "", str(number))

def normalize_for_matching(df, contact_numbers):
    contact_numbers = [normalize_number(n) for n in contact_numbers if n.strip()]
    if not contact_numbers:
        return df
    pattern = "|".join(map(re.escape, contact_numbers))
    return df[df["Contact"].apply(lambda x: bool(re.search(pattern, normalize_number(str(x)))) if pd.notna(x) else False)]

def filter_by_date(df, option):
    if option == "All": return df
    today = datetime.today()
    if option == "Last 7 days":
        start = today - timedelta(days=7)
    elif option == "Last 2 months":
        start = today - timedelta(days=60)
    else:
        return df

    def parse_date(val):
        try:
            return datetime.strptime(str(val).split(",")[0], "%Y-%m-%d")
        except:
            return None

    df["parsed_date"] = df["Date"].apply(parse_date)
    df = df[df["parsed_date"].notna() & (df["parsed_date"] >= start)]
    df.drop(columns=["parsed_date"], inplace=True)
    return df

# ---- WHATSAPP MESSAGE GENERATION ----
def generate_whatsapp_message(df):
    clean_df = df.copy()

    # Remove listings with missing required fields
    def is_valid(row):
        for col in REQUIRED_FIELDS_FOR_MESSAGE:
            if pd.isna(row[col]) or str(row[col]).strip() == "":
                return False
        if row["Sector"] in SECTOR_WITH_REQUIRED_STREET:
            if pd.isna(row["Street#"]) or str(row["Street#"]).strip() == "":
                return False
        return True

    clean_df = clean_df[clean_df.apply(is_valid, axis=1)]

    # Remove duplicates based on Sector, Plot Size, Plot No#, Demand/Price, and Street# (for I-15/x)
    def get_dedup_key(row):
        sector = str(row["Sector"]).strip()
        key = (
            sector,
            str(row["Plot Size"]).strip(),
            str(row["Plot No#"]).strip(),
            str(row["Demand/Price"]).strip()
        )
        if sector in SECTOR_WITH_REQUIRED_STREET:
            key += (str(row["Street#"]).strip(),)
        else:
            key += ("",)
        return key

    clean_df["dedup_key"] = clean_df.apply(get_dedup_key, axis=1)
    clean_df = clean_df.drop_duplicates(subset=["dedup_key"])
    clean_df = clean_df.drop(columns=["dedup_key"])

    # Generate message
    grouped = {}
    for _, row in clean_df.iterrows():
        sector = row["Sector"]
        plot_size = row["Plot Size"]
        plot_no = row["Plot No#"]
        price = row["Demand/Price"]
        street = row.get("Street#", "")

        group_key = f"{sector}__{plot_size}"
        grouped.setdefault(group_key, []).append((plot_no, plot_size, price, street, sector))

    msg = ""
    for group in sorted(grouped.keys()):
        sector, size = group.split("__")
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, sec in grouped[group]:
            if sec in SECTOR_WITH_REQUIRED_STREET:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

# ---- CONTACT MANAGEMENT ----
def load_contacts():
    try:
        return pd.read_csv(CONTACTS_FILE)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def save_contact(name, c1, c2, c3):
    contacts = load_contacts()
    new_row = {"Name": name, "Contact1": c1, "Contact2": c2, "Contact3": c3}
    contacts = pd.concat([contacts, pd.DataFrame([new_row])], ignore_index=True)
    contacts.to_csv(CONTACTS_FILE, index=False)

# ---- MAIN APP ----
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    df = load_data_from_gsheet()
    df = df.fillna("")

    # ---- SIDEBAR FILTERS ----
    st.sidebar.header("🔍 Filters")
    sector_filter = st.sidebar.text_input("Sector (e.g., I-14 or I-15/2)")
    plot_size_filter = st.sidebar.text_input("Plot Size (e.g., 25x50)")
    street_filter = st.sidebar.text_input("Street#")
    plot_no_filter = st.sidebar.text_input("Plot No#")
    contact_filter = st.sidebar.text_input("Contact")
    date_filter = st.sidebar.selectbox("Date Range", ["All", "Last 7 days", "Last 2 months"])

    contacts_df = load_contacts()
    selected_name = st.sidebar.selectbox("📇 Search by Saved Contact", [""] + sorted(contacts_df["Name"].tolist()))
    if selected_name:
        contact_row = contacts_df[contacts_df["Name"] == selected_name]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in contact_row and pd.notna(contact_row.iloc[0][col]):
                nums.append(str(contact_row.iloc[0][col]))
        df = normalize_for_matching(df, nums)

    # ---- APPLY FILTERS ----
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
        norm_contact = normalize_number(contact_filter)
        df_filtered = normalize_for_matching(df_filtered, [norm_contact])
    df_filtered = filter_by_date(df_filtered, date_filter)

    # ---- DISPLAY DATA ----
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # ---- WHATSAPP MESSAGE GENERATION ----
    st.subheader("📤 Send Listings via WhatsApp")
    phone_input = st.text_input("Enter WhatsApp number (03xxxxxxxxx)")
    if st.button("Generate WhatsApp Message"):
        if not phone_input.strip():
            st.warning("Please enter a phone number.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            if msg:
                clean_number = normalize_number(phone_input)
                wa_url = f"https://wa.me/92{clean_number.lstrip('0')}?text={st.experimental_urlencode(msg)}"
                st.markdown(f"[👉 Click to Send WhatsApp Message](%s)" % wa_url, unsafe_allow_html=True)
            else:
                st.warning("No valid listings to include in message.")

    # ---- ADD CONTACT ----
    st.subheader("➕ Add New Contact")
    with st.form("add_contact_form"):
        name = st.text_input("Contact Name", key="name")
        c1 = st.text_input("Contact 1", key="c1")
        c2 = st.text_input("Contact 2 (Optional)", key="c2")
        c3 = st.text_input("Contact 3 (Optional)", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if not name or not c1:
                st.error("Name and Contact 1 are required.")
            else:
                save_contact(name, c1, c2, c3)
                st.success(f"Contact saved: {name}")

if __name__ == "__main__":
    main()