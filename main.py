import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"
CONTACTS_CSV = "contacts.csv"

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Load Google Sheet data (ignores empty rows)
def load_data_from_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

    all_data = sheet.get_all_values()

    header_row = None
    for i, row in enumerate(all_data):
        if any(cell.strip() for cell in row):
            header_row = i
            break

    if header_row is None:
        return pd.DataFrame()

    headers = all_data[header_row]
    data_rows = all_data[header_row + 1:]
    cleaned_data = [row for row in data_rows if any(cell.strip() for cell in row)]

    for row in cleaned_data:
        while len(row) < len(headers):
            row.append("")
        if len(row) > len(headers):
            row[:] = row[:len(headers)]

    df = pd.DataFrame(cleaned_data, columns=headers)
    df["SheetRowNum"] = [header_row + 2 + i for i in range(len(cleaned_data))]
    return df

# Sector filter logic
def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

# Phone cleaner
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

# WhatsApp message builder
def generate_whatsapp_messages(df):
    filtered = []
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No#", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand/Price", "")).strip()
        street = str(row.get("Street#", "")).strip()

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

    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    def extract_plot_number(val):
        try:
            return int(re.search(r"\d+", str(val)).group())
        except:
            return float("inf")

    message_chunks = []
    current_msg = ""

    for (sector, size), items in sorted(grouped.items()):
        sorted_items = sorted(items, key=lambda x: extract_plot_number(x["Plot No#"]))
        header = f"*Available Options in {sector} Size: {size}*\n"
        lines = []
        for row in sorted_items:
            if "I-15/" in sector:
                line = f"St: {row['Street#']} | P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}"
            else:
                line = f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}"
            lines.append(line)

        block = header + "\n".join(lines) + "\n\n"

        if len(current_msg + block) > 3900:
            message_chunks.append(current_msg.strip())
            current_msg = block
        else:
            current_msg += block

    if current_msg:
        message_chunks.append(current_msg.strip())

    return message_chunks

# Date filter
def filter_by_date(df, label):
    if label == "All":
        return df
    today = datetime.today()
    days_map = {
        "Last 7 Days": 7,
        "Last 15 Days": 15,
        "Last 30 Days": 30,
        "Last 2 Months": 60
    }
    days = days_map.get(label, 0)
    cutoff = today - timedelta(days=days)

    def parse_date(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d, %H:%M")
        except:
            try:
                return datetime.strptime(val.strip(), "%Y-%m-%d")
            except:
                return None

    df["ParsedDate"] = df["Date"].apply(parse_date)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

# Load contacts
def load_contacts():
    try:
        return pd.read_csv(CONTACTS_CSV)
    except:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])

# Main App
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    df = df.fillna("")
    contacts_df = load_contacts()

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector (e.g. I-14/1 or I-14)")
        plot_size_filter = st.text_input("Plot Size (e.g. 25x50)")
        street_filter = st.text_input("Street#")
        plot_no_filter = st.text_input("Plot No#")
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        dealer_filter = ""
        dealer_names = sorted(df["Dealer name"].dropna().unique()) if "Dealer name" in df.columns else []
        if dealer_names:
            dealer_filter = st.selectbox("Dealer name", [""] + list(dealer_names))

        st.markdown("---")
        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_name = st.selectbox("📇 Saved Contacts", contact_names)

    df_filtered = df.copy()

    if selected_name:
        contact_row = contacts_df[contacts_df["Name"] == selected_name]
        nums = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in contact_row.columns:
                val = contact_row[col].values[0]
                if pd.notna(val) and str(val).strip():
                    nums.append(clean_number(val))
        if nums:
            df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(
                lambda x: any(n in clean_number(x) for n in nums)
            )]

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street#"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No#"].astype(str).str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        cnum = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Contact"].astype(str).apply(lambda x: cnum in clean_number(x))]
    if dealer_filter and "Dealer name" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["Dealer name"].astype(str).str.contains(dealer_filter, case=False, na=False)]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("🗑️ Delete Listings from Google Sheet")

    if not df_filtered.empty:
        df_filtered_reset = df_filtered.reset_index(drop=True)
        selected_indices = st.multiselect(
            "Select rows to delete",
            df_filtered_reset.index,
            format_func=lambda i: f"{df_filtered_reset.at[i, 'Sector']} | Plot#: {df_filtered_reset.at[i, 'Plot No#']}"
        )

        if st.button("❌ Delete Selected Rows"):
            if selected_indices:
                try:
                    if "SheetRowNum" not in df_filtered_reset.columns:
                        st.error("Missing SheetRowNum. Cannot delete from sheet.")
                        return

                    sheet_row_nums = df_filtered_reset.loc[selected_indices, "SheetRowNum"].astype(int).tolist()
                    st.write("Deleting rows from sheet (row numbers):", sheet_row_nums)

                    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                    creds_dict = st.secrets["gcp_service_account"]
                    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                    client = gspread.authorize(creds)
                    sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

                    for row_num in sorted(sheet_row_nums, reverse=True):
                        sheet.delete_rows(row_num)

                    st.success(f"✅ Deleted {len(sheet_row_nums)} row(s) from Google Sheet.")
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Failed to delete rows: {e}")
            else:
                st.warning("⚠️ No rows selected.")

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")
    number = st.text_input("Enter WhatsApp Number (e.g. 03xxxxxxxxx)")
    if st.button("Generate WhatsApp Message"):
        if not number or not number.strip().startswith("03"):
            st.error("❌ Please enter a valid number starting with 03...")
        else:
            chunks = generate_whatsapp_messages(df_filtered)
            if not chunks:
                st.warning("⚠️ No valid listings to include.")
            else:
                wa_number = "92" + clean_number(number).lstrip("0")
                for i, msg in enumerate(chunks):
                    encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                    link = f"https://wa.me/{wa_number}?text={encoded}"
                    st.markdown(f"[📩 Send Message {i+1}]({link})", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("➕ Add New Contact")
    with st.form("add_contact"):
        name = st.text_input("Name*", key="name")
        c1 = st.text_input("Contact1*", key="c1")
        c2 = st.text_input("Contact2", key="c2")
        c3 = st.text_input("Contact3", key="c3")
        submitted = st.form_submit_button("Save Contact")
        if submitted:
            if name and c1:
                new_row = pd.DataFrame([[name, c1, c2, c3]], columns=["Name", "Contact1", "Contact2", "Contact3"])
                updated_df = pd.concat([contacts_df, new_row], ignore_index=True)
                updated_df.to_csv(CONTACTS_CSV, index=False)
                st.success(f"Contact '{name}' saved.")
            else:
                st.warning("Name and Contact1 are required.")

if __name__ == "__main__":
    main()
