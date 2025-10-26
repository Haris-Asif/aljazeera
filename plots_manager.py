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
from datetime import datetime

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
        return pd.DataFrame(), pd.DataFrame()
    
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
        return pd.DataFrame(), pd.DataFrame()
    
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
        return pd.DataFrame(), pd.DataFrame()
    
    # Combine all duplicates
    duplicates_df = pd.concat(all_matching_listings, ignore_index=True)
    
    # Remove temporary normalized columns
    duplicates_df = duplicates_df.drop(
        ["Sector_Norm", "Plot_No_Norm", "Street_No_Norm", "Plot_Size_Norm"], 
        axis=1, 
        errors="ignore"
    )
    
    # Create styled version with color grouping
    styled_duplicates_df = duplicates_df.copy()
    groups = styled_duplicates_df["GroupKey"].unique()
    color_mapping = {group: f"hsl({int(i*360/len(groups))}, 70%, 80%)" for i, group in enumerate(groups)}
    
    def color_group(row):
        return [f"background-color: {color_mapping[row['GroupKey']]}"] * len(row)
    
    styled_duplicates_df = styled_duplicates_df.style.apply(color_group, axis=1)
    
    return styled_duplicates_df, duplicates_df

def show_plots_manager():
    st.header("🏠 Plots Management")
    
    # Load data
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    sold_df = load_sold_data()
    
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
            "Phone Number", 
            value=st.session_state.contact_filter, 
            key="contact_filter_input"
        )
        current_filters['contact_filter'] = contact_filter
        
        if 'price_from' not in st.session_state or st.session_state.filters_reset:
            st.session_state.price_from = 0.0
        price_from = st.number_input(
            "Price From (in Lacs)", 
            min_value=0.0, 
            value=st.session_state.price_from, 
            step=1.0, 
            key="price_from_input"
        )
        current_filters['price_from'] = price_from
        
        if 'price_to' not in st.session_state or st.session_state.filters_reset:
            st.session_state.price_to = 1000.0
        price_to = st.number_input(
            "Price To (in Lacs)", 
            min_value=0.0, 
            value=st.session_state.price_to, 
            step=1.0, 
            key="price_to_input"
        )
        current_filters['price_to'] = price_to
        
        all_features = get_all_unique_features(df)
        
        if 'selected_features' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_features = []
        selected_features = st.multiselect(
            "Select Feature(s)", 
            options=all_features, 
            default=st.session_state.selected_features, 
            key="features_input"
        )
        current_filters['selected_features'] = selected_features
        
        if 'date_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.date_filter = "All"
        date_filter = st.selectbox(
            "Date Range", 
            ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"], 
            index=["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"].index(st.session_state.date_filter), 
            key="date_filter_input"
        )
        current_filters['date_filter'] = date_filter

        # Property Type filter
        prop_type_options = ["All"]
        if "Property Type" in df.columns:
            prop_type_options += sorted([str(v).strip() for v in df["Property Type"].dropna().astype(str).unique()])
        
        if 'selected_prop_type' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_prop_type = "All"
        selected_prop_type = st.selectbox(
            "Property Type", 
            prop_type_options, 
            index=prop_type_options.index(st.session_state.selected_prop_type), 
            key="prop_type_input"
        )
        current_filters['selected_prop_type'] = selected_prop_type

        # DYNAMIC DEALER FILTER - This updates immediately when other filters change
        # Get dynamic dealer names based on current filters
        dealer_names, contact_to_name = get_dynamic_dealer_names(df, current_filters)
        
        if 'selected_dealer' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_dealer = ""
        
        # Check if current selected dealer is still in the updated list
        dealer_options = [""] + dealer_names
        current_dealer = st.session_state.selected_dealer
        if current_dealer not in dealer_options:
            current_dealer = ""
            st.session_state.selected_dealer = ""
        
        # Show dynamic dealer filter with current count
        selected_dealer = st.selectbox(
            f"Dealer Name (by contact) - {len(dealer_names)} found", 
            dealer_options, 
            index=dealer_options.index(current_dealer) if current_dealer in dealer_options else 0, 
            key="dealer_input"
        )
        current_filters['selected_dealer'] = selected_dealer

        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique()) if not contacts_df.empty else [""]
        
        # Pre-select contact if coming from Contacts tab
        if st.session_state.get("selected_contact"):
            st.session_state.selected_saved = st.session_state.selected_contact
            st.session_state.selected_contact = None
        
        if 'selected_saved' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_saved = ""
        selected_saved = st.selectbox(
            "📇 Saved Contact (by number)", 
            contact_names, 
            index=contact_names.index(st.session_state.selected_saved) if st.session_state.selected_saved in contact_names else 0, 
            key="saved_contact_input"
        )
        current_filters['selected_saved'] = selected_saved
        
        # Check if filters have changed to trigger rerun
        filters_changed = current_filters != st.session_state.last_filter_state
        if filters_changed:
            st.session_state.last_filter_state = current_filters.copy()
            # Use experimental_rerun to refresh the page with new dealer list
            st.rerun()
        
        # Reset Filters Button
        if st.button("🔄 Reset All Filters", use_container_width=True, key="reset_filters_btn"):
            # Reset all filter session states
            st.session_state.sector_filter = ""
            st.session_state.plot_size_filter = ""
            st.session_state.street_filter = ""
            st.session_state.plot_no_filter = ""
            st.session_state.contact_filter = ""
            st.session_state.price_from = 0.0
            st.session_state.price_to = 1000.0
            st.session_state.selected_features = []
            st.session_state.date_filter = "All"
            st.session_state.selected_prop_type = "All"
            st.session_state.selected_dealer = ""
            st.session_state.selected_saved = ""
            st.session_state.filters_reset = True
            st.session_state.last_filter_state = {}
            st.rerun()
        else:
            st.session_state.filters_reset = False
    
    # Update session state with current filter values
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
    st.session_state.selected_dealer = current_filters['selected_dealer']
    st.session_state.selected_saved = current_filters['selected_saved']

    # Display dealer contact info if selected
    if st.session_state.selected_dealer:
        actual_name = st.session_state.selected_dealer.split(". ", 1)[1] if ". " in st.session_state.selected_dealer else st.session_state.selected_dealer
        
        # Find all numbers for this dealer
        dealer_numbers = []
        for contact, name in contact_to_name.items():
            if name == actual_name:
                dealer_numbers.append(contact)
        
        if dealer_numbers:
            st.info(f"**📞 Contact: {actual_name}**")
            cols = st.columns(len(dealer_numbers))
            for i, num in enumerate(dealer_numbers):
                formatted_num = format_phone_link(num)
                cols[i].markdown(f'<a href="tel:{formatted_num}" style="display: inline-block; padding: 0.5rem 1rem; background-color: #25D366; color: white; text-decoration: none; border-radius: 0.5rem; font-weight: 600;">Call {num}</a>', 
                                unsafe_allow_html=True)

    # Apply filters - SHOW ALL LISTINGS regardless of missing values
    df_filtered = df.copy()

    # Apply dealer filter first
    if st.session_state.selected_dealer:
        actual_name = st.session_state.selected_dealer.split(". ", 1)[1] if ". " in st.session_state.selected_dealer else st.session_state.selected_dealer
        selected_contacts = [c for c, name in contact_to_name.items() if name == actual_name]
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(c in clean_number(str(x)) for c in selected_contacts))]

    if st.session_state.selected_saved:
        row = contacts_df[contacts_df["Name"] == st.session_state.selected_saved].iloc[0] if not contacts_df.empty and not contacts_df[contacts_df["Name"] == st.session_state.selected_saved].empty else None
        selected_contacts = []
        if row is not None:
            for col in ["Contact1", "Contact2", "Contact3"]:
                if col in row and pd.notna(row[col]):
                    selected_contacts.extend(extract_numbers(str(row[col])))
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(n in clean_number(str(x)) for n in selected_contacts))]

    if st.session_state.sector_filter:
        df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(st.session_state.sector_filter, str(x)))]
    if st.session_state.plot_size_filter:
        df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(st.session_state.plot_size_filter, case=False, na=False)]
    
    # Enhanced Street No filter - match exact or partial matches
    if st.session_state.street_filter:
        street_pattern = re.compile(re.escape(st.session_state.street_filter), re.IGNORECASE)
        df_filtered = df_filtered[df_filtered["Street No"].apply(lambda x: bool(street_pattern.search(str(x))))]
    
    # Enhanced Plot No filter - match exact or partial matches
    if st.session_state.plot_no_filter:
        plot_pattern = re.compile(re.escape(st.session_state.plot_no_filter), re.IGNORECASE)
        df_filtered = df_filtered[df_filtered["Plot No"].apply(lambda x: bool(plot_pattern.search(str(x))))]
    
    if st.session_state.contact_filter:
        cnum = clean_number(st.session_state.contact_filter)
        df_filtered = df_filtered[df_filtered["Extracted Contact"].astype(str).apply(
            lambda x: any(cnum == clean_number(p) for p in x.split(",")))]

    # Apply Property Type filter if selected
    if "Property Type" in df_filtered.columns and st.session_state.selected_prop_type and st.session_state.selected_prop_type != "All":
        df_filtered = df_filtered[df_filtered["Property Type"].astype(str).str.strip() == st.session_state.selected_prop_type]

    # Price filtering (only if prices can be parsed)
    df_filtered["ParsedPrice"] = df_filtered["Demand"].apply(parse_price)
    # Only apply price filter if we have valid parsed prices
    if "ParsedPrice" in df_filtered.columns:
        df_filtered_with_price = df_filtered[df_filtered["ParsedPrice"].notnull()]
        if not df_filtered_with_price.empty:
            df_filtered = df_filtered_with_price[(df_filtered_with_price["ParsedPrice"] >= st.session_state.price_from) & (df_filtered_with_price["ParsedPrice"] <= st.session_state.price_to)]

    if st.session_state.selected_features:
        df_filtered = df_filtered[df_filtered["Features"].apply(lambda x: fuzzy_feature_match(x, st.session_state.selected_features))]

    df_filtered = filter_by_date(df_filtered, st.session_state.date_filter)

    # Sort the dataframe by Sector, Plot No, Street No, Plot Size in ascending order
    # I-15 sectors are sorted by Street No, others by Plot No
    df_filtered = sort_dataframe_with_i15_street_no(df_filtered)

    # Move Timestamp column to the end
    if "Timestamp" in df_filtered.columns:
        cols = [col for col in df_filtered.columns if col != "Timestamp"] + ["Timestamp"]
        df_filtered = df_filtered[cols]

    st.subheader("📋 Filtered Listings")
    
    # Count WhatsApp eligible listings (using the same logic as before)
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
    
    st.info(f"📊 **Total filtered listings:** {len(df_filtered)} | ✅ **WhatsApp eligible:** {whatsapp_eligible_count}")
    
    # FIXED: SIMPLIFIED DELETION PROCESS WITH DATA TYPE FIXES
    if not df_filtered.empty:
        # Create display dataframe with selection
        display_df = df_filtered.copy().reset_index(drop=True)
        display_df.insert(0, "Select", False)
        
        # Ensure all data types are consistent for display
        display_df = safe_dataframe_for_display(display_df)
        
        # Action buttons row
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            select_all = st.checkbox("Select All Rows", key="select_all_main")
        with col2:
            edit_btn = st.button("✏️ Edit Selected", use_container_width=True, key="edit_selected_btn")
        with col3:
            mark_sold_btn = st.button("✅ Mark as Sold", use_container_width=True, key="mark_sold_btn")
        with col4:
            delete_btn = st.button("🗑️ Delete Selected", type="primary", use_container_width=True, key="delete_button_main")
        
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
            key="plots_data_editor"
        )
        
        # Get selected rows from the edited dataframe
        selected_indices = edited_df[edited_df["Select"]].index.tolist()
        
        # Update session state with selected indices
        st.session_state.selected_rows = selected_indices
        
        # Display selection info
        if st.session_state.selected_rows:
            st.success(f"**{len(st.session_state.selected_rows)} row(s) selected**")
            
            # Handle Edit action
            if edit_btn:
                if len(st.session_state.selected_rows) == 1:
                    st.session_state.edit_mode = True
                    st.session_state.editing_row = display_df.iloc[st.session_state.selected_rows[0]].to_dict()
                    st.rerun()
                else:
                    st.warning("Please select only one row to edit.")
            
            # Handle Mark as Sold action - FIXED: Now properly removes from Plots and adds to Sold
            if mark_sold_btn:
                selected_display_rows = [display_df.iloc[idx] for idx in st.session_state.selected_rows]
                mark_listings_sold(selected_display_rows)
            
            # Handle Delete action
            if delete_btn:
                # Get the actual SheetRowNum values from the selected rows
                selected_display_rows = [display_df.iloc[idx] for idx in st.session_state.selected_rows]
                row_nums = [int(row["SheetRowNum"]) for row in selected_display_rows]
                
                # Show deletion confirmation
                st.warning(f"🗑️ Deleting {len(row_nums)} selected row(s)...")
                
                # Perform deletion
                success = delete_rows_from_sheet(row_nums)
                
                if success:
                    st.success(f"✅ Successfully deleted {len(row_nums)} row(s)!")
                    # Clear selection and refresh
                    st.session_state.selected_rows = []
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("❌ Failed to delete rows. Please try again.")
        
        # Edit Form
        if st.session_state.get('edit_mode') and st.session_state.editing_row:
            show_edit_form(st.session_state.editing_row)
            
    else:
        st.info("No listings match your filters")
    
    # NEW: Dealer-Specific Duplicates Section
    if st.session_state.selected_dealer:
        st.markdown("---")
        st.subheader("👥 Dealer-Specific Duplicates")
        
        # Get the selected dealer's contact(s)
        actual_name = st.session_state.selected_dealer.split(". ", 1)[1] if ". " in st.session_state.selected_dealer else st.session_state.selected_dealer
        selected_contacts = [c for c, name in contact_to_name.items() if name == actual_name]
        
        # Create dealer-specific duplicates view
        styled_dealer_duplicates, dealer_duplicates_df = create_dealer_specific_duplicates_view(df, selected_contacts)
        
        if not dealer_duplicates_df.empty:
            st.info(f"Showing duplicate listings for dealer **{actual_name}** - matching Sector, Plot No, Street No, Plot Size but different Contacts/Names")
            
            # Display the styled duplicates table with color grouping (read-only)
            st.markdown("**Color Grouped View (Read-only)**")
            st.dataframe(styled_dealer_duplicates, width='stretch', hide_index=True)
            
            st.markdown("---")
            st.markdown("**Actionable View (With Checkboxes)**")
            
            # Sort dealer duplicates
            dealer_duplicates_df = sort_dataframe_with_i15_street_no(dealer_duplicates_df)
            
            # Display dealer duplicates with checkboxes for actions
            dealer_duplicates_display_df = dealer_duplicates_df.copy().reset_index(drop=True)
            dealer_duplicates_display_df.insert(0, "Select", False)
            
            # Ensure data types are consistent
            dealer_duplicates_display_df = safe_dataframe_for_display(dealer_duplicates_display_df)
            
            # Action buttons for dealer duplicates
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                dealer_duplicates_select_all = st.checkbox("Select All Dealer Duplicates", key="select_all_dealer_duplicates")
            with col2:
                dealer_duplicates_edit_btn = st.button("✏️ Edit Selected", use_container_width=True, key="edit_dealer_duplicates_btn")
            with col3:
                dealer_duplicates_delete_btn = st.button("🗑️ Delete Selected", type="primary", use_container_width=True, key="delete_dealer_duplicates_btn")
            
            # Handle select all for dealer duplicates
            if dealer_duplicates_select_all:
                dealer_duplicates_display_df["Select"] = True
            
            # Configure columns for dealer duplicates data editor
            dealer_duplicates_column_config = {
                "Select": st.column_config.CheckboxColumn(required=True),
                "SheetRowNum": st.column_config.NumberColumn(disabled=True),
                "GroupKey": st.column_config.TextColumn(disabled=True)
            }
            
            # Display dealer duplicates with checkboxes
            dealer_duplicates_edited_df = st.data_editor(
                dealer_duplicates_display_df,
                column_config=dealer_duplicates_column_config,
                hide_index=True,
                width='stretch',
                disabled=dealer_duplicates_display_df.columns.difference(["Select"]).tolist(),
                key="dealer_duplicates_data_editor"
            )
            
            # Get selected dealer duplicate rows
            dealer_duplicates_selected_indices = dealer_duplicates_edited_df[dealer_duplicates_edited_df["Select"]].index.tolist()
            
            # Handle dealer duplicate listing actions
            if dealer_duplicates_selected_indices:
                st.success(f"**{len(dealer_duplicates_selected_indices)} dealer duplicate listing(s) selected**")
                
                if dealer_duplicates_edit_btn:
                    if len(dealer_duplicates_selected_indices) == 1:
                        st.session_state.edit_mode = True
                        st.session_state.editing_row = dealer_duplicates_display_df.iloc[dealer_duplicates_selected_indices[0]].to_dict()
                        st.rerun()
                    else:
                        st.warning("Please select only one row to edit.")
                
                if dealer_duplicates_delete_btn:
                    selected_dealer_duplicate_rows = [dealer_duplicates_display_df.iloc[idx] for idx in dealer_duplicates_selected_indices]
                    dealer_duplicate_row_nums = [int(row["SheetRowNum"]) for row in selected_dealer_duplicate_rows]
                    
                    st.warning(f"🗑️ Deleting {len(dealer_duplicate_row_nums)} selected dealer duplicate listing(s)...")
                    
                    success = delete_rows_from_sheet(dealer_duplicate_row_nums)
                    
                    if success:
                        st.success(f"✅ Successfully deleted {len(dealer_duplicate_row_nums)} dealer duplicate listing(s)!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete dealer duplicate listings. Please try again.")
        else:
            st.info(f"No dealer-specific duplicates found for **{actual_name}**")
    
    # NEW: Sold Listings Table in Plots Section
    st.markdown("---")
    st.subheader("✅ Sold Listings (Filtered)")
    
    # Apply the same filters to sold listings - FIXED: Added proper column existence checks
    sold_df_filtered = sold_df.copy()
    
    # Apply the same filters to sold data with safety checks
    if st.session_state.sector_filter and "Sector" in sold_df_filtered.columns:
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Sector"].str.contains(st.session_state.sector_filter, case=False, na=False)]
    
    if st.session_state.plot_size_filter and "Plot Size" in sold_df_filtered.columns:
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Plot Size"].str.contains(st.session_state.plot_size_filter, case=False, na=False)]
    
    if st.session_state.street_filter and "Street No" in sold_df_filtered.columns:
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Street No"].str.contains(st.session_state.street_filter, case=False, na=False)]
    
    if st.session_state.plot_no_filter and "Plot No" in sold_df_filtered.columns:
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Plot No"].str.contains(st.session_state.plot_no_filter, case=False, na=False)]
    
    # Apply Property Type filter if selected
    if "Property Type" in sold_df_filtered.columns and st.session_state.selected_prop_type and st.session_state.selected_prop_type != "All":
        sold_df_filtered = sold_df_filtered[sold_df_filtered["Property Type"].astype(str).str.strip() == st.session_state.selected_prop_type]
    
    # Sort sold listings
    sold_df_filtered = sort_dataframe_with_i15_street_no(sold_df_filtered)
    
    if not sold_df_filtered.empty:
        st.info(f"Showing {len(sold_df_filtered)} sold listings matching your filters")
        
        # Display sold listings
        display_columns = ["Sector", "Plot No", "Street No", "Plot Size", "Sale Price", "Buyer Name", "Agent", "Sale Date"]
        available_columns = [col for col in display_columns if col in sold_df_filtered.columns]
        
        st.dataframe(
            sold_df_filtered[available_columns],
            use_container_width=True,
            height=300
        )
    else:
        st.info("No sold listings match your filters")
    
    # NEW: Incomplete Listings Section
    st.markdown("---")
    st.subheader("❌ Incomplete Listings")
    
    # Apply the same filters to identify incomplete listings
    incomplete_df_filtered = df_filtered.copy()
    
    if not incomplete_df_filtered.empty:
        # Identify incomplete listings (missing required fields for WhatsApp)
        incomplete_listings = []
        for _, row in incomplete_df_filtered.iterrows():
            sector = str(row.get("Sector", "")).strip()
            plot_no = str(row.get("Plot No", "")).strip()
            size = str(row.get("Plot Size", "")).strip()
            price = str(row.get("Demand", "")).strip()
            street = str(row.get("Street No", "")).strip()
            
            # Check if listing is incomplete
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
                missing_fields.append("Valid Plot No")
            
            if missing_fields:
                row_dict = row.to_dict()
                row_dict["Missing Fields"] = ", ".join(missing_fields)
                incomplete_listings.append(row_dict)
        
        incomplete_df = pd.DataFrame(incomplete_listings)
        
        # Sort incomplete listings
        incomplete_df = sort_dataframe_with_i15_street_no(incomplete_df)
        
        if not incomplete_df.empty:
            st.info(f"Found {len(incomplete_df)} listings with missing information")
            
            # Display incomplete listings with checkboxes
            incomplete_display_df = incomplete_df.copy().reset_index(drop=True)
            incomplete_display_df.insert(0, "Select", False)
            
            # Ensure data types are consistent
            incomplete_display_df = safe_dataframe_for_display(incomplete_display_df)
            
            # Action buttons for incomplete listings
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                incomplete_select_all = st.checkbox("Select All Incomplete", key="select_all_incomplete")
            with col2:
                incomplete_edit_btn = st.button("✏️ Edit Selected", use_container_width=True, key="edit_incomplete_btn")
            with col3:
                incomplete_delete_btn = st.button("🗑️ Delete Selected", type="primary", use_container_width=True, key="delete_incomplete_btn")
            
            # Handle select all for incomplete listings
            if incomplete_select_all:
                incomplete_display_df["Select"] = True
            
            # Configure columns for incomplete data editor
            incomplete_column_config = {
                "Select": st.column_config.CheckboxColumn(required=True),
                "SheetRowNum": st.column_config.NumberColumn(disabled=True),
                "Missing Fields": st.column_config.TextColumn(disabled=True)
            }
            
            # Display incomplete listings
            incomplete_edited_df = st.data_editor(
                incomplete_display_df,
                column_config=incomplete_column_config,
                hide_index=True,
                width='stretch',
                disabled=incomplete_display_df.columns.difference(["Select"]).tolist(),
                key="incomplete_data_editor"
            )
            
            # Get selected incomplete rows
            incomplete_selected_indices = incomplete_edited_df[incomplete_edited_df["Select"]].index.tolist()
            
            # Handle incomplete listing actions
            if incomplete_selected_indices:
                st.success(f"**{len(incomplete_selected_indices)} incomplete listing(s) selected**")
                
                if incomplete_edit_btn:
                    if len(incomplete_selected_indices) == 1:
                        st.session_state.edit_mode = True
                        st.session_state.editing_row = incomplete_display_df.iloc[incomplete_selected_indices[0]].to_dict()
                        st.rerun()
                    else:
                        st.warning("Please select only one row to edit.")
                
                if incomplete_delete_btn:
                    selected_incomplete_rows = [incomplete_display_df.iloc[idx] for idx in incomplete_selected_indices]
                    incomplete_row_nums = [int(row["SheetRowNum"]) for row in selected_incomplete_rows]
                    
                    st.warning(f"🗑️ Deleting {len(incomplete_row_nums)} selected incomplete listing(s)...")
                    
                    success = delete_rows_from_sheet(incomplete_row_nums)
                    
                    if success:
                        st.success(f"✅ Successfully deleted {len(incomplete_row_nums)} incomplete listing(s)!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete incomplete listings. Please try again.")
        else:
            st.info("🎉 All filtered listings have complete information!")
    else:
        st.info("No listings available to check for completeness")
    
    # UPDATED: Duplicate Listings Section with Checkboxes AND Color Grouping
    st.markdown("---")
    st.subheader("👥 Duplicate Listings Detection")
    
    if not df_filtered.empty:
        # Use the updated duplicate detection with new criteria
        styled_duplicates_df, duplicates_df = create_duplicates_view_updated(df_filtered)
        
        if duplicates_df.empty:
            st.info("No duplicate listings found")
        else:
            st.info("Showing duplicate listings with matching Sector, Plot No, Street No, Plot Size but different Contact/Name/Demand")
            
            # FIRST: Display the styled duplicates table with color grouping (read-only)
            st.markdown("**Color Grouped View (Read-only)**")
            st.dataframe(styled_duplicates_df, width='stretch', hide_index=True)
            
            st.markdown("---")
            st.markdown("**Actionable View (With Checkboxes)**")
            
            # Sort duplicates
            duplicates_df = sort_dataframe_with_i15_street_no(duplicates_df)
            
            # SECOND: Display duplicates with checkboxes for actions
            duplicates_display_df = duplicates_df.copy().reset_index(drop=True)
            duplicates_display_df.insert(0, "Select", False)
            
            # Ensure data types are consistent
            duplicates_display_df = safe_dataframe_for_display(duplicates_display_df)
            
            # Action buttons for duplicates
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                duplicates_select_all = st.checkbox("Select All Duplicates", key="select_all_duplicates")
            with col2:
                duplicates_edit_btn = st.button("✏️ Edit Selected", use_container_width=True, key="edit_duplicates_btn")
            with col3:
                duplicates_delete_btn = st.button("🗑️ Delete Selected", type="primary", use_container_width=True, key="delete_duplicates_btn")
            
            # Handle select all for duplicates
            if duplicates_select_all:
                duplicates_display_df["Select"] = True
            
            # Configure columns for duplicates data editor
            duplicates_column_config = {
                "Select": st.column_config.CheckboxColumn(required=True),
                "SheetRowNum": st.column_config.NumberColumn(disabled=True),
                "GroupKey": st.column_config.TextColumn(disabled=True)
            }
            
            # Display duplicates with checkboxes
            duplicates_edited_df = st.data_editor(
                duplicates_display_df,
                column_config=duplicates_column_config,
                hide_index=True,
                width='stretch',
                disabled=duplicates_display_df.columns.difference(["Select"]).tolist(),
                key="duplicates_data_editor"
            )
            
            # Get selected duplicate rows
            duplicates_selected_indices = duplicates_edited_df[duplicates_edited_df["Select"]].index.tolist()
            
            # Handle duplicate listing actions
            if duplicates_selected_indices:
                st.success(f"**{len(duplicates_selected_indices)} duplicate listing(s) selected**")
                
                if duplicates_edit_btn:
                    if len(duplicates_selected_indices) == 1:
                        st.session_state.edit_mode = True
                        st.session_state.editing_row = duplicates_display_df.iloc[duplicates_selected_indices[0]].to_dict()
                        st.rerun()
                    else:
                        st.warning("Please select only one row to edit.")
                
                if duplicates_delete_btn:
                    selected_duplicate_rows = [duplicates_display_df.iloc[idx] for idx in duplicates_selected_indices]
                    duplicate_row_nums = [int(row["SheetRowNum"]) for row in selected_duplicate_rows]
                    
                    st.warning(f"🗑️ Deleting {len(duplicate_row_nums)} selected duplicate listing(s)...")
                    
                    success = delete_rows_from_sheet(duplicate_row_nums)
                    
                    if success:
                        st.success(f"✅ Successfully deleted {len(duplicate_row_nums)} duplicate listing(s)!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete duplicate listings. Please try again.")
    else:
        st.info("No listings to analyze for duplicates")

    # WhatsApp section - PRESERVE EXISTING LOGIC FOR WHATSAPP MESSAGE GENERATION
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

        # Generate WhatsApp messages using the SAME LOGIC AS BEFORE
        # This will filter out listings that don't meet WhatsApp criteria while preserving the display
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
                st.markdown(f'<a href="{link}" target="_blank" style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #25D366; color: white; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 0.5rem 0;">📩 Send Message {i+1}</a>', 
                          unsafe_allow_html=True)
                st.markdown("---")

def sort_dataframe_with_i15_street_no(df):
    """Sort dataframe with special handling for I-15 sectors - sort by Street No"""
    if df.empty:
        return df
    
    # Create a copy to avoid modifying the original
    sorted_df = df.copy()
    
    # Extract numeric values for proper sorting
    if "Plot No" in sorted_df.columns:
        sorted_df["Plot_No_Numeric"] = sorted_df["Plot No"].apply(_extract_int)
    
    if "Street No" in sorted_df.columns:
        sorted_df["Street_No_Numeric"] = sorted_df["Street No"].apply(_extract_int)
    
    if "Plot Size" in sorted_df.columns:
        sorted_df["Plot_Size_Numeric"] = sorted_df["Plot Size"].apply(_extract_int)
    
    # For I-15 sectors, sort by Street No, for others by Plot No
    def get_sort_key(row):
        sector = str(row.get("Sector", "")).strip()
        if sector.startswith("I-15"):
            # For I-15 sectors, use Street No for primary sorting
            street_no = _extract_int(row.get("Street No", ""))
            plot_no = _extract_int(row.get("Plot No", ""))
            return (sector, street_no, plot_no)
        else:
            # For other sectors, use Plot No for primary sorting
            plot_no = _extract_int(row.get("Plot No", ""))
            street_no = _extract_int(row.get("Street No", ""))
            return (sector, plot_no, street_no)
    
    # Create a temporary sort key column
    sorted_df["Sort_Key"] = sorted_df.apply(get_sort_key, axis=1)
    
    try:
        sorted_df = sorted_df.sort_values(by="Sort_Key", ascending=True)
    except Exception as e:
        st.warning(f"Could not sort dataframe: {e}")
        return df
    
    # Drop temporary columns
    sorted_df = sorted_df.drop(columns=["Plot_No_Numeric", "Street_No_Numeric", "Plot_Size_Numeric", "Sort_Key"], errors="ignore")
    
    return sorted_df

def mark_listings_sold(rows_data):
    """Mark selected listings as sold by moving them to Sold sheet and removing from Plots"""
    try:
        # Load existing sold data
        sold_df = load_sold_data()
        
        # Add each selected row to sold data
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
                "Sale Price": row_data.get("Demand", ""),  # Use Demand as Sale Price
                "Commission": "",
                "Agent": "Auto-marked",  # You can change this to current user
                "Notes": "Marked as sold from Plots section",
                "Original Row Num": row_data.get("SheetRowNum", "")
            }
            
            sold_df = pd.concat([sold_df, pd.DataFrame([new_sold_record])], ignore_index=True)
        
        # Save sold data
        if save_sold_data(sold_df):
            # Delete from plots sheet
            row_nums = [int(row_data["SheetRowNum"]) for row_data in rows_data]
            if delete_rows_from_sheet(row_nums):
                st.success(f"✅ Successfully marked {len(rows_data)} listing(s) as sold and moved to Sold sheet!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("❌ Failed to remove listings from plots sheet.")
        else:
            st.error("❌ Failed to save sold data. Please try again.")
            
    except Exception as e:
        st.error(f"❌ Error marking listings as sold: {str(e)}")

def show_edit_form(row_data):
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
            # Update the row data
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
            
            # Save to Google Sheets
            if update_plot_data(updated_row):
                st.success("✅ Listing updated successfully!")
                st.session_state.edit_mode = False
                st.session_state.editing_row = None
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("❌ Failed to update listing. Please try again.")
        
        if cancel:
            st.session_state.edit_mode = False
            st.session_state.editing_row = None
            st.rerun()
