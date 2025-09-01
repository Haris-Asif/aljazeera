import streamlit as st
import pandas as pd
import gspread
import re
import difflib
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict
import unicodedata

# Constants
SPREADSHEET_NAME = "Al-Jazeera"
PLOTS_SHEET = "Plots"
CONTACTS_SHEET = "Contacts"

# Streamlit setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# --- Helpers ---
def clean_number(num):
    """Extract only digits from a string"""
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text):
    """Extract all phone numbers from a string"""
    text = str(text or "")
    # Match Pakistani phone number patterns
    patterns = [
        r"\b03\d{2} ?\d{3} ?\d{4}\b",  # 03XX XXX XXXX
        r"\b\d{4} ?\d{3} ?\d{3}\b",    # XXXX XXX XXX
        r"\b\d{5} ?\d{5}\b",           # XXXXX XXXXX
        r"\b\d{11}\b",                 # 11 consecutive digits
    ]
    
    numbers = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            cleaned = clean_number(match)
            if len(cleaned) == 11 and cleaned.startswith('03'):
                numbers.append(cleaned)
            elif len(cleaned) == 10 and cleaned.startswith('3'):
                numbers.append('0' + cleaned)
    
    return numbers

def parse_price(price_str):
    """Parse price string into numeric value"""
    try:
        price_str = str(price_str).lower().replace(",", "").replace("cr", "00").replace("crore", "00")
        numbers = re.findall(r"\d+\.?\d*", price_str)
        return float(numbers[0]) if numbers else None
    except:
        return None

def normalize_text(text):
    """Normalize text for consistent comparison"""
    if not text or pd.isna(text):
        return ""
    # Convert to string, lowercase, and remove extra spaces
    text = str(text).lower().strip()
    # Remove special characters and keep only alphanumeric and spaces
    text = re.sub(r'[^\w\s]', '', text)
    # Normalize unicode characters
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return text

def get_all_unique_features(df):
    """Extract all unique features from the dataset"""
    feature_set = set()
    for f in df["Features"].fillna("").astype(str):
        parts = [normalize_text(p.strip()) for p in f.split(",") if p.strip()]
        feature_set.update(parts)
    return sorted(feature_set)

def fuzzy_feature_match(row_features, selected_features):
    """Fuzzy match features with selected features"""
    if not row_features or pd.isna(row_features):
        return False
        
    row_features = [normalize_text(f.strip()) for f in str(row_features).split(",")]
    selected_features = [normalize_text(f) for f in selected_features]
    
    for sel in selected_features:
        match = difflib.get_close_matches(sel, row_features, n=1, cutoff=0.7)
        if match:
            return True
    return False

# Google Sheets
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_gsheet_client():
    """Authenticate with Google Sheets API"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_plot_data():
    """Load plot data from Google Sheets"""
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        df["SheetRowNum"] = [i + 2 for i in range(len(df))]  # Start from row 2
        return df
    except Exception as e:
        st.error(f"Error loading plot data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_contacts():
    """Load contacts data from Google Sheets"""
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        return pd.DataFrame(sheet.get_all_records())
    except Exception as e:
        st.error(f"Error loading contacts: {e}")
        return pd.DataFrame()

def filter_by_date(df, label):
    """Filter dataframe by date range"""
    if label == "All" or df.empty:
        return df
        
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.now() - timedelta(days=days_map.get(label, 0))
    
    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            try:
                return datetime.strptime(val.strip(), "%Y-%m-%d")
            except:
                return None
                
    df["ParsedDate"] = df["Timestamp"].apply(try_parse)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

def build_name_map(df):
    """Build mapping of dealer names to contact numbers with fuzzy matching"""
    if df.empty:
        return [], {}
    
    # Collect all name-contact pairs
    name_contact_pairs = []
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name", "")).strip()
        contacts = extract_numbers(row.get("Extracted Contact", ""))
        
        if name and contacts:
            for contact in contacts:
                if contact:
                    name_contact_pairs.append((name, contact))
    
    if not name_contact_pairs:
        return [], {}
    
    # Group contacts by normalized names (case-insensitive)
    name_to_contacts = defaultdict(set)
    for name, contact in name_contact_pairs:
        normalized_name = normalize_text(name)
        if normalized_name:
            name_to_contacts[normalized_name].add(contact)
    
    # Use fuzzy matching to group similar names
    merged_groups = {}
    all_names = list(name_to_contacts.keys())
    
    for name in all_names:
        if name not in merged_groups:
            # Find similar names
            matches = difflib.get_close_matches(name, all_names, n=5, cutoff=0.7)
            for match in matches:
                if match not in merged_groups:
                    merged_groups[match] = name
                    # Merge contacts
                    name_to_contacts[name].update(name_to_contacts[match])
    
    # Create the final mapping
    final_mapping = {}
    for canonical_name in set(merged_groups.values()):
        contacts = name_to_contacts[canonical_name]
        for contact in contacts:
            final_mapping[contact] = canonical_name
    
    # Get the original name representation for display (first occurrence)
    display_names = {}
    for orig_name, contact in name_contact_pairs:
        normalized = normalize_text(orig_name)
        if normalized in set(merged_groups.values()):
            display_names[normalized] = orig_name  # Keep the original formatting
    
    # Create numbered list for dropdown
    numbered_dealers = []
    for i, normalized_name in enumerate(sorted(set(merged_groups.values())), 1):
        display_name = display_names.get(normalized_name, normalized_name)
        numbered_dealers.append(f"{i}. {display_name}")
    
    return numbered_dealers, final_mapping

def sector_matches(f, c):
    """Check if sector filter matches sector value"""
    if not f:
        return True
    f = f.replace(" ", "").upper()
    c = str(c).replace(" ", "").upper()
    return f in c if "/" not in f else f == c

def safe_dataframe(df):
    """Create a safe copy of dataframe for display"""
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

# ---------- WhatsApp utilities ----------
def _extract_int(val):
    """Extract first integer from a string; used for numeric sorting of Plot No."""
    try:
        m = re.search(r"\d+", str(val))
        return int(m.group()) if m else float("inf")
    except:
        return float("inf")

def _url_encode_for_whatsapp(text: str) -> str:
    """Encode minimally for wa.me URL"""
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

def generate_whatsapp_messages(df):
    """Generate WhatsApp messages from filtered data"""
    # Build list of eligible rows
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

    # Group by (Sector, Plot Size)
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
                lines.append(f"St: {r['Street No']} | P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")
            else:
                lines.append(f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")

        header = f"*Available Options in {sector} Size: {size}*\n"
        block = header + "\n".join(lines) + "\n\n"
        blocks.append(block)

    # Split into URL-safe chunks
    messages = _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800)

    return messages

def delete_rows_from_sheet(row_numbers):
    """Delete rows from Google Sheet"""
    try:
        client = get_gsheet_client()
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
            
        return True
    except Exception as e:
        st.error(f"Error in delete operation: {str(e)}")
        return False

def create_duplicates_view(df):
    """Create a view for duplicate listings with color coding"""
    if df.empty:
        return None, pd.DataFrame()
    
    # Create a composite key for grouping
    df["GroupKey"] = (
        df["Sector"].astype(str) + "|" + 
        df["Plot No"].astype(str) + "|" + 
        df["Street No"].astype(str) + "|" + 
        df["Plot Size"].astype(str)
    )
    
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

# --- Streamlit App ---
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")

    # Load data
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()

    # Get all unique features and property types
    all_features = get_all_unique_features(df)
    
    # Get property types from the sheet
    prop_type_options = ["All"]
    if "Property Type" in df.columns:
        prop_types = [str(v).strip() for v in df["Property Type"].dropna().astype(str).unique() if v]
        prop_type_options.extend(sorted(prop_types))

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street No")
        plot_no_filter = st.text_input("Plot No")
        contact_filter = st.text_input("Phone Number (03xxxxxxxxx)")
        
        # Price range with no default filtering
        price_from = st.number_input("Price From (in Lacs)", min_value=0.0, value=0.0, step=1.0)
        price_to = st.number_input("Price To (in Lacs)", min_value=0.0, value=10000.0, step=1.0)
        
        selected_features = st.multiselect("Select Feature(s)", options=all_features)
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])
        selected_prop_type = st.selectbox("Property Type", prop_type_options)

        # Build dealer name mapping
        dealer_names, contact_to_name = build_name_map(df)
        selected_dealer = st.selectbox("Dealer Name (by contact)", [""] + dealer_names)

        # Get contact names
        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names)

    # Start with all data
    df_filtered = df.copy()

    # Apply filters
    if selected_dealer:
        actual_name = selected_dealer.split(". ", 1)[1] if ". " in selected_dealer else selected_dealer
        # Normalize for comparison
        normalized_actual_name = normalize_text(actual_name)
        # Find all contacts associated with this dealer (exact and fuzzy matches)
        selected_contacts = [c for c, name in contact_to_name.items() if normalize_text(name) == normalized_actual_name]
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(c in clean_number(x) for c in selected_contacts))]

    if selected_saved:
        row = contacts_df[contacts_df["Name"] == selected_saved].iloc[0] if not contacts_df[contacts_df["Name"] == selected_saved].empty else None
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
    
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street No"].str.contains(street_filter, case=False, na=False)]
    
    if plot_no_filter:
        # Enhanced plot number filter to match various formats
        pattern = re.compile(re.escape(plot_no_filter), re.IGNORECASE)
        df_filtered = df_filtered[df_filtered["Plot No"].apply(lambda x: bool(pattern.search(str(x))))]
    
    if contact_filter:
        cnum = clean_number(contact_filter)
        df_filtered = df_filtered[df_filtered["Extracted Contact"].astype(str).apply(
            lambda x: any(cnum == clean_number(p) for p in extract_numbers(x)))]

    # Apply Property Type filter if selected
    if "Property Type" in df_filtered.columns and selected_prop_type and selected_prop_type != "All":
        df_filtered = df_filtered[df_filtered["Property Type"].astype(str).str.strip() == selected_prop_type]

    # Parse prices and filter by price range
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
    
    # Count WhatsApp eligible listings
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
            contact_row = contacts_df[contacts_df["Name"] == selected_name_whatsapp]
            if not contact_row.empty:
                row = contact_row.iloc[0]
                numbers = []
                for col in ["Contact1", "Contact2", "Contact3"]:
                    if col in row and pd.notna(row[col]):
                        numbers.append(clean_number(row[col]))
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

if __name__ == "__main__":
    main()
