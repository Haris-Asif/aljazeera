import streamlit as st
import pandas as pd
import re
from utils import (load_plot_data, load_contacts, delete_rows_from_sheet, 
                  generate_whatsapp_messages, build_name_map, sector_matches,
                  extract_numbers, clean_number, format_phone_link, 
                  get_all_unique_features, filter_by_date, create_duplicates_view_updated,
                  parse_price, update_plot_data, load_sold_data, save_sold_data,
                  generate_sold_id, sort_dataframe, safe_dataframe_for_display, _extract_int)
from utils import fuzzy_feature_match
from datetime import datetime, timedelta
from io import BytesIO

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Import hold functions with fallbacks
try:
    from utils import load_hold_data, save_hold_data, move_to_hold, move_to_plots
except ImportError:
    st.error("⚠️ Hold functions not found in utils.py. Please add the required functions.")
    
    # Fallback implementations
    def load_hold_data():
        return pd.DataFrame()
    
    def save_hold_data(df):
        st.error("Hold functionality not available")
        return False
    
    def move_to_hold(row_nums):
        st.error("Hold functionality not available")
        return False
    
    def move_to_plots(row_nums):
        st.error("Hold functionality not available")
        return False

def get_dynamic_dealer_names(df, filters):
    """Get dealer names based on current filter settings"""
    df_temp = df.copy()
    
    # Apply all current filters except dealer filter
    if filters.get('sector_filter'):
        sector_filter = filters['sector_filter']
        if isinstance(sector_filter, list) and sector_filter:
            # Multi-select: use exact matching
            df_temp = df_temp[df_temp["Sector"].isin(sector_filter)]
        elif sector_filter:  # String case
            df_temp = df_temp[df_temp["Sector"].apply(lambda x: sector_matches(sector_filter, str(x)))]
    
    if filters.get('plot_size_filter'):
        plot_size_filter = filters['plot_size_filter']
        if isinstance(plot_size_filter, list) and plot_size_filter:
            # Multi-select: use exact matching
            df_temp = df_temp[df_temp["Plot Size"].isin(plot_size_filter)]
        elif plot_size_filter:  # String case
            df_temp = df_temp[df_temp["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
    
    if filters.get('street_filter'):
        street_pattern = re.compile(re.escape(filters['street_filter']), re.IGNORECASE)
        df_temp = df_temp[df_temp["Street No"].apply(lambda x: bool(street_pattern.search(str(x))))]
    
    if filters.get('plot_no_filter'):
        plot_pattern = re.compile(re.escape(filters['plot_no_filter']), re.IGNORECASE)
        df_temp = df_temp[df_temp["Plot No"].apply(lambda x: bool(plot_pattern.search(str(x))))]
    
    if filters.get('contact_filter'):
        cnum = clean_number(filters['contact_filter'])
        df_temp = df_temp[df_temp["Extracted Contact"].astype(str).apply(
            lambda x: any(cnum == clean_number(p) for p in x.split(",")))]
    
    if filters.get('selected_prop_type') and filters['selected_prop_type'] != "All" and "Property Type" in df_temp.columns:
        df_temp = df_temp[df_temp["Property Type"].astype(str).str.strip() == filters['selected_prop_type']]
    
    # Apply price filter
    df_temp["ParsedPrice"] = df_temp["Demand"].apply(parse_price)
    if "ParsedPrice" in df_temp.columns:
        df_temp_with_price = df_temp[df_temp["ParsedPrice"].notnull()]
        if not df_temp_with_price.empty:
            df_temp = df_temp_with_price[
                (df_temp_with_price["ParsedPrice"] >= filters.get('price_from', 0)) & 
                (df_temp_with_price["ParsedPrice"] <= filters.get('price_to', 1000))
            ]
    
    # Apply features filter
    if filters.get('selected_features'):
        df_temp = df_temp[df_temp["Features"].apply(lambda x: fuzzy_feature_match(x, filters['selected_features']))]
    
    # Apply date filter
    df_temp = filter_by_date(df_temp, filters.get('date_filter', 'All'))
    
    # Apply missing contact filter if enabled
    if filters.get('missing_contact_filter'):
        pass
    else:
        df_temp = df_temp[
            ~(df_temp["Extracted Contact"].isna() | (df_temp["Extracted Contact"] == "")) | 
            ~(df_temp["Extracted Name"].isna() | (df_temp["Extracted Name"] == ""))
        ]
    
    # Build dealer names from the filtered data
    dealer_names, contact_to_name = build_name_map(df_temp)
    return dealer_names, contact_to_name

def create_dealer_specific_duplicates_view(df, dealer_contacts):
    """Create a view of duplicates specific to the selected dealer's listings"""
    if df.empty or not dealer_contacts:
        return None, pd.DataFrame()
    
    # Create a normalized version of key fields for comparison
    df_normalized = df.copy()
    df_normalized["Sector_Norm"] = df_normalized["Sector"].astype(str).str.strip().str.upper()
    df_normalized["Plot_No_Norm"] = df_normalized["Plot No"].astype(str).str.strip().str.upper()
    df_normalized["Street_No_Norm"] = df_normalized["Street No"].astype(str).str.strip().str.upper()
    df_normalized["Plot_Size_Norm"] = df_normalized["Plot Size"].astype(str).str.strip().str.upper()
    
    # Get listings from the selected dealer
    dealer_listings = df_normalized[
        df_normalized["Extracted Contact"].apply(
            lambda x: any(contact in clean_number(str(x)) for contact in dealer_contacts)
        )
    ]
    
    if dealer_listings.empty:
        return None, pd.DataFrame()
    
    # Create group keys for the dealer's listings
    dealer_listings["GroupKey"] = dealer_listings.apply(
        lambda row: f"{row['Sector_Norm']}|{row['Plot_No_Norm']}|{row['Street_No_Norm']}|{row['Plot_Size_Norm']}", 
        axis=1
    )
    
    # Find all listings that match the dealer's group keys
    all_matching_listings = []
    for group_key in dealer_listings["GroupKey"].unique():
        # Get all listings with this group key
        matching_listings = df_normalized[
            df_normalized.apply(
                lambda row: f"{row['Sector_Norm']}|{row['Plot_No_Norm']}|{row['Street_No_Norm']}|{row['Plot_Size_Norm']}" == group_key,
                axis=1
            )
        ]
        
        # Only include if there are multiple different contacts
        unique_contacts = set()
        for contact_str in matching_listings["Extracted Contact"]:
            contacts = [clean_number(c) for c in str(contact_str).split(",") if clean_number(c)]
            unique_contacts.update(contacts)
        
        if len(unique_contacts) > 1:
            matching_listings = matching_listings.copy()
            matching_listings["GroupKey"] = group_key
            all_matching_listings.append(matching_listings)
    
    if not all_matching_listings:
        return None, pd.DataFrame()
    
    # Combine all duplicates
    duplicates_df = pd.concat(all_matching_listings, ignore_index=True)
    
    # Remove temporary normalized columns
    duplicates_df = duplicates_df.drop(
        ["Sector_Norm", "Plot_No_Norm", "Street_No_Norm", "Plot_Size_Norm"], 
        axis=1, 
        errors="ignore"
    )
    
    # --- PERFORMANCE FIX: Limit styling row count ---
    if len(duplicates_df) > 50:
        return None, duplicates_df

    # Create styled version with color grouping
    try:
        groups = duplicates_df["GroupKey"].unique()
        color_mapping = {group: f"hsl({int(i*360/len(groups))}, 70%, 80%)" for i, group in enumerate(groups)}
        
        def color_group(row):
            return [f"background-color: {color_mapping[row['GroupKey']]}"] * len(row)
        
        styled_duplicates_df = duplicates_df.style.apply(color_group, axis=1)
        return styled_duplicates_df, duplicates_df
    except Exception as e:
        return None, duplicates_df

def get_todays_unique_listings(df):
    """Get listings with new combinations of Sector & Plot No added today"""
    if df.empty:
        return pd.DataFrame()
    
    today = datetime.now().date()
    
    today_listings = df.copy()
    today_listings['Date'] = pd.to_datetime(today_listings['Timestamp']).dt.date
    today_listings = today_listings[today_listings['Date'] == today]
    
    if today_listings.empty:
        return pd.DataFrame()
    
    before_today_listings = df.copy()
    before_today_listings['Date'] = pd.to_datetime(before_today_listings['Timestamp']).dt.date
    before_today_listings = before_today_listings[before_today_listings['Date'] < today]
    
    today_listings["CombinationKey"] = today_listings.apply(
        lambda row: f"{str(row.get('Sector', '')).strip().upper()}|{str(row.get('Plot No', '')).strip().upper()}", 
        axis=1
    )
    
    before_today_listings["CombinationKey"] = before_today_listings.apply(
        lambda row: f"{str(row.get('Sector', '')).strip().upper()}|{str(row.get('Plot No', '')).strip().upper()}", 
        axis=1
    )
    
    existing_keys = set(before_today_listings["CombinationKey"].unique())
    unique_today_listings = today_listings[~today_listings["CombinationKey"].isin(existing_keys)]
    
    unique_today_listings = unique_today_listings.drop(["Date", "CombinationKey"], axis=1, errors="ignore")
    return unique_today_listings

def get_this_weeks_unique_listings(df):
    """Get listings with new combinations of Sector & Plot No added in the last 7 days"""
    if df.empty:
        return pd.DataFrame()
    
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    
    this_week_listings = df.copy()
    this_week_listings['Date'] = pd.to_datetime(this_week_listings['Timestamp']).dt.date
    this_week_listings = this_week_listings[this_week_listings['Date'] >= week_ago]
    
    if this_week_listings.empty:
        return pd.DataFrame()
    
    before_week_listings = df.copy()
    before_week_listings['Date'] = pd.to_datetime(before_week_listings['Timestamp']).dt.date
    before_week_listings = before_week_listings[before_week_listings['Date'] < week_ago]
    
    this_week_listings["CombinationKey"] = this_week_listings.apply(
        lambda row: f"{str(row.get('Sector', '')).strip().upper()}|{str(row.get('Plot No', '')).strip().upper()}", 
        axis=1
    )
    
    before_week_listings["CombinationKey"] = before_week_listings.apply(
        lambda row: f"{str(row.get('Sector', '')).strip().upper()}|{str(row.get('Plot No', '')).strip().upper()}", 
        axis=1
    )
    
    existing_keys = set(before_week_listings["CombinationKey"].unique())
    unique_week_listings = this_week_listings[~this_week_listings["CombinationKey"].isin(existing_keys)]
    
    unique_week_listings = unique_week_listings.drop(["Date", "CombinationKey"], axis=1, errors="ignore")
    return unique_week_listings

def safe_display_dataframe(df, height=300):
    """Safely display dataframe with error handling"""
    if df.empty:
        return
    try:
        safe_df = safe_dataframe_for_display(df)
        st.dataframe(safe_df, width='stretch', height=height)
    except Exception as e:
        st.error(f"Could not display dataframe: {str(e)}")
        st.table(df.head(50))

def display_table_with_actions(df, table_name, height=300, show_hold_button=True):
    """Display dataframe with edit/delete actions for any table"""
    if df.empty:
        st.info(f"No data available for {table_name}")
        return
    
    display_df = df.copy().reset_index(drop=True)
    display_df.insert(0, "Select", False)
    display_df = safe_dataframe_for_display(display_df)
    
    if show_hold_button:
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        with col1:
            select_all = st.checkbox(f"Select All {table_name} Rows", key=f"select_all_{table_name}")
        with col2:
            edit_btn = st.button("✏️ Edit Selected", width='stretch', key=f"edit_{table_name}")
        with col3:
            mark_sold_btn = st.button("✅ Mark as Sold", width='stretch', key=f"mark_sold_{table_name}")
        with col4:
            hold_btn = st.button("⏸️ Hold", width='stretch', key=f"hold_{table_name}")
        with col5:
            delete_btn = st.button("🗑️ Delete Selected", type="primary", width='stretch', key=f"delete_{table_name}")
    else:
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        with col1:
            select_all = st.checkbox(f"Select All {table_name} Rows", key=f"select_all_{table_name}")
        with col2:
            edit_btn = st.button("✏️ Edit Selected", width='stretch', key=f"edit_{table_name}")
        with col3:
            mark_sold_btn = st.button("✅ Mark as Sold", width='stretch', key=f"mark_sold_{table_name}")
        with col4:
            move_to_available_btn = st.button("🔄 Move To Available", width='stretch', key=f"move_available_{table_name}")
        with col5:
            delete_btn = st.button("🗑️ Delete Selected", type="primary", width='stretch', key=f"delete_{table_name}")
    
    if select_all:
        display_df["Select"] = True
    
    column_config = {
        "Select": st.column_config.CheckboxColumn(required=True),
        "SheetRowNum": st.column_config.NumberColumn(disabled=True)
    }
    
    edited_df = st.data_editor(
        display_df,
        column_config=column_config,
        hide_index=True,
        width='stretch',
        disabled=display_df.columns.difference(["Select"]).tolist(),
        key=f"{table_name}_data_editor"
    )
    
    selected_indices = edited_df[edited_df["Select"]].index.tolist()
    
    if selected_indices:
        st.success(f"**{len(selected_indices)} row(s) selected in {table_name}**")
        
        if edit_btn:
            if len(selected_indices) == 1:
                st.session_state.edit_mode = True
                st.session_state.editing_row = display_df.iloc[selected_indices[0]].to_dict()
                st.session_state.editing_table = table_name
                st.rerun()
            else:
                st.warning("Please select only one row to edit.")
        
        if mark_sold_btn:
            selected_display_rows = [display_df.iloc[idx] for idx in selected_indices]
            mark_listings_sold(selected_display_rows)
        
        if show_hold_button and hold_btn:
            selected_display_rows = [display_df.iloc[idx] for idx in selected_indices]
            move_listings_to_hold(selected_display_rows, table_name)
        
        if not show_hold_button and move_to_available_btn:
            selected_display_rows = [display_df.iloc[idx] for idx in selected_indices]
            move_listings_to_plots(selected_display_rows)
        
        if delete_btn:
            selected_display_rows = [display_df.iloc[idx] for idx in selected_indices]
            row_nums = [int(row["SheetRowNum"]) for row in selected_display_rows]
            st.warning(f"🗑️ Deleting {len(row_nums)} selected row(s) from {table_name}...")
            success = delete_rows_from_sheet(row_nums)
            if success:
                st.success(f"✅ Successfully deleted {len(row_nums)} row(s) from {table_name}!")
                # Clear cache and reset filters to prevent stale data issues
                st.cache_data.clear()
                # Reset filter session state to prevent multiselect errors
                reset_filter_session_state_after_deletion()
                st.rerun()
            else:
                st.error("❌ Failed to delete rows. Please try again.")

def generate_dealer_contacts_pdf(dealer_names, contact_to_name, contacts_df):
    """Generate a PDF with dealer contacts information"""
    if not REPORTLAB_AVAILABLE:
        st.error("PDF generation requires reportlab library. Please install it using: pip install reportlab")
        return None
    
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        styles = getSampleStyleSheet()
        title_style = styles['Heading1']
        title = Paragraph("Dealer Contacts Report", title_style)
        elements.append(title)
        elements.append(Paragraph("<br/>", styles['Normal']))
        
        table_data = [['Name', 'Contact 1', 'Contact 2', 'Contact 3']]
        
        actual_names = []
        for dealer in dealer_names:
            if ". " in dealer:
                actual_names.append(dealer.split(". ", 1)[1])
            else:
                actual_names.append(dealer)
        
        unique_names = sorted(set(actual_names))
        
        for name in unique_names:
            dealer_contacts = []
            for contact, contact_name in contact_to_name.items():
                if contact_name == name:
                    dealer_contacts.append(contact)
            
            contacts_row = [name]
            for i in range(3):
                if i < len(dealer_contacts):
                    contacts_row.append(dealer_contacts[i])
                else:
                    contacts_row.append("")
            
            table_data.append(contacts_row)
        
        table = Table(table_data)
        
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        
        table.setStyle(style)
        elements.append(table)
        
        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
    
    except Exception as e:
        st.error(f"Error generating PDF: {str(e)}")
        return None

def reset_filter_session_state_after_deletion():
    """Reset filter session state after deletion to prevent multiselect errors"""
    # Reset multiselect filters to only include values that still exist
    df = load_plot_data().fillna("")
    
    # Update sector filter
    if 'sector_filter' in st.session_state:
        all_sectors = sorted([str(s) for s in df["Sector"].dropna().unique() if s and str(s).strip() != ""])
        st.session_state.sector_filter = [s for s in st.session_state.sector_filter if s in all_sectors]
    
    # Update plot size filter
    if 'plot_size_filter' in st.session_state:
        all_plot_sizes = sorted([str(s) for s in df["Plot Size"].dropna().unique() if s and str(s).strip() != ""])
        st.session_state.plot_size_filter = [s for s in st.session_state.plot_size_filter if s in all_plot_sizes]
    
    # Update features filter
    if 'selected_features' in st.session_state:
        all_features = get_all_unique_features(df)
        st.session_state.selected_features = [f for f in st.session_state.selected_features if f in all_features]

def get_dealer_groups(df):
    """Create dealer groups based on unique combinations of Sender Number, Sender Name, Extracted Contact, Extracted Name"""
    if df.empty:
        return [], {}
    
    # Create a copy to avoid modifying original
    df_copy = df.copy()
    
    # Clean and normalize the grouping columns
    grouping_cols = ["Sender Number", "Sender Name", "Extracted Contact", "Extracted Name"]
    
    # Check which grouping columns exist in the dataframe
    available_cols = [col for col in grouping_cols if col in df_copy.columns]
    
    if not available_cols:
        return [], {}
    
    # Fill NaN with empty string and strip whitespace
    for col in available_cols:
        df_copy[col] = df_copy[col].fillna("").astype(str).str.strip()
    
    # Create a group key based on unique combination of available columns
    def create_group_key(row):
        parts = []
        for col in available_cols:
            parts.append(f"{col}={row[col]}")
        return "|".join(parts)
    
    df_copy["GroupKey"] = df_copy.apply(create_group_key, axis=1)
    
    # Create groups
    groups = {}
    group_info = {}
    
    for group_key, group_df in df_copy.groupby("GroupKey"):
        # Count listings in this group
        count = len(group_df)
        
        # Get representative values for display
        first_row = group_df.iloc[0]
        
        # Determine display name
        display_name = ""
        if "Extracted Name" in available_cols and first_row["Extracted Name"]:
            display_name = first_row["Extracted Name"]
        elif "Sender Name" in available_cols and first_row["Sender Name"]:
            display_name = first_row["Sender Name"]
        elif "Extracted Contact" in available_cols and first_row["Extracted Contact"]:
            display_name = first_row["Extracted Contact"]
        elif "Sender Number" in available_cols and first_row["Sender Number"]:
            display_name = first_row["Sender Number"]
        else:
            display_name = "Unknown"
        
        # Handle duplicate names by appending numbers
        base_name = display_name
        counter = 1
        final_name = base_name
        
        while final_name in groups:
            final_name = f"{base_name}-{counter}"
            counter += 1
        
        # Store group info
        group_info[final_name] = {
            "group_key": group_key,
            "count": count,
            "values": {
                "Extracted Name": first_row.get("Extracted Name", ""),
                "Extracted Contact": first_row.get("Extracted Contact", ""),
                "Sender Name": first_row.get("Sender Name", ""),
                "Sender Number": first_row.get("Sender Number", ""),
            }
        }
        
        # Store group with display name
        groups[final_name] = group_key
    
    # Create dealer names list with count
    dealer_names = []
    for name, info in group_info.items():
        dealer_names.append(f"{name} ({info['count']} listings)")
    
    return dealer_names, group_info

def apply_dealer_filter(df, selected_dealer_groups, dealer_groups_info):
    """Apply dealer filter to dataframe based on selected dealer groups using Exact Matching"""
    if not selected_dealer_groups or not dealer_groups_info or df.empty:
        return df
    
    # Identify the columns used for grouping (must match get_dealer_groups logic)
    grouping_cols = ["Sender Number", "Sender Name", "Extracted Contact", "Extracted Name"]
    available_cols = [col for col in grouping_cols if col in df.columns]
    
    if not available_cols:
        return df

    # Create a normalized temporary dataframe for comparison
    # We must replicate the exact same normalization used in get_dealer_groups
    df_norm = df.copy()
    for col in available_cols:
        df_norm[col] = df_norm[col].fillna("").astype(str).str.strip()
    
    # Initialize a mask for all rows (start with all False)
    final_mask = pd.Series(False, index=df.index)
    has_active_filter = False
    
    for dealer_display in selected_dealer_groups:
        if dealer_display in dealer_groups_info:
            group_info = dealer_groups_info[dealer_display]
            values = group_info["values"]
            
            # Start with a mask of True for this specific dealer group
            dealer_mask = pd.Series(True, index=df.index)
            
            # Iterate through available columns and enforce EXACT match
            # This ensures we get exactly the rows that formed this group
            for col in available_cols:
                # Get the value that defined this group (default to empty string if missing in info)
                target_val = str(values.get(col, "")).strip()
                
                # AND condition: The row must match this column's value
                dealer_mask = dealer_mask & (df_norm[col] == target_val)
            
            # Combine this dealer's rows with the accumulated result using OR
            final_mask = final_mask | dealer_mask
            has_active_filter = True
    
    # If we successfully built a filter mask, apply it
    if has_active_filter:
        return df[final_mask]
    
    return df

def show_plots_manager():
    st.header("🏠 Plots Management")
    
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    sold_df = load_sold_data()
    hold_df = load_hold_data().fillna("")
    
    if not contacts_df.empty:
        contacts_df["SheetRowNum"] = [i + 2 for i in range(len(contacts_df))]
    
    # Initialize session state
    if 'selected_rows' not in st.session_state:
        st.session_state.selected_rows = []
    if 'edit_mode' not in st.session_state:
        st.session_state.edit_mode = False
    if 'editing_row' not in st.session_state:
        st.session_state.editing_row = None
    if 'editing_table' not in st.session_state:
        st.session_state.editing_table = None
    if 'filters_reset' not in st.session_state:
        st.session_state.filters_reset = False
    if 'last_filter_state' not in st.session_state:
        st.session_state.last_filter_state = {}

    current_filters = {}

    with st.sidebar:
        st.markdown("""
        <div class='custom-card'>
            <h3>🔍 Filters</h3>
        </div>
        """, unsafe_allow_html=True)
        
        # Get current available options
        all_sectors = sorted([str(s) for s in df["Sector"].dropna().unique() if s and str(s).strip() != ""])
        all_plot_sizes = sorted([str(s) for s in df["Plot Size"].dropna().unique() if s and str(s).strip() != ""])
        
        # Initialize or fix session state for multiselect filters
        if 'sector_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.sector_filter = []
        else:
            # Ensure session state only contains valid sectors
            st.session_state.sector_filter = [s for s in st.session_state.sector_filter if s in all_sectors]
        
        if 'plot_size_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.plot_size_filter = []
        else:
            # Ensure session state only contains valid plot sizes
            st.session_state.plot_size_filter = [s for s in st.session_state.plot_size_filter if s in all_plot_sizes]
        
        # Sector filter with safe defaults
        sector_filter = st.multiselect(
            "Sector", 
            options=all_sectors,
            default=st.session_state.sector_filter,
            key="sector_filter_input"
        )
        current_filters['sector_filter'] = sector_filter
        
        # Plot size filter with safe defaults
        plot_size_filter = st.multiselect(
            "Plot Size", 
            options=all_plot_sizes,
            default=st.session_state.plot_size_filter,
            key="plot_size_filter_input"
        )
        current_filters['plot_size_filter'] = plot_size_filter
        
        if 'street_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.street_filter = ""
        street_filter = st.text_input("Street No", value=st.session_state.street_filter, key="street_filter_input")
        current_filters['street_filter'] = street_filter
        
        if 'plot_no_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.plot_no_filter = ""
        plot_no_filter = st.text_input("Plot No", value=st.session_state.plot_no_filter, key="plot_no_filter_input")
        current_filters['plot_no_filter'] = plot_no_filter
        
        if 'contact_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.contact_filter = ""
        contact_filter = st.text_input("Phone Number", value=st.session_state.contact_filter, key="contact_filter_input")
        current_filters['contact_filter'] = contact_filter
        
        col1, col2 = st.columns(2)
        with col1:
            if 'price_from' not in st.session_state or st.session_state.filters_reset:
                st.session_state.price_from = 0.0
            price_from = st.number_input("Price From (in Lacs)", min_value=0.0, value=st.session_state.price_from, step=1.0, key="price_from_input")
            current_filters['price_from'] = price_from
        
        with col2:
            if 'price_to' not in st.session_state or st.session_state.filters_reset:
                st.session_state.price_to = 1000.0
            price_to = st.number_input("Price To (in Lacs)", min_value=0.0, value=st.session_state.price_to, step=1.0, key="price_to_input")
            current_filters['price_to'] = price_to
        
        all_features = get_all_unique_features(df)
        
        if 'selected_features' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_features = []
        else:
            # Ensure session state only contains valid features
            st.session_state.selected_features = [f for f in st.session_state.selected_features if f in all_features]
            
        selected_features = st.multiselect("Select Feature(s)", options=all_features, default=st.session_state.selected_features, key="features_input")
        current_filters['selected_features'] = selected_features
        
        if 'date_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.date_filter = "All"
        date_filter = st.selectbox("Date Range", ["All", "Last 1 Day", "Last 3 Days", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"], index=["All", "Last 1 Day", "Last 3 Days", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"].index(st.session_state.date_filter), key="date_filter_input")
        current_filters['date_filter'] = date_filter

        prop_type_options = ["All"]
        if "Property Type" in df.columns:
            prop_type_options += sorted([str(v).strip() for v in df["Property Type"].dropna().astype(str).unique() if v and str(v).strip() != ""])
        
        if 'selected_prop_type' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_prop_type = "All"
        selected_prop_type = st.selectbox("Property Type", prop_type_options, index=prop_type_options.index(st.session_state.selected_prop_type) if st.session_state.selected_prop_type in prop_type_options else 0, key="prop_type_input")
        current_filters['selected_prop_type'] = selected_prop_type

        if 'missing_contact_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.missing_contact_filter = False
        missing_contact_filter = st.checkbox("Show listings with missing contact/name", value=st.session_state.missing_contact_filter, key="missing_contact_filter_input")
        current_filters['missing_contact_filter'] = missing_contact_filter

        # Get dealer groups from ALL data (not filtered)
        dealer_names, dealer_groups_info = get_dealer_groups(df)
        
        if 'selected_dealer' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_dealer = []
        
        # Convert selected dealer to list for multiselect
        selected_dealer_current = st.session_state.selected_dealer
        if not isinstance(selected_dealer_current, list):
            # Convert string to list if it's not already a list
            selected_dealer_current = [selected_dealer_current] if selected_dealer_current else []
        
        # Filter out any dealers that no longer exist
        selected_dealer_current = [d for d in selected_dealer_current if d in dealer_names]
        
        selected_dealer = st.multiselect(
            f"Dealer Name (by contact) - {len(dealer_names)} groups found", 
            options=dealer_names,
            default=selected_dealer_current,
            key="dealer_input"
        )
        current_filters['selected_dealer'] = selected_dealer

        # Get contact_to_name mapping for backward compatibility with other parts of the code
        dealer_names_old, contact_to_name = get_dynamic_dealer_names(df, current_filters)
        
        if dealer_names_old and contact_to_name:
            if st.button("📄 Download Dealer Contacts PDF", width='stretch'):
                pdf_data = generate_dealer_contacts_pdf(dealer_names_old, contact_to_name, contacts_df)
                if pdf_data:
                    st.download_button(label="⬇️ Download PDF Now", data=pdf_data, file_name="dealer_contacts.pdf", mime="application/pdf", width='stretch')

        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique()) if not contacts_df.empty else [""]
        
        if st.session_state.get("selected_contact"):
            st.session_state.selected_saved = st.session_state.selected_contact
            st.session_state.selected_contact = None
        
        if 'selected_saved' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_saved = ""
        selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names, index=contact_names.index(st.session_state.selected_saved) if st.session_state.selected_saved in contact_names else 0, key="saved_contact_input")
        current_filters['selected_saved'] = selected_saved
        
        filters_changed = current_filters != st.session_state.last_filter_state
        if filters_changed:
            st.session_state.last_filter_state = current_filters.copy()
            st.rerun()
        
        if st.button("🔄 Reset All Filters", width='stretch', key="reset_filters_btn"):
            st.session_state.sector_filter = []
            st.session_state.plot_size_filter = []
            st.session_state.street_filter = ""
            st.session_state.plot_no_filter = ""
            st.session_state.contact_filter = ""
            st.session_state.price_from = 0.0
            st.session_state.price_to = 1000.0
            st.session_state.selected_features = []
            st.session_state.date_filter = "All"
            st.session_state.selected_prop_type = "All"
            st.session_state.missing_contact_filter = False
            st.session_state.selected_dealer = []
            st.session_state.selected_saved = ""
            st.session_state.filters_reset = True
            st.session_state.last_filter_state = {}
            st.rerun()
        else:
            st.session_state.filters_reset = False
    
    st.session_state.sector_filter = current_filters['sector_filter']
    st.session_state.plot_size_filter = current_filters['plot_size_filter']
    st.session_state.street_filter = current_filters['street_filter']
    st.session_state.plot_no_filter = current_filters['plot_no_filter']
    st.session_state.contact_filter = current_filters['contact_filter']
    st.session_state.price_from = current_filters['price_from']
    st.session_state.price_to = current_filters['price_to']
    st.session_state.selected_features = current_filters['selected_features']
    st.session_state.date_filter = current_filters['date_filter']
    st.session_state.selected_prop_type = current_filters['selected_prop_type']
    st.session_state.missing_contact_filter = current_filters['missing_contact_filter']
    st.session_state.selected_dealer = current_filters['selected_dealer']
    st.session_state.selected_saved = current_filters['selected_saved']

    if st.session_state.edit_mode and st.session_state.editing_row is not None:
        show_edit_form(st.session_state.editing_row, st.session_state.editing_table)

    # Display dealer contact info if dealers are selected
    if st.session_state.selected_dealer:
        st.info(f"**📞 Selected Dealers ({len(st.session_state.selected_dealer)}):**")
        
        for dealer_display in st.session_state.selected_dealer:
            # Extract base dealer name (without count)
            dealer_base_name = re.sub(r'\s*\(\d+\s*listings\)$', '', dealer_display)
            
            if dealer_display in dealer_groups_info:
                group_info = dealer_groups_info[dealer_display]
                values = group_info["values"]
                
                # Show available contact information
                contact_info = []
                if values.get("Extracted Contact"):
                    contact_info.append(f"Extracted Contact: {values['Extracted Contact']}")
                if values.get("Sender Number"):
                    contact_info.append(f"Sender Number: {values['Sender Number']}")
                if values.get("Extracted Name"):
                    contact_info.append(f"Extracted Name: {values['Extracted Name']}")
                if values.get("Sender Name"):
                    contact_info.append(f"Sender Name: {values['Sender Name']}")
                
                if contact_info:
                    st.write(f"**{dealer_base_name}**: " + " | ".join(contact_info))

    # Start with ALL data
    df_filtered = df.copy()

    # Apply dealer filter if selected - FIRST FILTER to be applied
    if st.session_state.selected_dealer:
        df_filtered = apply_dealer_filter(df_filtered, st.session_state.selected_dealer, dealer_groups_info)

    # Apply saved contact filter
    if st.session_state.selected_saved:
        row = contacts_df[contacts_df["Name"] == st.session_state.selected_saved].iloc[0] if not contacts_df.empty and not contacts_df[contacts_df["Name"] == st.session_state.selected_saved].empty else None
        selected_contacts = []
        if row is not None:
            for col in ["Contact1", "Contact2", "Contact3"]:
                if col in row and pd.notna(row[col]):
                    selected_contacts.extend(extract_numbers(str(row[col])))
        if selected_contacts:
            df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(lambda x: any(n in clean_number(str(x)) for n in selected_contacts))]

    # Apply other filters
    if st.session_state.sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].isin(st.session_state.sector_filter)]
    
    if st.session_state.plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].isin(st.session_state.plot_size_filter)]
    
    if st.session_state.street_filter:
        street_pattern = re.compile(re.escape(st.session_state.street_filter), re.IGNORECASE)
        df_filtered = df_filtered[df_filtered["Street No"].apply(lambda x: bool(street_pattern.search(str(x))))]
    
    if st.session_state.plot_no_filter:
        plot_pattern = re.compile(re.escape(st.session_state.plot_no_filter), re.IGNORECASE)
        df_filtered = df_filtered[df_filtered["Plot No"].apply(lambda x: bool(plot_pattern.search(str(x))))]
    
    if st.session_state.contact_filter:
        cnum = clean_number(st.session_state.contact_filter)
        df_filtered = df_filtered[df_filtered["Extracted Contact"].astype(str).apply(lambda x: any(cnum == clean_number(p) for p in x.split(",")))]

    if "Property Type" in df_filtered.columns and st.session_state.selected_prop_type and st.session_state.selected_prop_type != "All":
        df_filtered = df_filtered[df_filtered["Property Type"].astype(str).str.strip() == st.session_state.selected_prop_type]

    if not st.session_state.missing_contact_filter:
        df_filtered = df_filtered[
            ~(df_filtered["Extracted Contact"].isna() | (df_filtered["Extracted Contact"] == "")) | 
            ~(df_filtered["Extracted Name"].isna() | (df_filtered["Extracted Name"] == ""))
        ]

    df_filtered["ParsedPrice"] = df_filtered["Demand"].apply(parse_price)
    if "ParsedPrice" in df_filtered.columns:
        df_filtered_with_price = df_filtered[df_filtered["ParsedPrice"].notnull()]
        if not df_filtered_with_price.empty:
            df_filtered = df_filtered_with_price[(df_filtered_with_price["ParsedPrice"] >= st.session_state.price_from) & (df_filtered_with_price["ParsedPrice"] <= st.session_state.price_to)]

    if st.session_state.selected_features:
        df_filtered = df_filtered[df_filtered["Features"].apply(lambda x: fuzzy_feature_match(x, st.session_state.selected_features))]

    df_filtered = filter_by_date(df_filtered, st.session_state.date_filter)
    df_filtered = sort_dataframe_with_i15_street_no(df_filtered)

    if "Timestamp" in df_filtered.columns:
        cols = [col for col in df_filtered.columns if col != "Timestamp"] + ["Timestamp"]
        df_filtered = df_filtered[cols]

    display_main_table = df_filtered.copy()
    i15_sectors = ["I-15", "I-15/1", "I-15/2", "I-15/3", "I-15/4"]
    
    def is_valid_listing(row):
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No", "")).strip()
        plot_size = str(row.get("Plot Size", "")).strip()
        demand = str(row.get("Demand", "")).strip()
        street_no = str(row.get("Street No", "")).strip()
        
        if not (sector and plot_no and plot_size and demand):
            return False
        if any(i15_sector in sector for i15_sector in i15_sectors):
            return bool(street_no)
        return True
    
    display_main_table = display_main_table[display_main_table.apply(is_valid_listing, axis=1)]

    st.subheader("📋 Filtered Listings")
    
    if not display_main_table.empty:
        csv_data = display_main_table.to_csv(index=False)
        st.download_button(label="📥 Download Filtered Listings as CSV", data=csv_data, file_name=f"filtered_listings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv", key="download_csv")
    
    whatsapp_eligible_count = 0
    for _, row in df_filtered.iterrows():
        sector = str(row.get("Sector", "")).strip()
        plot_no = str(row.get("Plot No", "")).strip()
        size = str(row.get("Plot Size", "")).strip()
        price = str(row.get("Demand", "")).strip()
        street = str(row.get("Street No", "")).strip()
        contact = str(row.get("Extracted Contact", "")).strip()
        name = str(row.get("Extracted Name", "")).strip()
        
        if not (sector and plot_no and size and price):
            continue
        if "I-15/" in sector and not street:
            continue
        if "series" in plot_no.lower():
            continue
        if "offer required" in price.lower():
            continue
        if not contact and not name:
            continue
            
        whatsapp_eligible_count += 1
    
    st.info(f"📊 **Total filtered listings:** {len(display_main_table)} | ✅ **WhatsApp eligible:** {whatsapp_eligible_count}")
    
    if not display_main_table.empty:
        display_table_with_actions(display_main_table, "Main", height=300, show_hold_button=True)
    else:
        st.info("No listings match your filters")
    
    st.markdown("---")
    st.subheader("⏸️ Listings on Hold")
    
    hold_df_filtered = hold_df.copy()
    
    # Apply dealer filter to hold data if selected
    if st.session_state.selected_dealer:
        hold_df_filtered = apply_dealer_filter(hold_df_filtered, st.session_state.selected_dealer, dealer_groups_info)
    
    if st.session_state.sector_filter and "Sector" in hold_df_filtered.columns:
        hold_df_filtered = hold_df_filtered[hold_df_filtered["Sector"].isin(st.session_state.sector_filter)]
    
    if st.session_state.plot_size_filter and "Plot Size" in hold_df_filtered.columns:
        hold_df_filtered = hold_df_filtered[hold_df_filtered["Plot Size"].isin(st.session_state.plot_size_filter)]
    
    if st.session_state.street_filter and "Street No" in hold_df_filtered.columns:
        street_pattern = re.compile(re.escape(st.session_state.street_filter), re.IGNORECASE)
        hold_df_filtered = hold_df_filtered[hold_df_filtered["Street No"].apply(lambda x: bool(street_pattern.search(str(x))))]
    
    if st.session_state.plot_no_filter and "Plot No" in hold_df_filtered.columns:
        plot_pattern = re.compile(re.escape(st.session_state.plot_no_filter), re.IGNORECASE)
        hold_df_filtered = hold_df_filtered[hold_df_filtered["Plot No"].apply(lambda x: bool(plot_pattern.search(str(x))))]
    
    if not st.session_state.missing_contact_filter:
        if "Extracted Contact" in hold_df_filtered.columns and "Extracted Name" in hold_df_filtered.columns:
            hold_df_filtered = hold_df_filtered[
                ~(hold_df_filtered["Extracted Contact"].isna() | (hold_df_filtered["Extracted Contact"] == "")) | 
                ~(hold_df_filtered["Extracted Name"].isna() | (hold_df_filtered["Extracted Name"] == ""))
            ]
    
    hold_df_filtered = sort_dataframe_with_i15_street_no(hold_df_filtered)
    
    if not hold_df_filtered.empty:
        st.info(f"Showing {len(hold_df_filtered)} listings on hold matching your filters")
        display_table_with_actions(hold_df_filtered, "Hold", height=300, show_hold_button=False)
    else:
        st.info("No listings on hold match your filters")
    
    st.markdown("---")
    st.subheader("🆕 Today's Unique Listings")
    
    todays_unique_listings = get_todays_unique_listings(df)
    
    if not todays_unique_listings.empty:
        todays_unique_filtered = todays_unique_listings.copy()
        
        # Apply dealer filter to today's unique listings if selected
        if st.session_state.selected_dealer:
            todays_unique_filtered = apply_dealer_filter(todays_unique_filtered, st.session_state.selected_dealer, dealer_groups_info)
        
        if st.session_state.sector_filter:
            todays_unique_filtered = todays_unique_filtered[todays_unique_filtered["Sector"].isin(st.session_state.sector_filter)]
        
        if not st.session_state.missing_contact_filter:
            todays_unique_filtered = todays_unique_filtered[
                ~(todays_unique_filtered["Extracted Contact"].isna() | (todays_unique_filtered["Extracted Contact"] == "")) | 
                ~(todays_unique_filtered["Extracted Name"].isna() | (todays_unique_filtered["Extracted Name"] == ""))
            ]
        
        todays_unique_filtered = sort_dataframe_with_i15_street_no(todays_unique_filtered)
        st.info(f"Found {len(todays_unique_filtered)} unique listings added today with new Sector & Plot No combinations")
        display_table_with_actions(todays_unique_filtered, "Today_Unique", height=300, show_hold_button=True)
    else:
        st.info("No unique listings found for today")
    
    st.markdown("---")
    st.subheader("📅 This Week's Unique Listings")
    
    weeks_unique_listings = get_this_weeks_unique_listings(df)
    
    if not weeks_unique_listings.empty:
        weeks_unique_filtered = weeks_unique_listings.copy()
        
        # Apply dealer filter to this week's unique listings if selected
        if st.session_state.selected_dealer:
            weeks_unique_filtered = apply_dealer_filter(weeks_unique_filtered, st.session_state.selected_dealer, dealer_groups_info)
        
        if st.session_state.sector_filter:
            weeks_unique_filtered = weeks_unique_filtered[weeks_unique_filtered["Sector"].isin(st.session_state.sector_filter)]
        
        if not st.session_state.missing_contact_filter:
            weeks_unique_filtered = weeks_unique_filtered[
                ~(weeks_unique_filtered["Extracted Contact"].isna() | (weeks_unique_filtered["Extracted Contact"] == "")) | 
                ~(weeks_unique_filtered["Extracted Name"].isna() | (weeks_unique_filtered["Extracted Name"] == ""))
            ]
        
        weeks_unique_filtered = sort_dataframe_with_i15_street_no(weeks_unique_filtered)
        st.info(f"Found {len(weeks_unique_filtered)} unique listings added in the last 7 days with new Sector & Plot No combinations")
        display_table_with_actions(weeks_unique_filtered, "Week_Unique", height=300, show_hold_button=True)
    else:
        st.info("No unique listings found for this week")
    
    # Dealer-specific duplicates section (only show if exactly one dealer is selected)
    if st.session_state.selected_dealer and len(st.session_state.selected_dealer) == 1:
        st.markdown("---")
        st.subheader("👥 Dealer-Specific Duplicates")
        
        # Get the single selected dealer
        selected_dealer_display = st.session_state.selected_dealer[0]
        dealer_base_name = re.sub(r'\s*\(\d+\s*listings\)$', '', selected_dealer_display)
        
        if selected_dealer_display in dealer_groups_info:
            group_info = dealer_groups_info[selected_dealer_display]
            values = group_info["values"]
            
            # Get all contacts from this dealer group
            dealer_contacts = []
            if values.get("Extracted Contact"):
                contacts = extract_numbers(values["Extracted Contact"])
                dealer_contacts.extend(contacts)
            if values.get("Sender Number"):
                contacts = extract_numbers(values["Sender Number"])
                dealer_contacts.extend(contacts)
            
            dealer_contacts = list(set(dealer_contacts))
            
            styled_dealer_duplicates, dealer_duplicates_df = create_dealer_specific_duplicates_view(df, dealer_contacts)
            
            if not st.session_state.missing_contact_filter and not dealer_duplicates_df.empty:
                dealer_duplicates_df = dealer_duplicates_df[
                    ~(dealer_duplicates_df["Extracted Contact"].isna() | (dealer_duplicates_df["Extracted Contact"] == "")) | 
                    ~(dealer_duplicates_df["Extracted Name"].isna() | (dealer_duplicates_df["Extracted Name"] == ""))
                ]
            
            if not dealer_duplicates_df.empty:
                st.info(f"Showing duplicate listings for dealer **{dealer_base_name}** - matching Sector, Plot No, Street No, Plot Size but different Contacts/Names")
                
                # --- FIX: Avoid rendering HTML if None is returned (Too many rows) ---
                if styled_dealer_duplicates is not None:
                    st.markdown("**Color Grouped View (Read-only)**")
                    try:
                        styled_html = styled_dealer_duplicates.to_html()
                        st.markdown(f'<div style="height: 400px; overflow: auto; border: 1px solid #e6e9ef; border-radius: 0.5rem;">{styled_html}</div>', unsafe_allow_html=True)
                    except:
                        st.warning("Preview too large to render with colors.")
                
                st.markdown("---")
                st.markdown("**Actionable View (With Checkboxes)**")
                dealer_duplicates_df = sort_dataframe_with_i15_street_no(dealer_duplicates_df)
                display_table_with_actions(dealer_duplicates_df, "Dealer_Duplicates", height=400, show_hold_button=True)
            else:
                st.info(f"No dealer-specific duplicates found for **{dealer_base_name}**")
    
    st.markdown("---")
    st.subheader("✅ Sold Listings (Filtered)")
    
    sold_df_filtered = sold_df.copy()
    
    # Apply dealer filter to sold listings if selected
    if st.session_state.selected_dealer:
        sold_df_filtered = apply_dealer_filter(sold_df_filtered, st.session_state.selected_dealer, dealer_groups_info)
    
    if st.session_state.sector_filter and "Sector" in sold_df_filtered.columns:
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Sector"].isin(st.session_state.sector_filter)]
    
    if st.session_state.plot_size_filter and "Plot Size" in sold_df_filtered.columns:
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Plot Size"].isin(st.session_state.plot_size_filter)]
    
    if st.session_state.street_filter and "Street No" in sold_df_filtered.columns:
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Street No"].str.contains(st.session_state.street_filter, case=False, na=False)]
    
    if st.session_state.plot_no_filter and "Plot No" in sold_df_filtered.columns:
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Plot No"].str.contains(st.session_state.plot_no_filter, case=False, na=False)]
    
    if "Property Type" in sold_df_filtered.columns and st.session_state.selected_prop_type and st.session_state.selected_prop_type != "All":
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Property Type"].astype(str).str.strip() == st.session_state.selected_prop_type]
    
    if not st.session_state.missing_contact_filter:
        if "Extracted Contact" in sold_df_filtered.columns and "Extracted Name" in sold_df_filtered.columns:
            sold_df_filtered = sold_df_filtered[
                ~(sold_df_filtered["Extracted Contact"].isna() | (sold_df_filtered["Extracted Contact"] == "")) | 
                ~(sold_df_filtered["Extracted Name"].isna() | (sold_df_filtered["Extracted Name"] == ""))
            ]
    
    sold_df_filtered = sort_dataframe_with_i15_street_no(sold_df_filtered)
    
    if not sold_df_filtered.empty:
        st.info(f"Showing {len(sold_df_filtered)} sold listings matching your filters")
        display_table_with_actions(sold_df_filtered, "Sold", height=300, show_hold_button=True)
    else:
        st.info("No sold listings match your filters")
    
    st.markdown("---")
    st.subheader("❌ Incomplete Listings")
    
    incomplete_df_filtered = df_filtered.copy()
    
    if not incomplete_df_filtered.empty:
        incomplete_listings = []
        for _, row in incomplete_df_filtered.iterrows():
            sector = str(row.get("Sector", "")).strip()
            plot_no = str(row.get("Plot No", "")).strip()
            size = str(row.get("Plot Size", "")).strip()
            price = str(row.get("Demand", "")).strip()
            street = str(row.get("Street No", "")).strip()
            contact = str(row.get("Extracted Contact", "")).strip()
            name = str(row.get("Extracted Name", "")).strip()
            
            missing_fields = []
            if not sector:
                missing_fields.append("Sector")
            if not plot_no:
                missing_fields.append("Plot No")
            if not size:
                missing_fields.append("Plot Size")
            if not price:
                missing_fields.append("Demand")
            if "I-15/" in sector and not street:
                missing_fields.append("Street No")
            if "series" in plot_no.lower():
                missing_fields.append("Valid Plot No (contains 'series')")
            if "offer required" in price.lower():
                missing_fields.append("Valid Demand (contains 'offer required')")
            if not contact and not name:
                missing_fields.append("Both Contact and Name are empty")
            
            if missing_fields:
                row_dict = row.to_dict()
                row_dict["Missing Fields"] = ", ".join(missing_fields)
                incomplete_listings.append(row_dict)
        
        incomplete_df = pd.DataFrame(incomplete_listings)
        
        if not incomplete_df.empty:
            incomplete_df["Extracted Name"] = incomplete_df["Extracted Name"].fillna("")
            incomplete_df = incomplete_df.sort_values(by="Extracted Name")
            incomplete_df = sort_dataframe_with_i15_street_no(incomplete_df)
        
        if not incomplete_df.empty:
            st.info(f"Found {len(incomplete_df)} listings with missing information")
            display_table_with_actions(incomplete_df, "Incomplete", height=300, show_hold_button=True)
        else:
            st.info("🎉 All filtered listings have complete information!")
    else:
        st.info("No listings available to check for completeness")
    
    st.markdown("---")
    st.subheader("👥 Duplicate Listings Detection")
    
    if not df_filtered.empty:
        # Use existing utility but wrapped safely
        try:
            styled_duplicates_df, duplicates_df = create_duplicates_view_updated(df_filtered)
            # --- FIX: If dataset is too large, drop style to prevent crash ---
            if len(duplicates_df) > 50:
                styled_duplicates_df = None
        except:
            styled_duplicates_df, duplicates_df = None, pd.DataFrame()

        if not st.session_state.missing_contact_filter and not duplicates_df.empty:
            duplicates_df = duplicates_df[
                ~(duplicates_df["Extracted Contact"].isna() | (duplicates_df["Extracted Contact"] == "")) | 
                ~(duplicates_df["Extracted Name"].isna() | (duplicates_df["Extracted Name"] == ""))
            ]
        
        if duplicates_df.empty:
            st.info("No duplicate listings found")
        else:
            st.info("Showing duplicate listings with matching Sector, Plot No, Street No, Plot Size but different Contact/Name/Demand")
            
            if styled_duplicates_df is not None:
                st.markdown("**Color Grouped View (Read-only)**")
                try:
                    styled_html = styled_duplicates_df.to_html()
                    st.markdown(f'<div style="height: 400px; overflow: auto; border: 1px solid #e6e9ef; border-radius: 0.5rem;">{styled_html}</div>', unsafe_allow_html=True)
                except:
                    st.warning("Preview too large to render with colors.")
            
            st.markdown("---")
            st.markdown("**Actionable View (With Checkboxes)**")
            duplicates_df = sort_dataframe_with_i15_street_no(duplicates_df)
            display_table_with_actions(duplicates_df, "Duplicates", height=400, show_hold_button=True)
    else:
        st.info("No listings to analyze for duplicates")

    st.markdown("---")
    st.subheader("📤 Send WhatsApp Message")

    selected_name_whatsapp = st.selectbox("📱 Select Contact to Message", contact_names, key="wa_contact")
    manual_number = st.text_input("Or Enter WhatsApp Number (e.g. 0300xxxxxxx)")

    if st.button("Generate WhatsApp Message", width='stretch'):
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
            st.stop()

        if len(cleaned) == 10 and cleaned.startswith("3"):
            wa_number = "92" + cleaned
        elif len(cleaned) == 11 and cleaned.startswith("03"):
            wa_number = "92" + cleaned[1:]
        elif len(cleaned) == 12 and cleaned.startswith("92"):
            wa_number = cleaned
        else:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
            st.stop()

        messages = generate_whatsapp_messages_with_enhanced_filtering(df_filtered)
        if not messages:
            st.warning("⚠️ No valid listings to include. Listings must have: Sector, Plot No, Size, Price; I-15 must have Street No; No 'series' plots; No 'offer required' in demand; No duplicates with same Sector/Plot No/Street No/Plot Size/Demand.")
        else:
            st.success(f"📨 Generated {len(messages)} WhatsApp message(s)")
            for i, msg in enumerate(messages):
                st.markdown(f"**Message {i+1}** ({len(msg)} characters):")
                st.text_area(f"Preview Message {i+1}", msg, height=150, key=f"msg_preview_{i}")
                encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                link = f"https://wa.me/{wa_number}?text={encoded}"
                st.markdown(f'<a href="{link}" target="_blank" style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #25D366; color: white; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 0.5rem 0;">📩 Send Message {i+1}</a>', unsafe_allow_html=True)
                st.markdown("---")

def generate_whatsapp_messages_with_enhanced_filtering(df):
    """Generate WhatsApp messages with enhanced filtering criteria"""
    if df.empty:
        return []
    
    eligible_listings = []
    
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
        if "offer required" in price.lower():
            continue
            
        eligible_listings.append(row)
    
    if not eligible_listings:
        return []
    
    eligible_df = pd.DataFrame(eligible_listings)
    
    eligible_df["ParsedPrice"] = eligible_df["Demand"].apply(parse_price)
    
    eligible_df["DuplicateKey"] = eligible_df.apply(
        lambda row: f"{str(row.get('Sector', '')).strip().upper()}|{str(row.get('Plot No', '')).strip().upper()}|{str(row.get('Street No', '')).strip().upper()}|{str(row.get('Plot Size', '')).strip().upper()}|{str(row.get('Demand', '')).strip().upper()}", 
        axis=1
    )
    
    filtered_listings = []
    for key, group in eligible_df.groupby("DuplicateKey"):
        if len(group) > 1:
            lowest_price_row = group.loc[group["ParsedPrice"].idxmin()]
            filtered_listings.append(lowest_price_row)
        else:
            filtered_listings.append(group.iloc[0])
    
    final_df = pd.DataFrame(filtered_listings)
    return generate_whatsapp_messages(final_df)

def sort_dataframe_with_i15_street_no(df):
    """Sort dataframe with special handling for I-15 sectors - sort by Street No"""
    if df.empty:
        return df
    
    sorted_df = df.copy()
    
    if "Plot No" in sorted_df.columns:
        sorted_df["Plot_No_Numeric"] = sorted_df["Plot No"].apply(_extract_int)
    
    if "Street No" in sorted_df.columns:
        sorted_df["Street_No_Numeric"] = sorted_df["Street No"].apply(_extract_int)
    
    if "Plot Size" in sorted_df.columns:
        sorted_df["Plot_Size_Numeric"] = sorted_df["Plot Size"].apply(_extract_int)
    
    def get_sort_key(row):
        sector = str(row.get("Sector", "")).strip()
        if sector.startswith("I-15"):
            street_no = _extract_int(row.get("Street No", ""))
            plot_no = _extract_int(row.get("Plot No", ""))
            return (sector, street_no, plot_no)
        else:
            plot_no = _extract_int(row.get("Plot No", ""))
            street_no = _extract_int(row.get("Street No", ""))
            return (sector, plot_no, street_no)
    
    sorted_df["Sort_Key"] = sorted_df.apply(get_sort_key, axis=1)
    
    try:
        sorted_df = sorted_df.sort_values(by="Sort_Key", ascending=True)
    except Exception as e:
        st.warning(f"Could not sort dataframe: {e}")
        return df
    
    sorted_df = sorted_df.drop(columns=["Plot_No_Numeric", "Street_No_Numeric", "Plot_Size_Numeric", "Sort_Key"], errors="ignore")
    return sorted_df

def mark_listings_sold(rows_data):
    """Mark selected listings as sold by moving them to Sold sheet and removing from Plots"""
    try:
        sold_df = load_sold_data()
        
        for row_data in rows_data:
            sold_id = generate_sold_id()
            new_sold_record = {
                "ID": sold_id,
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Sector": row_data.get("Sector", ""),
                "Plot No": row_data.get("Plot No", ""),
                "Street No": row_data.get("Street No", ""),
                "Plot Size": row_data.get("Plot Size", ""),
                "Demand": row_data.get("Demand", ""),
                "Features": row_data.get("Features", ""),
                "Property Type": row_data.get("Property Type", ""),
                "Extracted Name": row_data.get("Extracted Name", ""),
                "Extracted Contact": row_data.get("Extracted Contact", ""),
                "Sale Date": datetime.now().strftime("%Y-%m-%d"),
                "Sale Price": row_data.get("Demand", ""),
                "Commission": "",
                "Agent": "Auto-marked",
                "Notes": "Marked as sold from Plots section",
                "Original Row Num": row_data.get("SheetRowNum", "")
            }
            sold_df = pd.concat([sold_df, pd.DataFrame([new_sold_record])], ignore_index=True)
        
        if save_sold_data(sold_df):
            row_nums = [int(row_data["SheetRowNum"]) for row_data in rows_data]
            if delete_rows_from_sheet(row_nums):
                st.success(f"✅ Successfully marked {len(rows_data)} listing(s) as sold and moved to Sold sheet!")
                st.cache_data.clear()
                # Reset filter session state to prevent multiselect errors
                reset_filter_session_state_after_deletion()
                st.rerun()
            else:
                st.error("❌ Failed to remove listings from plots sheet.")
        else:
            st.error("❌ Failed to save sold data. Please try again.")
            
    except Exception as e:
        st.error(f"❌ Error marking listings as sold: {str(e)}")

def move_listings_to_hold(rows_data, source_table):
    """Move selected listings to Hold sheet"""
    try:
        hold_df = load_hold_data()
        
        for row_data in rows_data:
            new_hold_record = {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Sector": row_data.get("Sector", ""),
                "Plot No": row_data.get("Plot No", ""),
                "Street No": row_data.get("Street No", ""),
                "Plot Size": row_data.get("Plot Size", ""),
                "Demand": row_data.get("Demand", ""),
                "Features": row_data.get("Features", ""),
                "Property Type": row_data.get("Property Type", ""),
                "Extracted Name": row_data.get("Extracted Name", ""),
                "Extracted Contact": row_data.get("Extracted Contact", ""),
                "Hold Date": datetime.now().strftime("%Y-%m-%d"),
                "Hold Reason": f"Moved from {source_table}",
                "Original Row Num": row_data.get("SheetRowNum", "")
            }
            hold_df = pd.concat([hold_df, pd.DataFrame([new_hold_record])], ignore_index=True)
        
        if save_hold_data(hold_df):
            row_nums = [int(row_data["SheetRowNum"]) for row_data in rows_data]
            if move_to_hold(row_nums):
                st.success(f"✅ Successfully moved {len(rows_data)} listing(s) to Hold!")
                st.cache_data.clear()
                # Reset filter session state to prevent multiselect errors
                reset_filter_session_state_after_deletion()
                st.rerun()
            else:
                st.error("❌ Failed to remove listings from original sheet.")
        else:
            st.error("❌ Failed to save hold data. Please try again.")
            
    except Exception as e:
        st.error(f"❌ Error moving listings to hold: {str(e)}")

def move_listings_to_plots(rows_data):
    """Move selected listings from Hold back to Plots sheet"""
    try:
        plot_df = load_plot_data()
        
        for row_data in rows_data:
            new_plot_record = {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Sector": row_data.get("Sector", ""),
                "Plot No": row_data.get("Plot No", ""),
                "Street No": row_data.get("Street No", ""),
                "Plot Size": row_data.get("Plot Size", ""),
                "Demand": row_data.get("Demand", ""),
                "Features": row_data.get("Features", ""),
                "Property Type": row_data.get("Property Type", ""),
                "Extracted Name": row_data.get("Extracted Name", ""),
                "Extracted Contact": row_data.get("Extracted Contact", ""),
                "Original Row Num": row_data.get("SheetRowNum", "")
            }
            plot_df = pd.concat([plot_df, pd.DataFrame([new_plot_record])], ignore_index=True)
        
        if update_plot_data(plot_df):
            row_nums = [int(row_data["SheetRowNum"]) for row_data in rows_data]
            if move_to_plots(row_nums):
                st.success(f"✅ Successfully moved {len(rows_data)} listing(s) back to Available Plots!")
                st.cache_data.clear()
                # Reset filter session state to prevent multiselect errors
                reset_filter_session_state_after_deletion()
                st.rerun()
            else:
                st.error("❌ Failed to remove listings from hold sheet.")
        else:
            st.error("❌ Failed to save plot data. Please try again.")
            
    except Exception as e:
        st.error(f"❌ Error moving listings to plots: {str(e)}")

def show_edit_form(row_data, table_name):
    """Show form to edit a listing"""
    st.markdown("---")
    st.subheader("✏️ Edit Listing")
    
    with st.form("edit_listing_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            sector = st.text_input("Sector", value=row_data.get("Sector", ""))
            plot_no = st.text_input("Plot No", value=row_data.get("Plot No", ""))
            street_no = st.text_input("Street No", value=row_data.get("Street No", ""))
            plot_size = st.text_input("Plot Size", value=row_data.get("Plot Size", ""))
            demand = st.text_input("Demand", value=row_data.get("Demand", ""))
        
        with col2:
            features = st.text_area("Features", value=row_data.get("Features", ""))
            property_type = st.text_input("Property Type", value=row_data.get("Property Type", ""))
            extracted_name = st.text_input("Extracted Name", value=row_data.get("Extracted Name", ""))
            extracted_contact = st.text_input("Extracted Contact", value=row_data.get("Extracted Contact", ""))
        
        submitted = st.form_submit_button("💾 Save Changes")
        cancel = st.form_submit_button("❌ Cancel")
        
        if submitted:
            updated_row = row_data.copy()
            updated_row["Sector"] = sector
            updated_row["Plot No"] = plot_no
            updated_row["Street No"] = street_no
            updated_row["Plot Size"] = plot_size
            updated_row["Demand"] = demand
            updated_row["Features"] = features
            updated_row["Property Type"] = property_type
            updated_row["Extracted Name"] = extracted_name
            updated_row["Extracted Contact"] = extracted_contact
            
            if table_name == "Hold":
                hold_df = load_hold_data()
                row_num = int(row_data.get("SheetRowNum", 0)) - 2
                if 0 <= row_num < len(hold_df):
                    for key, value in updated_row.items():
                        if key in hold_df.columns and key != "SheetRowNum":A
                            hold_df.at[row_num, key] = value
                    if save_hold_data(hold_df):
                        st.success("✅ Hold listing updated successfully!")
                    else:
                        st.error("❌ Failed to update hold listing.")
            else:
                if update_plot_data(updated_row):
                    st.success("✅ Listing updated successfully!")
                else:
                    st.error("❌ Failed to update listing. Please try again.")
            
            st.session_state.edit_mode = False
            st.session_state.editing_row = None
            st.session_state.editing_table = None
            st.cache_data.clear()
            st.rerun()
        
        if cancel:
            st.session_state.edit_mode = False
            st.session_state.editing_row = None
            st.session_state.editing_table = None
            st.rerun()
