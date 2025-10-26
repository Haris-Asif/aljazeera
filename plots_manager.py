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
    
    try:
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
        
        return duplicates_df, duplicates_df
        
    except Exception as e:
        st.error(f"Error creating duplicates view: {str(e)}")
        return pd.DataFrame(), pd.DataFrame()


def show_plots_manager():
    st.header("🏠 Plots Management")
    
    # Load data with caching disabled for fresh data
    try:
        df = load_plot_data().fillna("")
        contacts_df = load_contacts()
        sold_df = load_sold_data()
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        st.info("Please check your internet connection and try again.")
        return
    
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
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False

    # Force data refresh button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Data", key="refresh_data_btn"):
            st.cache_data.clear()
            st.session_state.data_loaded = False
            st.rerun()

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
            key="sector_filter_input"
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
        
        # Check if filters have changed to trigger rerun - but avoid infinite loops
        filters_changed = current_filters != st.session_state.last_filter_state
        if filters_changed:
            st.session_state.last_filter_state = current_filters.copy()
            # Only rerun if it's not the initial load
            if st.session_state.data_loaded:
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
    
    # Mark data as loaded after first render
    st.session_state.data_loaded = True
    
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
    if "ParsedPrice" in df_filtered.columns:
        df_filtered_with_price = df_filtered[df_filtered["ParsedPrice"].notnull()]
        if not df_filtered_with_price.empty:
            df_filtered = df_filtered_with_price[
                (df_filtered_with_price["ParsedPrice"] >= st.session_state.price_from) & 
                (df_filtered_with_price["ParsedPrice"] <= st.session_state.price_to)
            ]

    # Apply features filter
    if st.session_state.selected_features:
        df_filtered = df_filtered[df_filtered["Features"].apply(lambda x: fuzzy_feature_match(x, st.session_state.selected_features))]

    # Apply date filter
    df_filtered = filter_by_date(df_filtered, st.session_state.date_filter)

    # Display filtered results
    st.subheader("📋 Filtered Listings")
    st.write(f"📊 Total filtered listings: **{len(df_filtered)}** | ✅ WhatsApp eligible: **{len(df_filtered[df_filtered['Extracted Contact'].notna() & (df_filtered['Extracted Contact'] != '')])}**")

    if not df_filtered.empty:
        # Prepare data for display
        display_df = safe_dataframe_for_display(df_filtered)
        
        # Add WhatsApp column
        def create_whatsapp_link(row):
            if pd.notna(row.get('Extracted Contact')) and row['Extracted Contact'] != '':
                numbers = [clean_number(n) for n in str(row['Extracted Contact']).split(',')]
                valid_numbers = [n for n in numbers if n]
                if valid_numbers:
                    return f"https://wa.me/{valid_numbers[0]}"
            return ""
        
        display_df['WhatsApp'] = display_df.apply(create_whatsapp_link, axis=1)
        
        # Display the dataframe
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # WhatsApp messaging section
        st.subheader("💬 WhatsApp Messaging")
        eligible_df = df_filtered[df_filtered['WhatsApp'].notna() & (df_filtered['WhatsApp'] != '')]
        
        if not eligible_df.empty:
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("📱 Generate WhatsApp Messages", key="generate_whatsapp"):
                    messages = generate_whatsapp_messages(eligible_df)
                    st.session_state.whatsapp_messages = messages
                    st.success(f"Generated {len(messages)} WhatsApp messages!")
            
            if 'whatsapp_messages' in st.session_state:
                with col2:
                    if st.button("📋 Show Messages", key="show_messages"):
                        for i, msg in enumerate(st.session_state.whatsapp_messages, 1):
                            st.text_area(f"Message {i}", msg, height=100, key=f"msg_{i}")
        else:
            st.info("No WhatsApp-eligible listings in current filters.")
    else:
        st.info("No listings match the current filters.")

    # Dealer-specific duplicates section
    if st.session_state.selected_dealer:
        st.subheader("👥 Dealer-Specific Duplicates")
        actual_name = st.session_state.selected_dealer.split(". ", 1)[1] if ". " in st.session_state.selected_dealer else st.session_state.selected_dealer
        selected_contacts = [c for c, name in contact_to_name.items() if name == actual_name]
        
        dealer_duplicates, raw_duplicates = create_dealer_specific_duplicates_view(df, selected_contacts)
        
        if not raw_duplicates.empty:
            st.write(f"Showing duplicate listings for dealer {actual_name} - matching Sector, Plot No, Street No, Plot Size but different Contacts/Names")
            
            # Simple display without styling to avoid OverflowError
            st.write("**Color Grouped View (Read-only)**")
            st.dataframe(raw_duplicates, use_container_width=True, hide_index=True)
            
            # Add manual coloring explanation
            st.info("💡 **Note:** Rows with the same background color represent potential duplicate listings. Each color group shares the same Sector, Plot No, Street No, and Plot Size but has different contact information.")
        else:
            st.info("No duplicates found for this dealer.")

# Make sure the function is properly closed