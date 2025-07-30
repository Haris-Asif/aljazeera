import streamlit as st
import pandas as pd
import gspread
import re
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Constants
SPREADSHEET_NAME = "Al Jazeera Real Estate & Developers"
PLOTS_SHEET = "Plots_Sale"
CONTACTS_SHEET = "Contacts"

st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# Clean number
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num))

# Google Sheets
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def load_plot_data():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
    all_data = sheet.get_all_values()
    header_row = next((i for i, row in enumerate(all_data) if any(cell.strip() for cell in row)), None)
    if header_row is None:
        return pd.DataFrame()
    headers = all_data[header_row]
    data_rows = all_data[header_row + 1:]
    cleaned_data = [row for row in data_rows if any(cell.strip() for cell in row)]
    for row in cleaned_data:
        while len(row) < len(headers):
            row.append("")
        row[:] = row[:len(headers)]
    df = pd.DataFrame(cleaned_data, columns=headers)
    df["SheetRowNum"] = [header_row + 2 + i for i in range(len(df))]
    return df

def load_contacts():
    client = get_gsheet_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    all_data = sheet.get_all_values()
    header_row = next((i for i, row in enumerate(all_data) if any(cell.strip() for cell in row)), None)
    if header_row is None:
        return pd.DataFrame(columns=["Name", "Contact1", "Contact2", "Contact3"])
    headers = all_data[header_row]
    data_rows = all_data[header_row + 1:]
    cleaned_data = [row for row in data_rows if any(cell.strip() for cell in row)]
    for row in cleaned_data:
        while len(row) < len(headers):
            row.append("")
        row[:] = row[:len(headers)]
    return pd.DataFrame(cleaned_data, columns=headers)

# Date filtering
def filter_by_date(df, label):
    if label == "All":
        return df
    today = datetime.today()
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    days = days_map.get(label, 0)
    cutoff = today - timedelta(days=days)

    def parse_date(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            try:
                return datetime.strptime(val.strip(), "%Y-%m-%d")
            except:
                return None

    df["ParsedDate"] = df["Timestamp"].apply(parse_date)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

def sector_matches(filter_val, cell_val):
    if not filter_val:
        return True
    f = filter_val.replace(" ", "").upper()
    c = str(cell_val).replace(" ", "").upper()
    if "/" in f:
        return f == c
    return f in c

def generate_whatsapp_messages(df):
    filtered = []
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand", "")).strip()
        street = str(row.get("Street No", "")).strip()

        if not re.match(r"^[A-Z]-\d+(/\d+)?$", sector):
            continue
        if not (sector and plot_no and plot_size and demand):
            continue
        filtered.append({
            "Sector": sector,
            "Street No": street,
            "Plot No": plot_no,
            "Plot Size": plot_size,
            "Demand": demand
        })

    seen = set()
    unique = []
    for row in filtered:
        key = (
            row["Sector"],
            row["Plot No"],
            row["Plot Size"],
            row["Demand"],
            row["Street No"] if "I-15/" in row["Sector"] else ""
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
        sorted_items = sorted(items, key=lambda x: extract_plot_number(x["Plot No"]))
        header = f"*Available Options in {sector} Size: {size}*\n"
        lines = []
        for row in sorted_items:
            if "I-15/" in sector:
                line = f"St: {row['Street No']} | P: {row['Plot No']} | S: {row['Plot Size']} | D: {row['Demand']}"
            else:
                line = f"P: {row['Plot No']} | S: {row['Plot Size']} | D: {row['Demand']}"
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
        contact_filter = st.text_input("Contact Number")
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        all_names = sorted(set(df["Sender Name"].dropna()) | set(df["Extracted Name"].dropna()))
        selected_name_sidebar = st.selectbox("Filter by Name (Sender or Extracted)", [""] + all_names)

        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_saved_contact = st.selectbox("📇 Saved Contacts (For Filtering)", contact_names)

    df_filtered = df.copy()

    if selected_saved_contact:
        row = contacts_df[contacts_df["Name"] == selected_saved_contact]
        numbers = []
        for col in ["Contact1", "Contact2", "Contact3"]:
            val = row[col].values[0] if col in row.columns else ""
            if val:
                cleaned = clean_number(val)
                if cleaned:
                    numbers.append(cleaned)

        def contact_match(cell_val):
            cell_cleaned = clean_number(cell_val)
            return any(num in cell_cleaned for num in numbers)

        df_filtered = df_filtered[
            df_filtered["Sender Number"].astype(str).apply(contact_match) |
            df_filtered["Extracted Contact"].astype(str).apply(contact_match)
        ]

    if selected_name_sidebar:
        df_filtered = df_filtered[
            df_filtered["Sender Name"].astype(str).str.contains(selected_name_sidebar, case=False, na=False) |
            df_filtered["Extracted Name"].astype(str).str.contains(selected_name_sidebar, case=False, na=False)
        ]

    if sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
    if plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street No"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No"].astype(str).str.contains(plot_no_filter, case=False, na=False)]
    if contact_filter:
        cnum = clean_number(contact_filter)
        df_filtered = df_filtered[
            df_filtered["Sender Number"].astype(str).apply(lambda x: cnum in clean_number(x)) |
            df_filtered["Extracted Contact"].astype(str).apply(lambda x: cnum in clean_number(x))
        ]

    df_filtered = filter_by_date(df_filtered, date_filter)

    st.subheader("📋 Filtered Listings")
    st.dataframe(df_filtered.drop(columns=["ParsedDate"], errors="ignore"))

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    selected_name_whatsapp = st.selectbox("📱 Select Contact to Message", contact_names, key="whatsapp_contact")
    manual_number = st.text_input("Or Enter WhatsApp Number (e.g. 0300xxxxxxx)")

    if st.button("Generate WhatsApp Message"):
        cleaned = ""
        if manual_number:
            cleaned = clean_number(manual_number)
        elif selected_name_whatsapp:
            row = contacts_df[contacts_df["Name"] == selected_name_whatsapp]
            numbers = [clean_number(str(row[c].values[0])) for c in ["Contact1", "Contact2", "Contact3"] if c in row.columns and pd.notna(row[c].values[0])]
            cleaned = numbers[0] if numbers else ""

        if not cleaned:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
            return

        if len(cleaned) == 10 and cleaned.startswith("3"):
            wa_number = "92" + cleaned
        elif len(cleaned) == 11 and cleaned.startswith("03"):
            wa_number = "92" + cleaned[1:]
        elif len(cleaned) == 12 and cleaned.startswith("92"):
            wa_number = cleaned
        else:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
            return

        chunks = generate_whatsapp_messages(df_filtered)
        if not chunks:
            st.warning("⚠️ No valid listings to include.")
        else:
            for i, msg in enumerate(chunks):
                encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                link = f"https://wa.me/{wa_number}?text={encoded}"
                st.markdown(f"[📩 Send Message {i+1}]({link})", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
