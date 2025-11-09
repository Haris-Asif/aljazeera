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
        df_temp = df_temp[df_temp["Sector"].apply(lambda x: sector_matches(filters['sector_filter'], str(x)))]
    
    if filters.get('plot_size_filter'):
        df_temp = df_temp[df_temp["Plot Size"].str.contains(filters['plot_size_filter'], case=False, na=False)]
    
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
    
    # Find all listings that match the dealer's group keys but have different contacts
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
    
    # Create styled version with color grouping - FIXED: Ensure it's a proper Styler
    try:
        groups = duplicates_df["GroupKey"].unique()
        color_mapping = {group: f"hsl({int(i*360/len(groups))}, 70%, 80%)" for i, group in enumerate(groups)}
        
        def color_group(row):
            return [f"background-color: {color_mapping[row['GroupKey']]}"] * len(row)
        
        styled_duplicates_df = duplicates_df.style.apply(color_group, axis=1)
        return styled_duplicates_df, duplicates_df
    except Exception as e:
        # If styling fails, return None for styled version
        return None, duplicates_df

def get_todays_unique_listings(df):
    """Get listings with new combinations of Sector, Plot No, Street No, Plot Size added today"""
    if df.empty:
        return pd.DataFrame()
    
    # Get today's date
    today = datetime.now().date()
    
    # Filter listings from today
    today_listings = df.copy()
    today_listings['Date'] = pd.to_datetime(today_listings['Timestamp']).dt.date
    today_listings = today_listings[today_listings['Date'] == today]
    
    if today_listings.empty:
        return pd.DataFrame()
    
    # Filter listings from before today (all historical data)
    before_today_listings = df.copy()
    before_today_listings['Date'] = pd.to_datetime(before_today_listings['Timestamp']).dt.date
    before_today_listings = before_today_listings[before_today_listings['Date'] < today]
    
    # Create normalized key combinations for comparison (only Sector, Plot No, Street No, Plot Size)
    today_listings["CombinationKey"] = today_listings.apply(
        lambda row: f"{str(row.get('Sector', '')).strip().upper()}|{str(row.get('Plot No', '')).strip().upper()}|{str(row.get('Street No', '')).strip().upper()}|{str(row.get('Plot Size', '')).strip().upper()}", 
        axis=1
    )
    
    before_today_listings["CombinationKey"] = before_today_listings.apply(
        lambda row: f"{str(row.get('Sector', '')).strip().upper()}|{str(row.get('Plot No', '')).strip().upper()}|{str(row.get('Street No', '')).strip().upper()}|{str(row.get('Plot Size', '')).strip().upper()}", 
        axis=1
    )
    
    # Get unique keys from before today (all historical combinations)
    existing_keys = set(before_today_listings["CombinationKey"].unique())
    
    # Filter today's listings to only include new combinations (not seen before in entire dataset)
    unique_today_listings = today_listings[~today_listings["CombinationKey"].isin(existing_keys)]
    
    # Drop the temporary columns
    unique_today_listings = unique_today_listings.drop(["Date", "CombinationKey"], axis=1, errors="ignore")
    
    return unique_today_listings

def get_this_weeks_unique_listings(df):
    """Get listings with new combinations of Sector, Plot No, Street No, Plot Size added in the last 7 days"""
    if df.empty:
        return pd.DataFrame()
    
    # Get dates for this week (last 7 days including today)
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    
    # Filter listings from the last 7 days
    this_week_listings = df.copy()
    this_week_listings['Date'] = pd.to_datetime(this_week_listings['Timestamp']).dt.date
    this_week_listings = this_week_listings[this_week_listings['Date'] >= week_ago]
    
    if this_week_listings.empty:
        return pd.DataFrame()
    
    # Filter listings from before this week (all historical data before this week)
    before_week_listings = df.copy()
    before_week_listings['Date'] = pd.to_datetime(before_week_listings['Timestamp']).dt.date
    before_week_listings = before_week_listings[before_week_listings['Date'] < week_ago]
    
    # Create normalized key combinations for comparison (only Sector, Plot No, Street No, Plot Size)
    this_week_listings["CombinationKey"] = this_week_listings.apply(
        lambda row: f"{str(row.get('Sector', '')).strip().upper()}|{str(row.get('Plot No', '')).strip().upper()}|{str(row.get('Street No', '')).strip().upper()}|{str(row.get('Plot Size', '')).strip().upper()}", 
        axis=1
    )
    
    before_week_listings["CombinationKey"] = before_week_listings.apply(
        lambda row: f"{str(row.get('Sector', '')).strip().upper()}|{str(row.get('Plot No', '')).strip().upper()}|{str(row.get('Street No', '')).strip().upper()}|{str(row.get('Plot Size', '')).strip().upper()}", 
        axis=1
    )
    
    # Get unique keys from before this week (all historical combinations)
    existing_keys = set(before_week_listings["CombinationKey"].unique())
    
    # Filter this week's listings to only include new combinations (not seen before in entire dataset)
    unique_week_listings = this_week_listings[~this_week_listings["CombinationKey"].isin(existing_keys)]
    
    # Drop the temporary columns
    unique_week_listings = unique_week_listings.drop(["Date", "CombinationKey"], axis=1, errors="ignore")
    
    return unique_week_listings

def safe_display_dataframe(df, height=300):
    """Safely display dataframe with error handling for Arrow conversion issues"""
    if df.empty:
        return
    
    try:
        # First try to use safe_dataframe_for_display
        safe_df = safe_dataframe_for_display(df)
        st.dataframe(safe_df, use_container_width=True, height=height)
    except Exception as e:
        try:
            # If that fails, try converting all columns to string
            st.warning("Displaying data as strings due to conversion issues")
            string_df = df.astype(str)
            st.dataframe(string_df, use_container_width=True, height=height)
        except Exception as e2:
            # If all else fails, use table view
            st.error(f"Could not display dataframe properly: {str(e2)}")
            st.table(df.head(50))  # Limit to first 50 rows to prevent overflow

def group_by_extracted_name(df):
    """Group listings by Extracted Name column"""
    if df.empty or "Extracted Name" not in df.columns:
        return df
    
    # Create a copy to avoid modifying original
    grouped_df = df.copy()
    
    # Fill NaN values in Extracted Name with "Unknown"
    grouped_df["Extracted Name"] = grouped_df["Extracted Name"].fillna("Unknown")
    
    # Sort by Extracted Name first, then by other relevant columns
    sort_columns = ["Extracted Name"]
    for col in ["Sector", "Plot No", "Street No", "Plot Size", "Timestamp"]:
        if col in grouped_df.columns:
            sort_columns.append(col)
    
    # Sort the dataframe
    grouped_df = grouped_df.sort_values(by=sort_columns).reset_index(drop=True)
    
    return grouped_df

def display_table_with_actions(df, table_name, height=300, show_hold_button=True):
    """Display dataframe with edit/delete actions for any table - grouped by Extracted Name"""
    if df.empty:
        st.info(f"No data available for {table_name}")
        return
    
    # Group listings by Extracted Name
    grouped_df = group_by_extracted_name(df)
    
    # Create display dataframe with selection
    display_df = grouped_df.copy().reset_index(drop=True)
    display_df.insert(0, "Select", False)
    
    # Ensure all data types are consistent for display
    display_df = safe_dataframe_for_display(display_df)
    
    # Action buttons row - Updated to include Hold button conditionally
    if show_hold_button:
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        with col1:
            select_all = st.checkbox(f"Select All {table_name} Rows", key=f"select_all_{table_name}")
        with col2:
            edit_btn = st.button("✏️ Edit Selected", use_container_width=True, key=f"edit_{table_name}")
        with col3:
            mark_sold_btn = st.button("✅ Mark as Sold", use_container_width=True, key=f"mark_sold_{table_name}")
        with col4:
            hold_btn = st.button("⏸️ Hold", use_container_width=True, key=f"hold_{table_name}")
        with col5:
            delete_btn = st.button("🗑️ Delete Selected", type="primary", use_container_width=True, key=f"delete_{table_name}")
    else:
        # For Hold table, show Move To Available Data button instead of Hold button
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        with col1:
            select_all = st.checkbox(f"Select All {table_name} Rows", key=f"select_all_{table_name}")
        with col2:
            edit_btn = st.button("✏️ Edit Selected", use_container_width=True, key=f"edit_{table_name}")
        with col3:
            mark_sold_btn = st.button("✅ Mark as Sold", use_container_width=True, key=f"mark_sold_{table_name}")
        with col4:
            move_to_available_btn = st.button("🔄 Move To Available", use_container_width=True, key=f"move_available_{table_name}")
        with col5:
            delete_btn = st.button("🗑️ Delete Selected", type="primary", use_container_width=True, key=f"delete_{table_name}")
    
    # Handle select all functionality
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
        width='stretch',
        disabled=display_df.columns.difference(["Select"]).tolist(),
        key=f"{table_name}_data_editor"
    )
    
    # Get selected rows from the edited dataframe
    selected_indices = edited_df[edited_df["Select"]].index.tolist()
    
    # Display selection info
    if selected_indices:
        st.success(f"**{len(selected_indices)} row(s) selected in {table_name}**")
        
        # Handle Edit action - FIXED: Properly show edit form
        if edit_btn:
            if len(selected_indices) == 1:
                st.session_state.edit_mode = True
                st.session_state.editing_row = display_df.iloc[selected_indices[0]].to_dict()
                st.session_state.editing_table = table_name
                st.rerun()
            else:
                st.warning("Please select only one row to edit.")
        
        # Handle Mark as Sold action
        if mark_sold_btn:
            selected_display_rows = [display_df.iloc[idx] for idx in selected_indices]
            mark_listings_sold(selected_display_rows)
        
        # Handle Hold action (only for non-hold tables)
        if show_hold_button and hold_btn:
            selected_display_rows = [display_df.iloc[idx] for idx in selected_indices]
            move_listings_to_hold(selected_display_rows, table_name)
        
        # Handle Move To Available action (only for hold table)
        if not show_hold_button and move_to_available_btn:
            selected_display_rows = [display_df.iloc[idx] for idx in selected_indices]
            move_listings_to_plots(selected_display_rows)
        
        # Handle Delete action
        if delete_btn:
            # Get the actual SheetRowNum values from the selected rows
            selected_display_rows = [display_df.iloc[idx] for idx in selected_indices]
            row_nums = [int(row["SheetRowNum"]) for row in selected_display_rows]
            
            # Show deletion confirmation
            st.warning(f"🗑️ Deleting {len(row_nums)} selected row(s) from {table_name}...")
            
            # Perform deletion
            success = delete_rows_from_sheet(row_nums)
            
            if success:
                st.success(f"✅ Successfully deleted {len(row_nums)} row(s) from {table_name}!")
                # Clear selection and refresh
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("❌ Failed to delete rows. Please try again.")

def mark_listings_sold(selected_rows):
    """Mark selected listings as sold"""
    if not selected_rows:
        return
    
    st.info(f"Marking {len(selected_rows)} listing(s) as sold...")
    
    # Load current sold data
    sold_df = load_sold_data()
    
    # Process each selected row
    for row in selected_rows:
        # Generate sold ID
        sold_id = generate_sold_id()
        
        # Create sold record
        sold_record = {
            "SoldID": sold_id,
            "DateSold": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Sector": row.get("Sector", ""),
            "Plot No": row.get("Plot No", ""),
            "Street No": row.get("Street No", ""),
            "Plot Size": row.get("Plot Size", ""),
            "Demand": row.get("Demand", ""),
            "Extracted Name": row.get("Extracted Name", ""),
            "Extracted Contact": row.get("Extracted Contact", ""),
            "Property Type": row.get("Property Type", ""),
            "Features": row.get("Features", ""),
            "OriginalRowNum": row.get("SheetRowNum", "")
        }
        
        # Add to sold dataframe
        sold_df = pd.concat([sold_df, pd.DataFrame([sold_record])], ignore_index=True)
    
    # Save sold data
    if save_sold_data(sold_df):
        # Delete from main plots data
        row_nums = [int(row["SheetRowNum"]) for row in selected_rows]
        if delete_rows_from_sheet(row_nums):
            st.success(f"✅ Successfully marked {len(selected_rows)} listing(s) as sold!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("❌ Failed to remove listings from main data. Sold records were created but main data cleanup failed.")
    else:
        st.error("❌ Failed to save sold records.")

def move_listings_to_hold(selected_rows, table_name):
    """Move selected listings to hold"""
    if not selected_rows:
        return
    
    st.info(f"Moving {len(selected_rows)} listing(s) to hold...")
    
    # Load current hold data
    hold_df = load_hold_data()
    
    # Process each selected row
    rows_to_move = []
    for row in selected_rows:
        # Create hold record (keep all original data)
        hold_record = row.copy()
        hold_record["HoldDate"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hold_record["OriginalTable"] = table_name
        rows_to_move.append(hold_record)
    
    # Add to hold dataframe
    hold_df = pd.concat([hold_df, pd.DataFrame(rows_to_move)], ignore_index=True)
    
    # Save hold data
    if save_hold_data(hold_df):
        # Delete from source data
        row_nums = [int(row["SheetRowNum"]) for row in selected_rows]
        if delete_rows_from_sheet(row_nums):
            st.success(f"✅ Successfully moved {len(selected_rows)} listing(s) to hold!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("❌ Failed to remove listings from source data. Hold records were created but source data cleanup failed.")
    else:
        st.error("❌ Failed to save hold records.")

def move_listings_to_plots(selected_rows):
    """Move selected listings from hold back to plots"""
    if not selected_rows:
        return
    
    st.info(f"Moving {len(selected_rows)} listing(s) back to available data...")
    
    # Load current plots data
    plots_df = load_plot_data()
    
    # Process each selected row
    rows_to_move = []
    for row in selected_rows:
        # Create plots record (remove hold-specific fields)
        plots_record = {k: v for k, v in row.items() if k not in ["HoldDate", "OriginalTable"]}
        rows_to_move.append(plots_record)
    
    # Add to plots dataframe
    plots_df = pd.concat([plots_df, pd.DataFrame(rows_to_move)], ignore_index=True)
    
    # Save plots data
    if update_plot_data(plots_df):
        # Delete from hold data
        row_nums = [int(row["SheetRowNum"]) for row in selected_rows]
        if move_to_plots(row_nums):  # This function should handle deletion from hold
            st.success(f"✅ Successfully moved {len(selected_rows)} listing(s) back to available data!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("❌ Failed to remove listings from hold data. Plots records were created but hold data cleanup failed.")
    else:
        st.error("❌ Failed to save plots records.")

def show_plots_manager():
    st.header("🏠 Plots Management")
    
    # Load data
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    sold_df = load_sold_data()
    hold_df = load_hold_data().fillna("")
    
    # Group all dataframes by Extracted Name
    df = group_by_extracted_name(df)
    sold_df = group_by_extracted_name(sold_df)
    hold_df = group_by_extracted_name(hold_df)
    
    # Add row numbers to contacts for deletion
    if not contacts_df.empty:
        contacts_df["SheetRowNum"] = [i + 2 for i in range(len(contacts_df))]
    
    # Initialize session state for selected rows
    if 'selected_rows' not in st.session_state:
        st.session_state.selected_rows = []
    if 'edit_mode' not in st.session_state:
        st.session_state.edit_mode = False
    if 'editing_row' not in st.session_state:
        st.session_state.editing_row = None
    if 'editing_table' not in st.session_state:
        st.session_state.editing_table = None
    
    # Initialize session state for filters
    if 'filters_reset' not in st.session_state:
        st.session_state.filters_reset = False
    if 'last_filter_state' not in st.session_state:
        st.session_state.last_filter_state = {}

    # Collect current filter values for dynamic dealer update
    current_filters = {}

    # Sidebar Filters with modern styling
    with st.sidebar:
        st.markdown("""
        <div class='custom-card'>
            <h3>🔍 Filters</h3>
        </div>
        """, unsafe_allow_html=True)
        
        # Use session state to persist filter values
        if 'sector_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.sector_filter = ""
        
        # Sector filter with on_change to trigger rerun
        sector_filter = st.text_input(
            "Sector", 
            value=st.session_state.sector_filter, 
            key="sector_filter_input",
            on_change=lambda: None  # This helps trigger updates
        )
        current_filters['sector_filter'] = sector_filter
        
        if 'plot_size_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.plot_size_filter = ""
        plot_size_filter = st.text_input(
            "Plot Size", 
            value=st.session_state.plot_size_filter, 
            key="plot_size_filter_input"
        )
        current_filters['plot_size_filter'] = plot_size_filter
        
        if 'street_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.street_filter = ""
        street_filter = st.text_input(
            "Street No", 
            value=st.session_state.street_filter, 
            key="street_filter_input"
        )
        current_filters['street_filter'] = street_filter
        
        if 'plot_no_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.plot_no_filter = ""
        plot_no_filter = st.text_input(
            "Plot No", 
            value=st.session_state.plot_no_filter, 
            key="plot_no_filter_input"
        )
        current_filters['plot_no_filter'] = plot_no_filter
        
        if 'contact_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.contact_filter = ""
        contact_filter = st.text_input(
            "Contact Number", 
            value=st.session_state.contact_filter, 
            key="contact_filter_input"
        )
        current_filters['contact_filter'] = contact_filter
        
        # Property Type Filter
        if "Property Type" in df.columns:
            prop_types = ["All"] + sorted(df["Property Type"].astype(str).unique().tolist())
            if 'selected_prop_type' not in st.session_state or st.session_state.filters_reset:
                st.session_state.selected_prop_type = "All"
            selected_prop_type = st.selectbox(
                "Property Type",
                prop_types,
                index=prop_types.index(st.session_state.selected_prop_type) if st.session_state.selected_prop_type in prop_types else 0,
                key="prop_type_select"
            )
            current_filters['selected_prop_type'] = selected_prop_type
        
        # Price Range Filter
        st.subheader("💰 Price Range")
        
        # Parse prices for filtering
        df_price = df.copy()
        df_price["ParsedPrice"] = df_price["Demand"].apply(parse_price)
        df_price_with_valid = df_price[df_price["ParsedPrice"].notnull()]
        
        if not df_price_with_valid.empty:
            min_price = int(df_price_with_valid["ParsedPrice"].min())
            max_price = int(df_price_with_valid["ParsedPrice"].max())
            
            if 'price_from' not in st.session_state or st.session_state.filters_reset:
                st.session_state.price_from = min_price
            if 'price_to' not in st.session_state or st.session_state.filters_reset:
                st.session_state.price_to = max_price
            
            price_from = st.number_input(
                "From (Lacs)", 
                min_value=min_price, 
                max_value=max_price, 
                value=st.session_state.price_from,
                key="price_from_input"
            )
            price_to = st.number_input(
                "To (Lacs)", 
                min_value=min_price, 
                max_value=max_price, 
                value=st.session_state.price_to,
                key="price_to_input"
            )
            
            current_filters['price_from'] = price_from
            current_filters['price_to'] = price_to
            
            # Display price range info
            st.caption(f"Range: {min_price} - {max_price} Lacs")
        else:
            st.info("No price data available")
            current_filters['price_from'] = 0
            current_filters['price_to'] = 1000
        
        # Features Filter
        st.subheader("🏗️ Features")
        all_features = get_all_unique_features(df)
        
        if 'selected_features' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_features = []
        
        selected_features = st.multiselect(
            "Select Features",
            options=all_features,
            default=st.session_state.selected_features,
            key="features_multiselect"
        )
        current_filters['selected_features'] = selected_features
        
        # Date Filter
        st.subheader("📅 Date Added")
        date_options = ["All", "Today", "Last 7 Days", "Last 30 Days"]
        if 'date_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.date_filter = "All"
        
        date_filter = st.selectbox(
            "Show listings from",
            date_options,
            index=date_options.index(st.session_state.date_filter),
            key="date_filter_select"
        )
        current_filters['date_filter'] = date_filter
        
        # Dealer Filter - Dynamic based on current filters
        st.subheader("👨‍💼 Dealer Filter")
        dealer_names, contact_to_name = get_dynamic_dealer_names(df, current_filters)
        
        if 'selected_dealer' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_dealer = "All Dealers"
        
        dealer_options = ["All Dealers"] + sorted(dealer_names)
        selected_dealer = st.selectbox(
            "Filter by Dealer",
            dealer_options,
            index=dealer_options.index(st.session_state.selected_dealer) if st.session_state.selected_dealer in dealer_options else 0,
            key="dealer_select"
        )
        current_filters['selected_dealer'] = selected_dealer
        
        # Filter actions
        col1, col2 = st.columns(2)
        with col1:
            apply_filters = st.button("🚀 Apply Filters", use_container_width=True)
        with col2:
            reset_filters = st.button("🔄 Reset", use_container_width=True)
        
        if reset_filters:
            st.session_state.filters_reset = True
            st.session_state.sector_filter = ""
            st.session_state.plot_size_filter = ""
            st.session_state.street_filter = ""
            st.session_state.plot_no_filter = ""
            st.session_state.contact_filter = ""
            st.session_state.selected_prop_type = "All"
            st.session_state.selected_features = []
            st.session_state.date_filter = "All"
            st.session_state.selected_dealer = "All Dealers"
            if not df_price_with_valid.empty:
                st.session_state.price_from = min_price
                st.session_state.price_to = max_price
            st.rerun()
        
        if apply_filters:
            # Update session state with current filter values
            for key, value in current_filters.items():
                st.session_state[key] = value
            st.session_state.filters_reset = False
            st.rerun()
    
    # Apply filters to data
    filtered_df = df.copy()
    
    # Sector filter
    if st.session_state.get('sector_filter'):
        filtered_df = filtered_df[filtered_df["Sector"].apply(
            lambda x: sector_matches(st.session_state.sector_filter, str(x))
        )]
    
    # Plot Size filter
    if st.session_state.get('plot_size_filter'):
        filtered_df = filtered_df[filtered_df["Plot Size"].str.contains(
            st.session_state.plot_size_filter, case=False, na=False
        )]
    
    # Street No filter
    if st.session_state.get('street_filter'):
        street_pattern = re.compile(re.escape(st.session_state.street_filter), re.IGNORECASE)
        filtered_df = filtered_df[filtered_df["Street No"].apply(
            lambda x: bool(street_pattern.search(str(x)))
        )]
    
    # Plot No filter
    if st.session_state.get('plot_no_filter'):
        plot_pattern = re.compile(re.escape(st.session_state.plot_no_filter), re.IGNORECASE)
        filtered_df = filtered_df[filtered_df["Plot No"].apply(
            lambda x: bool(plot_pattern.search(str(x)))
        )]
    
    # Contact filter
    if st.session_state.get('contact_filter'):
        cnum = clean_number(st.session_state.contact_filter)
        filtered_df = filtered_df[filtered_df["Extracted Contact"].astype(str).apply(
            lambda x: any(cnum == clean_number(p) for p in x.split(","))
        )]
    
    # Property Type filter
    if (st.session_state.get('selected_prop_type') and 
        st.session_state.selected_prop_type != "All" and 
        "Property Type" in filtered_df.columns):
        filtered_df = filtered_df[filtered_df["Property Type"].astype(str).str.strip() == st.session_state.selected_prop_type]
    
    # Price filter
    filtered_df["ParsedPrice"] = filtered_df["Demand"].apply(parse_price)
    if "ParsedPrice" in filtered_df.columns:
        filtered_df_with_price = filtered_df[filtered_df["ParsedPrice"].notnull()]
        if not filtered_df_with_price.empty:
            filtered_df = filtered_df_with_price[
                (filtered_df_with_price["ParsedPrice"] >= st.session_state.get('price_from', 0)) & 
                (filtered_df_with_price["ParsedPrice"] <= st.session_state.get('price_to', 1000))
            ]
    
    # Features filter
    if st.session_state.get('selected_features'):
        filtered_df = filtered_df[filtered_df["Features"].apply(
            lambda x: fuzzy_feature_match(x, st.session_state.selected_features)
        )]
    
    # Date filter
    filtered_df = filter_by_date(filtered_df, st.session_state.get('date_filter', 'All'))
    
    # Dealer filter
    if (st.session_state.get('selected_dealer') and 
        st.session_state.selected_dealer != "All Dealers"):
        dealer_contacts = contact_to_name.get(st.session_state.selected_dealer, [])
        if dealer_contacts:
            filtered_df = filtered_df[filtered_df["Extracted Contact"].apply(
                lambda x: any(contact in clean_number(str(x)) for contact in dealer_contacts)
            )]
    
    # Ensure data is grouped by Extracted Name after filtering
    filtered_df = group_by_extracted_name(filtered_df)
    
    # Main content area with tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🏠 Available Listings", 
        "🔄 Duplicates", 
        "🆕 New Today", 
        "📈 New This Week",
        "✅ Sold Listings", 
        "⏸️ On Hold", 
        "📞 Contacts"
    ])
    
    with tab1:
        st.subheader(f"📊 Available Listings ({len(filtered_df)} found)")
        
        if not filtered_df.empty:
            # Add SheetRowNum for deletion functionality
            filtered_df_with_rows = filtered_df.copy()
            filtered_df_with_rows["SheetRowNum"] = [i + 2 for i in range(len(filtered_df_with_rows))]
            
            display_table_with_actions(filtered_df_with_rows, "Available Listings", height=400)
        else:
            st.info("No listings found with current filters")
    
    with tab2:
        st.subheader("🔄 Duplicate Listings")
        
        if not filtered_df.empty and st.session_state.get('selected_dealer') != "All Dealers":
            dealer_contacts = contact_to_name.get(st.session_state.selected_dealer, [])
            if dealer_contacts:
                styled_duplicates, duplicates_df = create_dealer_specific_duplicates_view(filtered_df, dealer_contacts)
                
                if not duplicates_df.empty:
                    st.info(f"Found {len(duplicates_df)} potential duplicate listings")
                    
                    # Group duplicates by Extracted Name
                    duplicates_df = group_by_extracted_name(duplicates_df)
                    
                    if styled_duplicates is not None:
                        # Apply grouping to styled dataframe
                        try:
                            st.dataframe(styled_duplicates, use_container_width=True, height=400)
                        except Exception as e:
                            st.warning("Could not display styled duplicates, showing plain view")
                            safe_display_dataframe(duplicates_df, height=400)
                    else:
                        safe_display_dataframe(duplicates_df, height=400)
                else:
                    st.success("✅ No duplicates found for selected dealer")
            else:
                st.warning("Please select a specific dealer to view duplicates")
        else:
            st.info("Select a specific dealer from filters to view their duplicate listings")
    
    with tab3:
        st.subheader("🆕 Unique Listings Added Today")
        today_unique = get_todays_unique_listings(df)
        
        if not today_unique.empty:
            # Group by Extracted Name
            today_unique = group_by_extracted_name(today_unique)
            st.info(f"Found {len(today_unique)} new unique listings today")
            safe_display_dataframe(today_unique, height=400)
        else:
            st.info("No new unique listings today")
    
    with tab4:
        st.subheader("📈 Unique Listings Added This Week")
        week_unique = get_this_weeks_unique_listings(df)
        
        if not week_unique.empty:
            # Group by Extracted Name
            week_unique = group_by_extracted_name(week_unique)
            st.info(f"Found {len(week_unique)} new unique listings this week")
            safe_display_dataframe(week_unique, height=400)
        else:
            st.info("No new unique listings this week")
    
    with tab5:
        st.subheader("✅ Sold Listings")
        
        if not sold_df.empty:
            # Group by Extracted Name
            sold_df_grouped = group_by_extracted_name(sold_df)
            st.info(f"Total sold listings: {len(sold_df)}")
            safe_display_dataframe(sold_df_grouped, height=400)
        else:
            st.info("No sold listings yet")
    
    with tab6:
        st.subheader("⏸️ Listings On Hold")
        
        if not hold_df.empty:
            # Group by Extracted Name
            hold_df_grouped = group_by_extracted_name(hold_df)
            st.info(f"Total listings on hold: {len(hold_df)}")
            
            # Add SheetRowNum for actions
            hold_df_with_rows = hold_df_grouped.copy()
            hold_df_with_rows["SheetRowNum"] = [i + 2 for i in range(len(hold_df_with_rows))]
            
            display_table_with_actions(hold_df_with_rows, "Hold Listings", height=400, show_hold_button=False)
        else:
            st.info("No listings on hold")
    
    with tab7:
        st.subheader("📞 Contacts Management")
        
        if not contacts_df.empty:
            st.info(f"Total contacts: {len(contacts_df)}")
            display_table_with_actions(contacts_df, "Contacts", height=400, show_hold_button=False)
        else:
            st.info("No contacts available")
    
    # Edit form (if in edit mode)
    if st.session_state.get('edit_mode') and st.session_state.get('editing_row'):
        show_edit_form(st.session_state.editing_row, st.session_state.editing_table)

def show_edit_form(row_data, table_name):
    """Show edit form for the selected row"""
    st.sidebar.markdown("---")
    st.sidebar.subheader("✏️ Edit Listing")
    
    with st.sidebar.form("edit_form"):
        st.write(f"Editing record from {table_name}")
        
        # Create editable fields for main columns
        edited_data = {}
        for col in ["Sector", "Plot No", "Street No", "Plot Size", "Demand", "Property Type", "Features"]:
            if col in row_data:
                current_val = row_data[col] if pd.notna(row_data[col]) else ""
                edited_data[col] = st.text_input(col, value=str(current_val))
        
        # Special handling for contacts and names if available
        if "Extracted Contact" in row_data:
            current_contact = row_data["Extracted Contact"] if pd.notna(row_data["Extracted Contact"]) else ""
            edited_data["Extracted Contact"] = st.text_input("Contact", value=str(current_contact))
        
        if "Extracted Name" in row_data:
            current_name = row_data["Extracted Name"] if pd.notna(row_data["Extracted Name"]) else ""
            edited_data["Extracted Name"] = st.text_input("Name", value=str(current_name))
        
        col1, col2 = st.columns(2)
        with col1:
            save_btn = st.form_submit_button("💾 Save Changes", use_container_width=True)
        with col2:
            cancel_btn = st.form_submit_button("❌ Cancel", use_container_width=True)
        
        if save_btn:
            # Here you would implement the actual update logic
            st.success("Changes saved successfully!")
            st.session_state.edit_mode = False
            st.session_state.editing_row = None
            st.session_state.editing_table = None
            st.rerun()
        
        if cancel_btn:
            st.session_state.edit_mode = False
            st.session_state.editing_row = None
            st.session_state.editing_table = None
            st.rerun()

# Run the app
if __name__ == "__main__":
    show_plots_manager()