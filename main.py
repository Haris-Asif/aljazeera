import streamlit as st
import pandas as pd
import gspread
import re
import difflib
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Constants
SPREADSHEET_NAME = "Al-Jazeera"
PLOTS_SHEET = "Plots"
CONTACTS_SHEET = "Contacts"

# Streamlit setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Helper functions
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text):
    text = str(text or "")
    parts = re.split(r"[,\s]+", text)
    return [clean_number(p) for p in parts if clean_number(p)]

def parse_price(price_str):
    try:
        price_str = str(price_str).lower().replace(",", "").replace("cr", "00").replace("crore", "00")
        numbers = re.findall(r"\d+\.?\d*", price_str)
        return float(numbers[0]) if numbers else None
    except:
        return None

def feature_matches(row_features, search_term):
    if not search_term:
        return True
    row_features = str(row_features or "").lower().split(",")
    row_features = [f.strip() for f in row_features if f.strip()]
    matches = difflib.get_close_matches(search_term.lower(), row_features, n=1, cutoff=0.7)
    return bool(matches)

def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def load_plot_data():
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
    df = pd.DataFrame(sheet.get_all_records())
    df["SheetRowNum"] = [i + 2 for i in range(len(df))]
    return df

def load_contacts():
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    return pd.DataFrame(sheet.get_all_records())

def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.now() - timedelta(days=days_map.get(label, 0))
    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            return None
    df["ParsedDate"] = df["Timestamp"].apply(try_parse)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

def build_name_map(df):
    contact_to_name = {}
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name")).strip()
        contacts = extract_numbers(row.get("Extracted Contact"))
        for c in contacts:
            if c and c not in contact_to_name:
                contact_to_name[c] = name
    name_groups = {}
    for c, name in contact_to_name.items():
        name_groups.setdefault(name, set()).add(c)
    merged = {}
    for name, numbers in name_groups.items():
        for c in numbers:
            merged[c] = name
    name_set = {}
    for _, row in df.iterrows():
        numbers = extract_numbers(row.get("Extracted Contact"))
        for c in numbers:
            if c in merged:
                name_set[merged[c]] = True
    return sorted(name_set.keys()), merged

def sector_matches(f, c):
    if not f:
        return True
    f = f.replace(" ", "").upper()
    c = str(c).replace(" ", "").upper()
    return f in c if "/" not in f else f == c

def safe_dataframe(df):
    try:
        df = df.copy()
        df = df.drop(columns=["ParsedDate"], errors="ignore")
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
        return df
    except Exception as e:
        st.error(f"⚠️ Error displaying table: {e}")
        return pd.DataFrame()

def create_whatsapp_link(contact, message):
    contact = clean_number(contact)
    if len(contact) == 10:
        contact = "92" + contact  # Assume it's a Pakistani number missing the +92
    elif contact.startswith("03") and len(contact) == 11:
        contact = "92" + contact[1:]
    return f"https://wa.me/{contact}?text={message.replace(' ', '%20')}"

# --- Streamlit App ---
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_plot_data().fillna("")
    contacts_df = load_contacts()

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street No")
        plot_no_filter = st.text_input("Plot No")
        contact_filter = st.text_input("Phone Number (03xxxxxxxxx)")
        price_from = st.number_input("Price From (in Lacs)", min_value=0.0, value=0.0, step=1.0)
        price_to = st.number_input("Price To (in Lacs)", min_value=0.0, value=1000.0, step=1.0)
        feature_filter = st.text_input("Features (e.g. corner, main road, etc.)")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        dealer_names, contact_to_name = build_name_map(df)
        selected_dealer = st.selectbox("Dealer Name (by contact)", [""] + dealer_names)

        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names)

    df_filtered = df.copy()

    if selected_dealer:
        selected_contacts = [c for c, name in contact_to_name.items() if name == selected_dealer]
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(c in clean_number(x) for c in selected_contacts))]

    if selected_saved:
        row = contacts_df[contacts_df["Name"] == selected_saved]
        selected_contacts = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            selected_contacts.extend(extract_numbers(row.get(col, "")))
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(n in clean_number(x) for n in selected_contacts))]

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street No"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No"].str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        cnum = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Extracted Contact"].astype(str).apply(
            lambda x: any(cnum == clean_number(p) for p in x.split(",")))]

    # Price filtering
    df_filtered["ParsedPrice"] = df_filtered["Demand"].apply(parse_price)
    df_filtered = df_filtered[df_filtered["ParsedPrice"].notnull()]
    df_filtered = df_filtered[(df_filtered["ParsedPrice"] >= price_from) & (df_filtered["ParsedPrice"] <= price_to)]

    # Feature filter
    if feature_filter:
        df_filtered = df_filtered[df_filtered["Features"].apply(lambda x: feature_matches(x, feature_filter))]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(safe_dataframe(df_filtered))

    # WhatsApp message generator
    st.subheader("📱 WhatsApp Message Generator")
    contact_input = st.text_input("Phone number (03xxxxxxxxx or with country code)")
    message_input = st.text_area("Message")

    if st.button("Generate WhatsApp Link"):
        if contact_input and message_input:
            url = create_whatsapp_link(contact_input, message_input)
            st.markdown(f"[Click here to send message via WhatsApp]({url})")
        else:
            st.warning("Please enter both phone number and message.")

    # Add new contact form
    st.subheader("➕ Add Contact to Saved List")
    with st.form("add_contact_form"):
        new_name = st.text_input("Name")
        new_contact1 = st.text_input("Contact 1")
        new_contact2 = st.text_input("Contact 2")
        new_contact3 = st.text_input("Contact 3")
        submitted = st.form_submit_button("Add to Contacts")
        if submitted and new_name and new_contact1:
            sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
            sheet.append_row([new_name, new_contact1, new_contact2, new_contact3])
            st.success(f"Contact '{new_name}' added successfully!")

if __name__ == "__main__":
    main()