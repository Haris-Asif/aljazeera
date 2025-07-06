import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
from urllib.parse import quote

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
REQUIRED_COLUMNS = ["Sector", "Plot No#", "Plot Size", "Demand/Price", "Street#"]
DISPLAY_COLUMNS = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
CONTACTS_CSV = "contacts.csv"

def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def normalize_number(number):
    return re.sub(r"[^0-9]", "", str(number))

def load_contacts():
    try:
        return pd.read_csv(CONTACTS_CSV)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    return f in c if "/" not in f else f == c

def filter_by_date(df, date_range):
    if date_range == "All":
        return df
    today = datetime.today()
    if date_range == "Last 7 Days":
        start_date = today - timedelta(days=7)
    else:
        start_date = today - timedelta(days=60)

    def is_within_range(val):
        try:
            parsed = pd.to_datetime(str(val).split(",")[0].strip())
            return parsed >= start_date
        except:
            return False

    return df[df["Date"].apply(is_within_range)]

def clean_and_dedupe_for_whatsapp(df):
    df = df.copy()

    # Filter out incomplete rows
    def is_valid(row):
        if any(pd.isna(row[col]) or str(row[col]).strip() == "" for col in REQUIRED_COLUMNS):
            return False
        sector = str(row["Sector"]).strip().upper()
        if not re.match(r"^[A-Z]-\d+/\d+$", sector):
            return False
        if sector.startswith("I-15/") and str(row["Street#"]).strip() == "":
            return False
        return True

    df = df[df.apply(is_valid, axis=1)]

    # Deduplicate
    def dedupe_key(row):
        key = (row["Sector"], row["Plot No#"], row["Plot Size"], row["Demand/Price"])
        if str(row["Sector"]).startswith("I-15/"):
            key += (row["Street#"],)
        return key

    df["dedupe_key"] = df.apply(dedupe_key, axis=1)
    df = df.drop_duplicates(subset=["dedupe_key"]).drop(columns=["dedupe_key"])
    return df

def generate_whatsapp_message(df):
    grouped = {}
    for _, row in df.iterrows():
        sector = str(row["Sector"])
        plot_size = str(row["Plot Size"])
        plot_no = str(row["Plot No#"])
        demand = str(row["Demand/Price"])
        street = str(row["Street#"])

        group_key = f"{sector}__{plot_size}"
        if group_key not in grouped:
            grouped[group_key] = []
        grouped[group_key].append((plot_no, plot_size, demand, street, sector))

    msg = ""
    for group_key in sorted(grouped.keys()):
        sector, size = group_key.split("__")
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st, sec in grouped[group_key]:
            if "I-15" in sec:
                msg += f"St: {st} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

def add_contact_ui():
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        name = st.text_input("Name", "")
        c1 = st.text_input("Contact 1", "")
        c2 = st.text_input("Contact 2", "")
        c3 = st.text_input("Contact 3", "")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1:
                contacts = load_contacts()
                new_row = pd.DataFrame([[name, c1, c2, c3]], columns=contacts.columns)
                contacts = pd.concat([contacts, new_row], ignore_index=True)
                contacts.to_csv(CONTACTS_CSV, index=False)
                st.success("Contact saved.")
            else:
                st.error("Name and Contact 1 are required.")

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    df = df.fillna("")

    contacts_df = load_contacts()

    with st.sidebar:
        st.subheader("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        plot_no_filter = st.text_input("Plot No#")
        street_filter = st.text_input("Street#")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 2 Months"])
        number_input = st.text_input("WhatsApp Number (03xxxxxxxxx)")

        contact_names = [""] + contacts_df["Name"].dropna().tolist()
        selected_contact = st.selectbox("📇 Select Saved Contact", contact_names)

    df_filtered = df.copy()

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].astype(str).str.contains(street_filter, case=False, na=False)]

    df_filtered = filter_by_date(df_filtered, date_filter)

    if selected_contact:
        contact_row = contacts_df[contacts_df["Name"] == selected_contact]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            val = contact_row[col].values[0] if col in contact_row else ""
            if pd.notna(val) and str(val).strip():
                nums.append(normalize_number(val))
        pattern = "|".join(nums)
        df_filtered = df_filtered[df_filtered["Contact"].apply(lambda x: any(n in normalize_number(x) for n in nums))]

    # Show full filtered data
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[DISPLAY_COLUMNS], use_container_width=True)

    # WhatsApp Message
    if st.button("📤 Generate WhatsApp Message"):
        final_df = clean_and_dedupe_for_whatsapp(df_filtered)
        if final_df.empty:
            st.warning("No valid listings to generate message.")
        else:
            msg = generate_whatsapp_message(final_df)
            st.text_area("📄 Message", msg, height=300)
            if number_input:
                clean_number = normalize_number(number_input)
                if clean_number.startswith("0"):
                    clean_number = clean_number[1:]
                wa_url = f"https://wa.me/92{clean_number}?text={quote(msg)}"
                st.markdown(f"[📲 Send WhatsApp Message](%s)" % wa_url, unsafe_allow_html=True)

    # Add Contact
    with st.expander("📒 Manage Contacts"):
        add_contact_ui()

if __name__ == "__main__":
    main()