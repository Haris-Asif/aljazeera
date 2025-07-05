import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import re
import urllib.parse

# Streamlit UI settings
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Google Sheet details
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
REQUIRED_COLUMNS = ["Sector", "Plot No#", "Plot Size", "Demand/Price", "Street#"]

# Load Google Sheet data
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(credentials)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    # Clean data: remove incomplete and invalid listings
    df = df.fillna("")
    df = df[df["Sector"].str.contains(r"I-\d+/\d+", na=False, regex=True)]
    for col in ["Sector", "Plot Size", "Plot No#", "Demand/Price"]:
        df = df[df[col].astype(str).str.strip() != ""]

    # Street# is mandatory only for I-15 sub-sectors
    df = df[~((df["Sector"].isin(["I-15/1", "I-15/2", "I-15/3", "I-15/4"])) & (df["Street#"].astype(str).str.strip() == ""))]

    return df

# Sector filtering logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = cell_val.replace(" ", "").upper()
    return f in c if "/" not in f else f == c

# WhatsApp message generator (deduplicates properly)
def generate_whatsapp_message(df):
    grouped = {}
    seen = set()

    for _, row in df.iterrows():
        sector = row["Sector"]
        plot_size = row["Plot Size"]
        plot_no = row["Plot No#"]
        price = row["Demand/Price"]
        street = row.get("Street#", "")

        if sector in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"]:
            dedup_key = (sector, plot_size, plot_no, price, street)
        else:
            dedup_key = (sector, plot_size, plot_no, price)

        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        group_key = f"{sector}__{plot_size}"
        grouped.setdefault(group_key, []).append((plot_no, plot_size, price, street, sector))

    msg = ""
    for key in sorted(grouped.keys()):
        sector, size = key.split("__")
        msg += f"*Available Options in {sector} Size: {size}*\n"
        for p, s, d, st_, sec in grouped[key]:
            if "I-15" in sec:
                msg += f"St: {st_} | P: {p} | S: {s} | D: {d}\n"
            else:
                msg += f"P: {p} | S: {s} | D: {d}\n"
        msg += "\n"

    return msg.strip()

# Load contacts from contacts.csv
def load_contacts():
    try:
        return pd.read_csv("contacts.csv").fillna("")
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

# Save new contact
def save_contact(name, c1, c2, c3):
    contacts = load_contacts()
    new_row = pd.DataFrame([{"Name": name, "Contact1": c1, "Contact2": c2, "Contact3": c3}])
    updated = pd.concat([contacts, new_row], ignore_index=True)
    updated.to_csv("contacts.csv", index=False)

# Main app
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    df = load_data_from_gsheet()
    df = df.fillna("")

    # 🧠 Sidebar Filters
    with st.sidebar:
        st.subheader("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14 or I-14/1)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")

        # Contact selection
        contacts_df = load_contacts()
        contact_names = contacts_df["Name"].tolist()
        selected_contact = st.selectbox("Search Listings by Saved Contact", [""] + contact_names)
        entered_number = st.text_input("Or enter WhatsApp number (03xxxxxxxxx)")

        # Date filter
        date_filter = st.selectbox("Listings Date Filter", ["All", "Last 7 days", "Last 15 days", "Last 1 month", "Last 2 months"])

    # 🔍 Filtering
    df_filtered = df.copy()

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]

    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]

    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]

    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]

    if selected_contact:
        contact_row = contacts_df[contacts_df["Name"] == selected_contact]
        nums = []
        if not contact_row.empty:
            for col in ["Contact1", "Contact2", "Contact3"]:
                val = str(contact_row.iloc[0][col]).strip()
                if val:
                    nums.append(val)
        if nums:
            pattern = "|".join(map(re.escape, nums))
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).str.contains(pattern, case=False, na=False)]

    if date_filter != "All":
        date_mapping = {
            "Last 7 days": 7,
            "Last 15 days": 15,
            "Last 1 month": 30,
            "Last 2 months": 60,
        }
        days = date_mapping[date_filter]
        df_filtered["ParsedDate"] = pd.to_datetime(df_filtered["Date"], errors="coerce")
        recent_date = datetime.now() - timedelta(days=days)
        df_filtered = df_filtered[df_filtered["ParsedDate"] >= recent_date]

    # Display filtered listings
    st.subheader("📋 Filtered Listings")
    display_cols = ["Date", "Sector", "Street#", "Plot No#", "Plot Size", "Demand/Price", "Description/Details", "Contact"]
    st.dataframe(df_filtered[display_cols])

    # 💬 Generate WhatsApp message
    if st.button("📤 Generate WhatsApp Message"):
        if df_filtered.empty:
            st.warning("No listings to generate message.")
        else:
            msg = generate_whatsapp_message(df_filtered)
            st.text_area("📄 Message Preview", msg, height=300)

            if entered_number.startswith("03"):
                international_number = "92" + entered_number[1:]
                encoded = urllib.parse.quote(msg)
                url = f"https://wa.me/{international_number}?text={encoded}"
                st.markdown(f"[Click to Send via WhatsApp 📲]({url})", unsafe_allow_html=True)

    # ➕ Add new contact
    st.subheader("➕ Add New Contact")
    with st.form("contact_form"):
        name = st.text_input("Name (required)")
        c1 = st.text_input("Contact 1 (required)")
        c2 = st.text_input("Contact 2 (optional)")
        c3 = st.text_input("Contact 3 (optional)")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1:
                save_contact(name, c1, c2, c3)
                st.success(f"Contact {name} saved!")
            else:
                st.warning("Please fill at least Name and Contact 1")

if __name__ == "__main__":
    main()