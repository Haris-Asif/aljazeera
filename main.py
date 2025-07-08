import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

SPREADSHEET_NAME = "RealEstateTool"
WORKSHEET_NAME = "Sheet1"
CONTACTS_CSV = "contacts.csv"

# Load data from Google Sheet
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data).fillna("")

# Helper functions
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    return f in c if "/" not in f else f == c

def parse_date(val):
    try:
        return datetime.strptime(val.strip(), "%Y-%m-%d, %H:%M")
    except:
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d")
        except:
            return None

def filter_by_date(df, days_label):
    if days_label == "All":
        return df
    today = datetime.today()
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = today - timedelta(days=days_map.get(days_label, 0))
    df["ParsedDate"] = df["Date"].apply(parse_date)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

# Load contacts
def load_contacts():
    try:
        return pd.read_csv(CONTACTS_CSV)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

# Format WhatsApp message, split by sector+size if long
def generate_whatsapp_messages(df):
    filtered = []

    for _, row in df.iterrows():
        sector = row.get("Sector", "").strip()
        plot_no = row.get("Plot No#", "").strip()
        plot_size = row.get("Plot Size", "").strip()
        demand = row.get("Demand/Price", "").strip()
        street = row.get("Street#", "").strip()

        if not re.match(r"^[A-Z]-\d+/\d+$", sector):
            continue
        if not (sector and plot_no and plot_size and demand):
            continue
        if sector in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] and not street:
            continue

        filtered.append({
            "Sector": sector,
            "Street#": street,
            "Plot No#": plot_no,
            "Plot Size": plot_size,
            "Demand/Price": demand
        })

    # Remove duplicates
    seen = set()
    unique = []
    for row in filtered:
        key = (
            row["Sector"],
            row["Plot No#"],
            row["Plot Size"],
            row["Demand/Price"],
            row["Street#"] if row["Sector"] in ["I-15/1", "I-15/2", "I-15/3", "I-15/4"] else ""
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)

    # Group by Sector + Plot Size
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    messages = []
    current_msg = ""
    for (sector, size), rows in sorted(grouped.items()):
        header = f"*Available Options in {sector} Size: {size}*\n"
        body = ""
        for row in rows:
            if sector.startswith("I-15/"):
                body += f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                body += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
        section = header + body + "\n"

        if len(current_msg + section) > 3900:
            messages.append(current_msg.strip())
            current_msg = section
        else:
            current_msg += section

    if current_msg:
        messages.append(current_msg.strip())

    return messages

# Streamlit UI
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    df = load_data_from_gsheet()
    contacts_df = load_contacts()

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        st.markdown("---")
        saved_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_name = st.selectbox("📇 Saved Contacts", saved_names)

    df_filtered = df.copy()

    # Apply contact filter from saved contact selection
    if selected_name:
        contact_row = contacts_df[contacts_df["Name"] == selected_name]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in contact_row and pd.notna(contact_row[col].values[0]):
                num = clean_number(contact_row[col].values[0])
                if num:
                    nums.append(num)

        if nums:
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(
                lambda x: any(n in clean_number(x) for n in nums)
            )]

    # Other filters
    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        c = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: c in clean_number(x))]

    df_filtered = filter_by_date(df_filtered, date_filter)

    # Show results
    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    wa_number_input = st.text_input("📱 Enter WhatsApp Number (03xxxxxxxxx)")
    wa_contact_name = st.selectbox("📇 Or select saved contact to send message", saved_names)

    wa_number = None
    if wa_contact_name:
        row = contacts_df[contacts_df["Name"] == wa_contact_name]
        if not row.empty:
            wa_number = clean_number(row["Contact1"].values[0])
    elif wa_number_input:
        wa_number = clean_number(wa_number_input)

    if st.button("Generate WhatsApp Message"):
        if not wa_number or not wa_number.startswith("3"):
            st.error("❌ Enter a valid number or select a valid saved contact.")
        else:
            messages = generate_whatsapp_messages(df_filtered)
            if not messages:
                st.warning("⚠️ No valid listings to include.")
            else:
                st.success("✅ Message(s) Ready:")
                for i, msg in enumerate(messages, 1):
                    link = f"https://wa.me/92{wa_number}?text={msg.replace(' ', '%20').replace('\n', '%0A')}"
                    st.markdown(f"[📩 Send Message {i} on WhatsApp]({link})", unsafe_allow_html=True)

    # Add new contact
    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact_form"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1*", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        save = st.form_submit_button("Save Contact")
        if save:
            if name and c1:
                new_row = pd.DataFrame([[name, c1, c2, c3]], columns=["Name", "Contact1", "Contact2", "Contact3"])
                updated = pd.concat([contacts_df, new_row], ignore_index=True)
                updated.to_csv(CONTACTS_CSV, index=False)
                st.success(f"✅ Contact '{name}' saved.")
            else:
                st.warning("❗ Name and Contact1 are required.")

if __name__ == "__main__":
    main()