import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import re
import urllib.parse

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_FILE = "contacts.csv"

@st.cache_data(show_spinner=False)
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def load_contacts():
    try:
        return pd.read_csv(CONTACTS_FILE)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def save_contact(name, c1, c2, c3):
    df = load_contacts()
    df = pd.concat([df, pd.DataFrame([{"Name": name, "Contact1": c1, "Contact2": c2, "Contact3": c3}])], ignore_index=True)
    df.to_csv(CONTACTS_FILE, index=False)

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = cell_val.replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

def filter_by_date(df, days_option):
    if days_option == "All":
        return df
    days_map = {"Last 7 days": 7, "Last 15 days": 15, "Last 30 days": 30, "Last 2 months": 60}
    days = days_map.get(days_option, 0)
    cutoff = datetime.now() - timedelta(days=days)
    
    def parse_date(d):
        try:
            return datetime.strptime(d.strip(), "%Y-%m-%d , %H:%M")
        except:
            try:
                return datetime.strptime(d.strip(), "%Y-%m-%d")
            except:
                return None

    df["ParsedDate"] = df["Date"].apply(parse_date)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

def generate_whatsapp_message(df):
    def normalize_size(val):
        val = str(val).replace("+", "x").replace("*", "x").replace("X", "x")
        return val.strip()

    df["NormalizedSize"] = df["Plot Size"].apply(normalize_size)
    df["SectorFormatted"] = df["Sector"]

    # Filter out listings with missing required values for messaging
    required_fields = ["Sector", "Plot Size", "Plot No#", "Demand/Price"]
    def is_valid(row):
        if any(pd.isna(row[col]) or str(row[col]).strip() == "" for col in required_fields):
            return False
        sec = str(row["Sector"])
        if re.match(r"I-15/[1-4]", sec):
            return pd.notna(row["Street#"]) and str(row["Street#"]).strip() != ""
        return True

    df_valid = df[df.apply(is_valid, axis=1)]

    # Deduplicate
    df_valid = df_valid.drop_duplicates(subset=["Sector", "Plot Size", "Plot No#", "Street#", "Demand/Price"])

    grouped = df_valid.groupby(["SectorFormatted", "NormalizedSize"])
    msg = ""
    for (sector, size), group in grouped:
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for _, row in group.iterrows():
            line = ""
            if re.match(r"I-15/[1-4]", str(row["Sector"])):
                line += f"St: {row['Street#']} | "
            line += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            msg += line
        msg += "\n"
    return msg.strip()

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    df = df.fillna("")

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14, I-15/3)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_range = st.selectbox("Date Filter", ["All", "Last 7 days", "Last 15 days", "Last 30 days", "Last 2 months"])
        
        st.markdown("---")
        contacts_df = load_contacts()
        contact_names = [""] + contacts_df["Name"].tolist()
        selected_name = st.selectbox("📇 Saved Contacts", contact_names)
        if selected_name:
            contact_row = contacts_df[contacts_df["Name"] == selected_name]
            nums = [str(contact_row[col].values[0]) for col in ["Contact1", "Contact2", "Contact3"]
                    if col in contact_row.columns and pd.notna(contact_row[col].values[0]) and str(contact_row[col].values[0]).strip()]
            if nums:
                pattern = "|".join(map(re.escape, nums))
                df = df[df["Contact"].astype(str).str.contains(pattern, na=False, case=False)]

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
    df_filtered = filter_by_date(df_filtered, date_range