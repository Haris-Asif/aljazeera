import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- Google Sheet Info ---
SHEET_NAME = "Al Jazeera Real Estate & Developers"
WORKSHEET_NAME = "Plots_Sale"

# --- Load Google Sheet Data (No Cache) ---
def load_data_from_gsheet():
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# --- Deduplication Helper ---
def deduplicate(df):
    return df.drop_duplicates(subset=["Sector", "Street#", "Plot No#", "Plot Size"])

# --- WhatsApp Message Generator ---
def generate_whatsapp_message(df):
    if df.empty:
        return "No listings to generate."

    df = deduplicate(df)
    df["Sector"] = df["Sector"].astype(str)
    df["Plot Size"] = df["Plot Size"].astype(str)
    df["Street#"] = df["Street#"].astype(str)
    df["Plot No#"] = df["Plot No#"].astype(str)
    df["Demand/Price"] = df["Demand/Price"].astype(str)

    message = ""
    sector_groups = df.groupby("Sector")

    for sector, sector_df in sector_groups:
        size_groups = sector_df.groupby("Plot Size")

        for size, group_df in size_groups:
            group_df = group_df.sort_values(by="Plot No#")
            if "I-15" in sector:
                message += f"*Available Options in {sector} Size: {size}*\n"
                for _, row in group_df.iterrows():
                    st_val = f"St: {row['Street#']} | " if row['Street#'] else ""
                    message += f"{st_val}P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            else:
                message += f"*Available Options in {sector} Size: {size}*\n"
                for _, row in group_df.iterrows():
                    message += f"P: {row['Plot No#']} | S: {row['Plot Size']} | D: {row['Demand/Price']}\n"
            message += "\n"

    return message.strip()

# --- Sidebar Filters ---
def apply_filters(df):
    st.sidebar.markdown("## 🔍 Filter Listings")

    sector_input = st.sidebar.text_input("Sector", placeholder="e.g. I-14/1 or I-14")
    street_input = st.sidebar.text_input("Street#", placeholder="e.g. 27A")
    plot_no_input = st.sidebar.text_input("Plot No#", placeholder="e.g. 107")
    size_input = st.sidebar.text_input("Plot Size", placeholder="e.g. 25x50")
    contact_input = st.sidebar.text_input("Contact", placeholder="Name or number")

    filtered_df = df.copy()

    if sector_input:
        if "/" in sector_input:
            filtered_df = filtered_df[filtered_df["Sector"].str.strip().str.lower() == sector_input.strip().lower()]
        else:
            filtered_df = filtered_df[filtered_df["Sector"].str.contains(sector_input.replace(" ", ""), case=False, na=False)]

    if street_input:
        filtered_df = filtered_df[filtered_df["Street#"].str.contains(street_input.strip(), case=False, na=False)]

    if plot_no_input:
        filtered_df = filtered_df[filtered_df["Plot No#"].astype(str).str.contains(plot_no_input.strip(), case=False, na=False)]

    if size_input:
        filtered_df = filtered_df[filtered_df["Plot Size"].str.contains(size_input.strip(), case=False, na=False)]

    if contact_input:
        filtered_df = filtered_df[filtered_df["Contact"].astype(str).str.contains(contact_input.strip(), case=False, na=False)]

    return filtered_df

# --- Contact Manager ---
def contact_manager(df):
    st.sidebar.markdown("## 📇 Contact Tools")

    add_name = st.sidebar.text_input("➕ Add Contact Name")
    add_number = st.sidebar.text_input("➕ Add Contact Number")
    if st.sidebar.button("Save Contact"):
        st.success(f"Saved contact: {add_name} - {add_number}")

    search_contact = st.sidebar.text_input("🔎 Search by Contact Name")
    if search_contact:
        matched_df = df[df["Contact"].astype(str).str.contains(search_contact.strip(), case=False, na=False)]
        st.write(f"Results for contact '{search_contact}':")
        st.dataframe(matched_df)

# --- Main App ---
def main():
    st.set_page_config(page_title="🏡 Al-Jazeera Real Estate Tool", layout="wide")
    st.title("🏡 Al-Jazeera Real Estate Tool")

    df = load_data_from_gsheet()
    contact_manager(df)

    df_filtered = apply_filters(df)

    st.markdown("### 📋 Filtered Listings")
    st.dataframe(df_filtered)

    if st.button("📲 Generate WhatsApp Message"):
        msg = generate_whatsapp_message(df_filtered)
        st.text_area("📩 WhatsApp Message", msg, height=400)

if __name__ == "__main__":
    main()