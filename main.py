import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import urllib.parse
import datetime
import os

st.set_page_config("🏡 Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_CSV = "contacts.csv"

def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def load_contacts():
    if os.path.exists(CONTACTS_CSV):
        return pd.read_csv(CONTACTS_CSV)
    else:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

def save_contact(name, c1, c2, c3):
    contacts = load_contacts()
    new_row = pd.DataFrame([[name, c1, c2, c3]], columns=["Name", "Contact1", "Contact2", "Contact3"])
    updated = pd.concat([contacts, new_row], ignore_index=True)
    updated.to_csv(CONTACTS_CSV, index=False)

def normalize_plot_size(size):
    if isinstance(size, str):
        return re.sub(r"[+xX*]", "x", size.strip())
    return size

def is_valid_sector(sector):
    if not isinstance(sector, str):
        return False
    return bool(re.match(r"^[A-Z]+-\d+/\d+$", sector.strip().upper()))

def filter_by_date(df, date_range):
    if date_range == "All":
        return df
    days = {"Last 7 days": 7, "Last 30 days": 30, "Last 2 months": 60}.get(date_range, 0)
    today = datetime.datetime.today()
    filtered = []
    for _, row in df.iterrows():
        date_str = str(row.get("Date", "")).split(",")[0].strip()
        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            if (today - date_obj).days <= days:
                filtered.append(True)
            else:
                filtered.append(False)
        except:
            filtered.append(False)
    return df[filtered]

def deduplicate_for_whatsapp(df):
    def key(row):
        sector = str(row.get("Sector", ""))
        plot = str(row.get("Plot No#", ""))
        size = str(row.get("Plot Size", ""))
        price = str(row.get("Demand/Price", ""))
        street = str(row.get("Street#", ""))
        if sector in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]:
            return (sector, plot, size, street, price)
        else:
            return (sector, plot, size, price)
    seen = set()
    unique_rows = []
    for _, row in df.iterrows():
        k = key(row)
        if k not in seen:
            seen.add(k)
            unique_rows.append(row)
    return pd.DataFrame(unique_rows)

def generate_whatsapp_message(df):
    df = deduplicate_for_whatsapp(df)
    grouped = {}
    for _, row in df.iterrows():
        sector = row.get("Sector", "")
        size = row.get("Plot Size", "")
        plot = row.get("Plot No#", "")
        price = row.get("Demand/Price", "")
        street = row.get("Street#", "")

        if not all([sector, size, plot, price]):
            continue
        if sector in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] and not street:
            continue

        key = f"{sector}__{size}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((plot, size, price, street, sector))

    msg = ""
    for key in sorted(grouped.keys()):
        sector, size = key.split("__")
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, _ in grouped[key]:
            if "I-15/" in sector:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"
    return msg.strip()

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    df = load_data_from_gsheet()
    df = df.fillna("")
    df["Plot Size"] = df["Plot Size"].apply(normalize_plot_size)

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        date_range = st.selectbox("Date Range", ["All", "Last 7 days", "Last 30 days", "Last 2 months"])

        contacts = load_contacts()
        contact_names = [""] + contacts["Name"].tolist()
        selected_contact = st.selectbox("Search by Saved Contact", contact_names)

        contact_filter = ""
        if selected_contact:
            contact_row = contacts[contacts["Name"] == selected_contact]
            if not contact_row.empty:
                nums = [str(contact_row[col].values[0]) for col in ["Contact1", "Contact2", "Contact3"] if col in contact_row.columns and pd.notna(contact_row[col].values[0])]
                if nums:
                    pattern = "|".join(map(re.escape, nums))
                    contact_filter = pattern

    df_filtered = df.copy()
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].astype(str).str.contains(sector_filter.strip(), case=False, na=False)]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].astype(str).str.contains(plot_size_filter.strip(), case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].astype(str).str.contains(street_filter.strip(), case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter.strip(), case=False, na=False)]
    if contact_filter:
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(contact_filter, case=False, na=False)]

    df_filtered = filter_by_date(df_filtered, date_range)
    df_filtered = df_filtered.drop_duplicates()

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered[["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]])

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    msg = ""
    if st.button("Generate WhatsApp Message"):
        msg = generate_whatsapp_message(df_filtered)
        if msg:
            st.success("Message generated successfully.")
            st.text_area("WhatsApp Message", msg, height=300)

    phone_number = st.text_input("Enter WhatsApp Number (e.g., 03XXXXXXXXX):")
    if phone_number and msg:
        number = phone_number.strip().replace(" ", "").replace("-", "")
        if number.startswith("03"):
            number = "92" + number[1:]
        link = f"https://wa.me/{number}?text={urllib.parse.quote(msg)}"
        st.markdown(f"[📨 Send WhatsApp Message]({link})", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("➕ Add New Contact")
    name = st.text_input("Name")
    c1 = st.text_input("Contact 1")
    c2 = st.text_input("Contact 2 (Optional)")
    c3 = st.text_input("Contact 3 (Optional)")
    if st.button("Save Contact"):
        if name and c1:
            save_contact(name, c1, c2, c3)
            st.success(f"Saved contact {name}")
        else:
            st.error("Name and Contact 1 are required.")

if __name__ == "__main__":
    main()