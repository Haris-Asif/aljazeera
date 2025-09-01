import streamlit as st
import pandas as pd
import gspread
import re
import difflib
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
import vobject  # For VCF file parsing
import tempfile
import os
import numpy as np

# Constants
SPREADSHEET_NAME = "Al-Jazeera"
PLOTS_SHEET = "Plots"
CONTACTS_SHEET = "Contacts"

# Streamlit setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# --- Helpers ---
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

def get_all_unique_features(df):
    feature_set = set()
    if "Features" in df.columns:
        for f in df["Features"].fillna("").astype(str):
            parts = [p.strip().lower() for p in f.split(",") if p.strip()]
            feature_set.update(parts)
    return sorted(feature_set)

def fuzzy_feature_match(row_features, selected_features):
    row_features = [f.strip().lower() for f in str(row_features or "").split(",")]
    for sel in selected_features:
        match = difflib.get_close_matches(sel.lower(), row_features, n=1, cutoff=0.7)
        if match:
            return True
    return False

# Google Sheets
@st.cache_resource(show_spinner=False)
def get_gsheet_client():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {str(e)}")
        return None

@st.cache_data(ttl=300, show_spinner="Loading plot data...")
def load_plot_data():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if not df.empty:
            df["SheetRowNum"] = [i + 2 for i in range(len(df))]  # Start from row 2
        return df
    except Exception as e:
        st.error(f"Error loading plot data: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner="Loading contacts...")
def load_contacts():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if not df.empty:
            df["SheetRowNum"] = [i + 2 for i in range(len(df))]
        return df
    except Exception as e:
        st.error(f"Error loading contacts: {str(e)}")
        return pd.DataFrame()

def add_contact_to_sheet(contact_data):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        sheet.append_row(contact_data)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error adding contact: {str(e)}")
        return False

def delete_contacts_from_sheet(row_numbers):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        
        valid_rows = [row_num for row_num in row_numbers if row_num > 1]
        if not valid_rows:
            return True
            
        valid_rows.sort(reverse=True)
        
        BATCH_SIZE = 10
        for i in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[i:i+BATCH_SIZE]
            for row_num in batch:
                try:
                    sheet.delete_rows(row_num)
                except Exception as e:
                    st.error(f"Error deleting row {row_num}: {str(e)}")
                    continue
                    
            import time
            time.sleep(1)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error in delete operation: {str(e)}")
        return False

def filter_by_date(df, label):
    if df.empty or label == "All":
        return df
        
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.now() - timedelta(days=days_map.get(label, 0))
    
    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            try:
                return datetime.strptime(val.strip(), "%m/%d/%Y %H:%M:%S")
            except:
                return None
                
    if "Timestamp" in df.columns:
        df["ParsedDate"] = df["Timestamp"].apply(try_parse)
        return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]
    else:
        return df

def build_name_map(df):
    contact_to_name = {}
    if df.empty or "Extracted Name" not in df.columns or "Extracted Contact" not in df.columns:
        return [], {}
        
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name", "")).strip()
        contacts = extract_numbers(row.get("Extracted Contact", ""))
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
        numbers = extract_numbers(row.get("Extracted Contact", ""))
        for c in numbers:
            if c in merged:
                name_set[merged[c]] = True
    
    # Create a list of dealer names with serial numbers
    numbered_dealers = []
    for i, name in enumerate(sorted(name_set.keys()), 1):
        numbered_dealers.append(f"{i}. {name}")
    
    return numbered_dealers, merged

def sector_matches(f, c):
    if not f:
        return True
    f = f.replace(" ", "").upper()
    c = str(c).replace(" ", "").upper()
    return f in c if "/" not in f else f == c

def safe_dataframe(df):
    try:
        df = df.copy()
        df = df.drop(columns=["ParsedDate", "ParsedPrice"], errors="ignore")
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
        return df
    except Exception as e:
        st.error(f"⚠️ Error displaying table: {e}")
        return pd.DataFrame()

# ---------- WhatsApp utilities (split + encode aware) ----------
def _extract_int(val):
    """Extract first integer from a string; used for numeric sorting of Plot No."""
    try:
        m = re.search(r"\d+", str(val))
        return int(m.group()) if m else float("inf")
    except:
        return float("inf")

def _url_encode_for_whatsapp(text: str) -> str:
    """Encode minimally for wa.me URL (matching your existing approach)."""
    # Keep same encoding style you used, so links behave consistently
    return text.replace(" ", "%20").replace("\n", "%0A")

def _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800):
    """
    Given a list of text blocks, accumulate them into chunks that
    satisfy both plain text and encoded URL length limits.
    """
    chunks = []
    current = ""

    for block in blocks:
        candidate = current + block
        # Check both plain and encoded limits
        if len(candidate) > plain_limit or len(_url_encode_for_whatsapp(candidate)) > encoded_limit:
            if current:
                chunks.append(current.rstrip())
                current = ""

            # If single block is still too large, split by lines
            if len(block) > plain_limit or len(_url_encode_for_whatsapp(block)) > encoded_limit:
                lines = block.splitlines(keepends=True)
                small = ""
                for ln in lines:
                    cand2 = small + ln
                    if len(cand2) > plain_limit or len(_url_encode_for_whatsapp(cand2)) > encoded_limit:
                        if small:
                            chunks.append(small.rstrip())
                            small = ""
                        # handle very long single line (rare): hard split
                        if len(ln) > plain_limit or len(_url_encode_for_whatsapp(ln)) > encoded_limit:
                            # split the line at safe slice points
                            seg = ln
                            while seg:
                                # pick a safe slice size
                                step = min(1000, len(seg))
                                piece = seg[:step]
                                while len(_url_encode_for_whatsapp(piece)) > encoded_limit and step > 10:
                                    step -= 10
                                    piece = seg[:step]
                                chunks.append(piece.rstrip())
                                seg = seg[step:]
                        else:
                            small = ln
                    else:
                        small = cand2
                if small:
                    chunks.append(small.rstrip())
            else:
                current = block
        else:
            current = candidate

    if current:
        chunks.append(current.rstrip())

    return chunks

# WhatsApp message generation (sorted by Plot No asc, URL-safe chunking)
def generate_whatsapp_messages(df):
    if df.empty:
        return []
        
    # Build list of eligible rows (keep your intentional filters)
    filtered = []
    for _, row in df.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No", "")).strip()
        size = str(row.get("Plot Size", "")).strip()
        price = str(row.get("Demand", "")).strip()
        street = str(row.get("Street No", "")).strip()

        if not (sector and plot_no and size and price):
            continue
        if "I-15/" in sector and not street:
            continue
        if "series" in plot_no.lower():
            continue

        filtered.append({
            "Sector": sector,
            "Plot No": plot_no,
            "Plot Size": size,
            "Demand": price,
            "Street No": street
        })

    # De-duplicate on (Sector, Plot No, Plot Size, Demand)
    seen = set()
    unique = []
    for row in filtered:
        key = (row["Sector"], row["Plot No"], row["Plot Size"], row["Demand"])
        if key not in seen:
            seen.add(key)
            unique.append(row)

    # Group by (Sector, Plot Size) as before
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    # Build per-group message blocks with sorting by Plot No ascending
    blocks = []
    for (sector, size), listings in grouped.items():
        # Sort primarily by Plot No ascending (numeric-first)
        listings = sorted(
            listings,
            key=lambda x: (_extract_int(x["Plot No"]), str(x["Plot No"]))
        )

        lines = []
        for r in listings:
            if sector.startswith("I-15/"):
                # Keep your I-15 line format but ordering still by Plot No due to sort above
                lines.append(f"St: {r['Street No']} | P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")
            else:
                lines.append(f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")

        header = f"*Available Options in {sector} Size: {size}*\n"
        block = header + "\n".join(lines) + "\n\n"
        blocks.append(block)

    # Split into URL-safe chunks
    # Conservative caps: plain <= 3000 chars, encoded <= 1800 chars
    messages = _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800)

    return messages

# Delete rows from Google Sheet
def delete_rows_from_sheet(row_numbers):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        
        valid_rows = [row_num for row_num in row_numbers if row_num > 1]
        if not valid_rows:
            return True
            
        valid_rows.sort(reverse=True)
        
        BATCH_SIZE = 10
        for i in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[i:i+BATCH_SIZE]
            for row_num in batch:
                try:
                    sheet.delete_rows(row_num)
                except Exception as e:
                    st.error(f"Error deleting row {row_num}: {str(e)}")
                    continue
                    
            import time
            time.sleep(1)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error in delete operation: {str(e)}")
        return False

# Function to create grouped view with colors for duplicate entries
def create_duplicates_view(df):
    if df.empty:
        return None, pd.DataFrame()
    
    # Check if required columns exist
    required_cols = ["Sector", "Plot No", "Street No", "Plot Size"]
    for col in required_cols:
        if col not in df.columns:
            st.warning(f"Cannot check duplicates: Missing column '{col}'")
            return None, pd.DataFrame()
    
    # Fixed the typo: ast(str) -> astype(str)
    df["GroupKey"] = df["Sector"].astype(str) + "|" + df["Plot No"].astype(str) + "|" + df["Street No"].astype(str) + "|" + df["Plot Size"].astype(str)
    
    group_counts = df["GroupKey"].value_counts()
    
    duplicate_groups = group_counts[group_counts >= 2].index
    duplicate_df = df[df["GroupKey"].isin(duplicate_groups)]
    
    if duplicate_df.empty:
        return None, duplicate_df
    
    duplicate_df = duplicate_df.sort_values(by="GroupKey")
    
    unique_groups = duplicate_df["GroupKey"].unique()
    color_map = {}
    colors = ["#FFCCCC", "#CCFFCC", "#CCCCFF", "#FFFFCC", "#FFCCFF", "#CCFFFF", "#FFE5CC", "#E5CCFF"]
    
    for i, group in enumerate(unique_groups):
        color_map[group] = colors[i % len(colors)]
    
    def apply_row_color(row):
        return [f"background-color: {color_map[row['GroupKey']]}"] * len(row)
    
    styled_df = duplicate_df.style.apply(apply_row_color, axis=1)
    return styled_df, duplicate_df

# Format phone number for tel: link
def format_phone_link(phone):
    cleaned = clean_number(phone)
    if len(cleaned) == 10 and cleaned.startswith('3'):
        return f"92{cleaned}"
    elif len(cleaned) == 11 and cleaned.startswith('03'):
        return f"92{cleaned[1:]}"
    elif len(cleaned) == 12 and cleaned.startswith('92'):
        return cleaned
    else:
        return cleaned

# Parse VCF file
def parse_vcf_file(vcf_file):
    contacts = []
    try:
        # Read the uploaded file
        content = vcf_file.getvalue().decode("utf-8")
        
        # Parse vCard content
        vcards = vobject.readComponents(content)
        
        for vcard in vcards:
            try:
                name = ""
                if hasattr(vcard, 'fn') and vcard.fn.value:
                    name = vcard.fn.value
                
                phones = []
                if hasattr(vcard, 'tel'):
                    if isinstance(vcard.tel, list):
                        for tel in vcard.tel:
                            phones.append(tel.value)
                    else:
                        phones.append(vcard.tel.value)
                
                email = ""
                if hasattr(vcard, 'email'):
                    if isinstance(vcard.email, list):
                        email = vcard.email[0].value if vcard.email else ""
                    else:
                        email = vcard.email.value
                
                # Add contact if we have at least a name or phone number
                if name or phones:
                    contacts.append({
                        "Name": name,
                        "Contact1": phones[0] if phones else "",
                        "Contact2": phones[1] if len(phones) > 1 else "",
                        "Contact3": phones[2] if len(phones) > 2 else "",
                        "Email": email,
                        "Address": ""  # VCF typically doesn't have address in a simple field
                    })
            except Exception as e:
                st.warning(f"Could not parse one contact: {e}")
                continue
                
    except Exception as e:
        st.error(f"Error parsing VCF file: {e}")
    
    return contacts

# --- Streamlit App ---
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    
    # Initialize session state for tab management
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Plots"
    if "selected_contact" not in st.session_state:
        st.session_state.selected_contact = None
    
    # Create tabs
    tabs = st.tabs(["Plots", "Contacts", "Leads Management"])
    
    # Load data
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    
    # Add row numbers to contacts for deletion
    if not contacts_df.empty:
        contacts_df["SheetRowNum"] = [i + 2 for i in range(len(contacts_df))]
    
    # Tab 1: Plots
    with tabs[0]:
        all_features = get_all_unique_features(df)
        
        with st.sidebar:
            st.header("🔍 Filters")
            sector_filter = st.text_input("Sector")
            plot_size_filter = st.text_input("Plot Size")
            street_filter = st.text_input("Street No")
            plot_no_filter = st.text_input("Plot No")
            contact_filter = st.text_input("Phone Number (03xxxxxxxxx)")
            price_from = st.number_input("Price From (in Lacs)", min_value=0.0, value=0.0, step=1.0)
            price_to = st.number_input("Price To (in Lacs)", min_value=0.0, value=1000.0, step=1.0)
            selected_features = st.multiselect("Select Feature(s)", options=all_features)
            date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

            # Property Type filter
            prop_type_options = ["All"]
            if "Property Type" in df.columns:
                prop_type_options += sorted([str(v).strip() for v in df["Property Type"].dropna().astype(str).unique()])
            selected_prop_type = st.selectbox("Property Type", prop_type_options)

            dealer_names, contact_to_name = build_name_map(df)
            selected_dealer = st.selectbox("Dealer Name (by contact)", [""] + dealer_names)

            contact_names = [""] + sorted(contacts_df["Name"].dropna().unique()) if not contacts_df.empty else [""]
            
            # Pre-select contact if coming from Contacts tab
            if st.session_state.selected_contact:
                selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names, 
                                             index=contact_names.index(st.session_state.selected_contact) if st.session_state.selected_contact in contact_names else 0)
                # Reset after using
                st.session_state.selected_contact = None
            else:
                selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names)
        
        # Display dealer contact info if selected
        if selected_dealer:
            actual_name = selected_dealer.split(". ", 1)[1] if ". " in selected_dealer else selected_dealer
            
            # Find all numbers for this dealer
            dealer_numbers = []
            for contact, name in contact_to_name.items():
                if name == actual_name:
                    dealer_numbers.append(contact)
            
            if dealer_numbers:
                st.subheader(f"📞 Contact: {actual_name}")
                cols = st.columns(len(dealer_numbers))
                for i, num in enumerate(dealer_numbers):
                    formatted_num = format_phone_link(num)
                    cols[i].markdown(f'<a href="tel:{formatted_num}" style="display: inline-block; padding: 0.5rem 1rem; background-color: #25D366; color: white; text-decoration: none; border-radius: 0.5rem;">Call {num}</a>', 
                                    unsafe_allow_html=True)

        df_filtered = df.copy()

        if selected_dealer:
            actual_name = selected_dealer.split(". ", 1)[1] if ". " in selected_dealer else selected_dealer
            selected_contacts = [c for c, name in contact_to_name.items() if name == actual_name]
            df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
                lambda x: any(c in clean_number(x) for c in selected_contacts))]

        if selected_saved:
            row = contacts_df[contacts_df["Name"] == selected_saved].iloc[0] if not contacts_df.empty and not contacts_df[contacts_df["Name"] == selected_saved].empty else None
            selected_contacts = []
            if row is not None:
                for col in ["Contact1", "Contact2", "Contact3"]:
                    if col in row and pd.notna(row[col]):
                        selected_contacts.extend(extract_numbers(row[col]))
            df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
                lambda x: any(n in clean_number(x) for n in selected_contacts))]

        if sector_filter:
            df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
        if plot_size_filter:
            df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
        
        # Enhanced Street No filter - match exact or partial matches
        if street_filter:
            street_pattern = re.compile(re.escape(street_filter), re.IGNORECASE)
            df_filtered = df_filtered[df_filtered["Street No"].apply(lambda x: bool(street_pattern.search(str(x))))]
        
        # Enhanced Plot No filter - match exact or partial matches
        if plot_no_filter:
            plot_pattern = re.compile(re.escape(plot_no_filter), re.IGNORECASE)
            df_filtered = df_filtered[df_filtered["Plot No"].apply(lambda x: bool(plot_pattern.search(str(x))))]
        
        if contact_filter:
            cnum = clean_number(contact_filter)
            df_filtered = df_filtered[df_filtered["Extracted Contact"].astype(str).apply(
                lambda x: any(cnum == clean_number(p) for p in x.split(",")))]

        # Apply Property Type filter if selected
        if "Property Type" in df_filtered.columns and selected_prop_type and selected_prop_type != "All":
            df_filtered = df_filtered[df_filtered["Property Type"].astype(str).str.strip() == selected_prop_type]

        df_filtered["ParsedPrice"] = df_filtered["Demand"].apply(parse_price)
        df_filtered = df_filtered[df_filtered["ParsedPrice"].notnull()]
        df_filtered = df_filtered[(df_filtered["ParsedPrice"] >= price_from) & (df_filtered["ParsedPrice"] <= price_to)]

        if selected_features:
            df_filtered = df_filtered[df_filtered["Features"].apply(lambda x: fuzzy_feature_match(x, selected_features))]

        df_filtered = filter_by_date(df_filtered, date_filter)

        # Move Timestamp column to the end
        if "Timestamp" in df_filtered.columns:
            cols = [col for col in df_filtered.columns if col != "Timestamp"] + ["Timestamp"]
            df_filtered = df_filtered[cols]

        st.subheader("📋 Filtered Listings")
        
        # Count WhatsApp eligible listings (same rules you had)
        whatsapp_eligible_count = 0
        for _, row in df_filtered.iterrows():
            sector = str(row.get("Sector", "")).strip()
            plot_no = str(row.get("Plot No", "")).strip()
            size = str(row.get("Plot Size", "")).strip()
            price = str(row.get("Demand", "")).strip()
            street = str(row.get("Street No", "")).strip()
            
            if not (sector and plot_no and size and price):
                continue
            if "I-15/" in sector and not street:
                continue
            if "series" in plot_no.lower():
                continue
            whatsapp_eligible_count += 1
        
        st.info(f"📊 Total filtered listings: {len(df_filtered)} | ✅ WhatsApp eligible: {whatsapp_eligible_count}")
        
        # Row selection and deletion feature for main table
        if not df_filtered.empty:
            display_df = df_filtered.copy().reset_index(drop=True)
            display_df.insert(0, "Select", False)
            
            # Add "Select All" checkbox
            select_all = st.checkbox("Select All Rows", key="select_all_main")
            if select_all:
                display_df["Select"] = True
            
            # Configure columns for data editor
            column_config = {
                "Select": st.column_config.CheckboxColumn(required=True),
                "SheetRowNum": st.column_config.NumberColumn(disabled=True)
            }
            
            # Display editable dataframe with checkboxes
            edited_df = st.data_editor(
                display_df,
                column_config=column_config,
                hide_index=True,
                use_container_width=True,
                disabled=display_df.columns.difference(["Select"]).tolist()
            )
            
            # Get selected rows
            selected_rows = edited_df[edited_df["Select"]]
            
            if not selected_rows.empty:
                st.markdown(f"**{len(selected_rows)} row(s) selected**")
                
                # Show delete confirmation with progress bar
                if st.button("🗑️ Delete Selected Rows", type="primary", key="delete_button_main"):
                    row_nums = selected_rows["SheetRowNum"].tolist()
                    
                    # Show progress
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Delete with progress updates
                    success = delete_rows_from_sheet(row_nums)
                    
                    if success:
                        progress_bar.progress(100)
                        status_text.success(f"✅ Successfully deleted {len(selected_rows)} row(s)!")
                        # Clear cache and refresh
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        status_text.error("❌ Failed to delete some rows. Please try again.")
        else:
            st.info("No listings match your filters")
        
        st.markdown("---")
        st.subheader("👥 Duplicate Listings (Matching Sector, Plot No, Street No, Plot Size)")
        
        # Create and display grouped view with colors for duplicates
        if not df_filtered.empty:
            # Generate styled DataFrame with duplicate groups
            styled_duplicates_df, duplicates_df = create_duplicates_view(df_filtered)
            
            if duplicates_df.empty:
                st.info("No duplicate listings found")
            else:
                st.info("Showing only duplicate listings with matching Sector, Plot No, Street No and Plot Size")
                
                # Display the styled DataFrame (color-coded)
                st.dataframe(
                    styled_duplicates_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Create a copy for deletion with selection column
                duplicate_display = duplicates_df.copy().reset_index(drop=True)
                duplicate_display.insert(0, "Select", False)
                
                # Add "Select All" checkbox for duplicates
                select_all_duplicates = st.checkbox("Select All Duplicate Rows", key="select_all_duplicates")
                if select_all_duplicates:
                    duplicate_display["Select"] = True
                
                # Configure columns for data editor
                column_config = {
                    "Select": st.column_config.CheckboxColumn(required=True),
                    "SheetRowNum": st.column_config.NumberColumn(disabled=True)
                }
                
                # Display editable dataframe with checkboxes
                edited_duplicates = st.data_editor(
                    duplicate_display,
                    column_config=column_config,
                    hide_index=True,
                    use_container_width=True,
                    disabled=duplicate_display.columns.difference(["Select"]).tolist()
                )
                
                # Get selected rows
                selected_duplicates = edited_duplicates[edited_duplicates["Select"]]
                
                if not selected_duplicates.empty:
                    st.markdown(f"**{len(selected_duplicates)} duplicate row(s) selected**")
                    
                    # Show delete confirmation with progress bar
                    if st.button("🗑️ Delete Selected Duplicate Rows", type="primary", key="delete_button_duplicates"):
                        row_nums = selected_duplicates["SheetRowNum"].tolist()
                        
                        # Show progress
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # Delete with progress updates
                        success = delete_rows_from_sheet(row_nums)
                        
                        if success:
                            progress_bar.progress(100)
                            status_text.success(f"✅ Successfully deleted {len(selected_duplicates)} duplicate row(s)!")
                            # Clear cache and refresh
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            status_text.error("❌ Failed to delete some rows. Please try again.")
        else:
            st.info("No listings to analyze for duplicates")

        st.markdown("---")
        st.subheader("📤 Send WhatsApp Message")

        selected_name_whatsapp = st.selectbox("📱 Select Contact to Message", contact_names, key="wa_contact")
        manual_number = st.text_input("Or Enter WhatsApp Number (e.g. 0300xxxxxxx)")

        if st.button("Generate WhatsApp Message"):
            cleaned = ""
            if manual_number:
                cleaned = clean_number(manual_number)
            elif selected_name_whatsapp:
                contact_row = contacts_df[contacts_df["Name"] == selected_name_whatsapp].iloc[0] if not contacts_df.empty and not contacts_df[contacts_df["Name"] == selected_name_whatsapp].empty else None
                if contact_row is not None:
                    numbers = []
                    for col in ["Contact1", "Contact2", "Contact3"]:
                        if col in contact_row and pd.notna(contact_row[col]):
                            numbers.append(clean_number(contact_row[col]))
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

            # Use the same filtered dataframe as the main table with intentional filters
            messages = generate_whatsapp_messages(df_filtered)
            if not messages:
                st.warning("⚠️ No valid listings to include. Listings must have: Sector, Plot No, Size, Price; I-15 must have Street No; No 'series' plots.")
            else:
                st.success(f"📨 Generated {len(messages)} WhatsApp message(s)")
                
                # Show message previews and safe links
                for i, msg in enumerate(messages):
                    st.markdown(f"**Message {i+1}** ({len(msg)} characters):")
                    st.text_area(f"Preview Message {i+1}", msg, height=150, key=f"msg_preview_{i}")
                    
                    encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                    link = f"https://wa.me/{wa_number}?text={encoded}"
                    st.markdown(f"[📩 Send Message {i+1}]({link})", unsafe_allow_html=True)
                    st.markdown("---")
    
    # Tab 2: Contacts
    with tabs[1]:
        st.header("📇 Contact Management")
        
        # Add new contact form
        with st.form("add_contact_form"):
            st.subheader("Add New Contact")
            col1, col2 = st.columns(2)
            name = col1.text_input("Name*", key="contact_name")
            contact1 = col1.text_input("Contact 1*", key="contact_1")
            contact2 = col2.text_input("Contact 2", key="contact_2")
            contact3 = col2.text_input("Contact 3", key="contact_3")
            email = col1.text_input("Email", key="contact_email")
            address = col2.text_input("Address", key="contact_address")
            
            submitted = st.form_submit_button("Add Contact")
            
            if submitted:
                if not name or not contact1:
                    st.error("Name and Contact 1 are required fields!")
                else:
                    contact_data = [name, contact1, contact2 or "", contact3 or "", email or "", address or ""]
                    if add_contact_to_sheet(contact_data):
                        st.success("Contact added successfully!")
                        # Clear cache to reload contacts
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Failed to add contact. Please try again.")
        
        st.markdown("---")
        
        # Import contacts from VCF
        st.subheader("Import Contacts from VCF")
        vcf_file = st.file_uploader("Upload VCF file", type=["vcf"], key="vcf_uploader")
        
        if vcf_file is not None:
            contacts = parse_vcf_file(vcf_file)
            if contacts:
                st.success(f"Found {len(contacts)} contacts in the VCF file")
                
                # Display contacts for review
                for i, contact in enumerate(contacts):
                    with st.expander(f"Contact {i+1}: {contact['Name']}"):
                        st.write(f"**Contact 1:** {contact['Contact1']}")
                        st.write(f"**Contact 2:** {contact['Contact2']}")
                        st.write(f"**Contact 3:** {contact['Contact3']}")
                        st.write(f"**Email:** {contact['Email']}")
                
                # Button to import all contacts
                if st.button("Import All Contacts", key="import_all"):
                    success_count = 0
                    for contact in contacts:
                        contact_data = [
                            contact["Name"],
                            contact["Contact1"],
                            contact["Contact2"],
                            contact["Contact3"],
                            contact["Email"],
                            contact["Address"]
                        ]
                        if add_contact_to_sheet(contact_data):
                            success_count += 1
                    
                    st.success(f"Successfully imported {success_count} out of {len(contacts)} contacts")
                    st.cache_data.clear()
                    st.rerun()
        
        st.markdown("---")
        st.subheader("Saved Contacts")
        
        # Display existing contacts with selection for deletion
        if not contacts_df.empty:
            # Create a copy for editing
            contacts_display = contacts_df.copy().reset_index(drop=True)
            contacts_display.insert(0, "Select", False)
            
            # Add "Select All" checkbox
            select_all_contacts = st.checkbox("Select All Contacts", key="select_all_contacts")
            if select_all_contacts:
                contacts_display["Select"] = True
            
            # Configure columns for data editor
            column_config = {
                "Select": st.column_config.CheckboxColumn(required=True),
                "SheetRowNum": st.column_config.NumberColumn(disabled=True)
            }
            
            # Display editable dataframe with checkboxes
            edited_contacts = st.data_editor(
                contacts_display,
                column_config=column_config,
                hide_index=True,
                use_container_width=True,
                disabled=contacts_display.columns.difference(["Select"]).tolist()
            )
            
            # Get selected contacts
            selected_contacts = edited_contacts[edited_contacts["Select"]]
            
            if not selected_contacts.empty:
                st.markdown(f"**{len(selected_contacts)} contact(s) selected**")
                
                # Show delete confirmation
                if st.button("🗑️ Delete Selected Contacts", type="primary", key="delete_contacts"):
                    row_nums = selected_contacts["SheetRowNum"].tolist()
                    
                    # Show progress
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Delete with progress updates
                    success = delete_contacts_from_sheet(row_nums)
                    
                    if success:
                        progress_bar.progress(100)
                        status_text.success(f"✅ Successfully deleted {len(selected_contacts)} contact(s)!")
                        # Clear cache and refresh
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        status_text.error("❌ Failed to delete some contacts. Please try again.")
            
            # Display individual contacts with "Show Shared Listings" button
            for idx, row in contacts_df.iterrows():
                with st.expander(f"{row['Name']} - {row.get('Contact1', '')}"):
                    col1, col2 = st.columns(2)
                    col1.write(f"**Contact 1:** {row.get('Contact1', '')}")
                    col1.write(f"**Contact 2:** {row.get('Contact2', '')}")
                    col1.write(f"**Contact 3:** {row.get('Contact3', '')}")
                    col2.write(f"**Email:** {row.get('Email', '')}")
                    col2.write(f"**Address:** {row.get('Address', '')}")
                    
                    # Button to show shared listings
                    if st.button("Show Shared Listings", key=f"show_listings_{idx}"):
                        # Set the contact filter in session state and switch to Plots tab
                        st.session_state.selected_contact = row['Name']
                        st.session_state.active_tab = "Plots"
                        st.rerun()
        else:
            st.info("No contacts found. Add a new contact using the form above.")
    
    # Tab 3: Leads Management
    with tabs[2]:
        st.header("📊 Leads Management")
        st.info("This section is under development and will be available in the next phase.")

if __name__ == "__main__":
    main()
