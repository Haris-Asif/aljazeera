import streamlit as st
import pandas as pd
import re
from utils import (load_plot_data, load_contacts, delete_rows_from_sheet, 
                  generate_whatsapp_messages, build_name_map, sector_matches,
                  extract_numbers, clean_number, format_phone_link, 
                  get_all_unique_features, filter_by_date, create_duplicates_view,
                  parse_price, update_plot_data, load_sold_data, save_sold_data,
                  generate_sold_id)
from utils import fuzzy_feature_match
from datetime import datetime

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
    if 'mark_sold_mode' not in st.session_state:
        st.session_state.mark_sold_mode = False
    if 'mark_sold_rows' not in st.session_state:
        st.session_state.mark_sold_rows = None
    
    # Initialize session state for filters
    if 'filters_reset' not in st.session_state:
        st.session_state.filters_reset = False
    
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
        sector_filter = st.text_input("Sector", value=st.session_state.sector_filter, key="sector_filter_input")
        
        if 'plot_size_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.plot_size_filter = ""
        plot_size_filter = st.text_input("Plot Size", value=st.session_state.plot_size_filter, key="plot_size_filter_input")
        
        if 'street_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.street_filter = ""
        street_filter = st.text_input("Street No", value=st.session_state.street_filter, key="street_filter_input")
        
        if 'plot_no_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.plot_no_filter = ""
        plot_no_filter = st.text_input("Plot No", value=st.session_state.plot_no_filter, key="plot_no_filter_input")
        
        if 'contact_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.contact_filter = ""
        contact_filter = st.text_input("Phone Number", value=st.session_state.contact_filter, key="contact_filter_input")
        
        if 'price_from' not in st.session_state or st.session_state.filters_reset:
            st.session_state.price_from = 0.0
        price_from = st.number_input("Price From (in Lacs)", min_value=0.0, value=st.session_state.price_from, step=1.0, key="price_from_input")
        
        if 'price_to' not in st.session_state or st.session_state.filters_reset:
            st.session_state.price_to = 1000.0
        price_to = st.number_input("Price To (in Lacs)", min_value=0.0, value=st.session_state.price_to, step=1.0, key="price_to_input")
        
        all_features = get_all_unique_features(df)
        
        if 'selected_features' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_features = []
        selected_features = st.multiselect("Select Feature(s)", options=all_features, default=st.session_state.selected_features, key="features_input")
        
        if 'date_filter' not in st.session_state or st.session_state.filters_reset:
            st.session_state.date_filter = "All"
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"], 
                                 index=["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"].index(st.session_state.date_filter), 
                                 key="date_filter_input")

        # Property Type filter
        prop_type_options = ["All"]
        if "Property Type" in df.columns:
            prop_type_options += sorted([str(v).strip() for v in df["Property Type"].dropna().astype(str).unique()])
        
        if 'selected_prop_type' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_prop_type = "All"
        selected_prop_type = st.selectbox("Property Type", prop_type_options, 
                                        index=prop_type_options.index(st.session_state.selected_prop_type), 
                                        key="prop_type_input")

        dealer_names, contact_to_name = build_name_map(df)
        
        if 'selected_dealer' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_dealer = ""
        selected_dealer = st.selectbox("Dealer Name (by contact)", [""] + dealer_names, 
                                     index=([""] + dealer_names).index(st.session_state.selected_dealer) if st.session_state.selected_dealer in [""] + dealer_names else 0, 
                                     key="dealer_input")

        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique()) if not contacts_df.empty else [""]
        
        # Pre-select contact if coming from Contacts tab
        if st.session_state.get("selected_contact"):
            st.session_state.selected_saved = st.session_state.selected_contact
            st.session_state.selected_contact = None
        
        if 'selected_saved' not in st.session_state or st.session_state.filters_reset:
            st.session_state.selected_saved = ""
        selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names, 
                                    index=contact_names.index(st.session_state.selected_saved) if st.session_state.selected_saved in contact_names else 0, 
                                    key="saved_contact_input")
        
        # Reset Filters Button - FIXED: Actually reset all filters
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
            st.rerun()
        else:
            st.session_state.filters_reset = False
    
    # Update session state with current filter values
    st.session_state.sector_filter = sector_filter
    st.session_state.plot_size_filter = plot_size_filter
    st.session_state.street_filter = street_filter
    st.session_state.plot_no_filter = plot_no_filter
    st.session_state.contact_filter = contact_filter
    st.session_state.price_from = price_from
    st.session_state.price_to = price_to
    st.session_state.selected_features = selected_features
    st.session_state.date_filter = date_filter
    st.session_state.selected_prop_type = selected_prop_type
    st.session_state.selected_dealer = selected_dealer
    st.session_state.selected_saved = selected_saved

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
        display_df = df_filtered.copy().reset_index(drop=True)
        display_df.insert(0, "Select", False)
        
        # Ensure all data types are consistent for display
        for col in display_df.columns:
            if display_df[col].dtype == "object":
                display_df[col] = display_df[col].astype(str)
        
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
        if select_all:
            st.session_state.selected_rows = list(range(len(display_df)))
        else:
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
            
            # Handle Mark as Sold action
            if mark_sold_btn:
                st.session_state.mark_sold_mode = True
                st.session_state.mark_sold_rows = [display_df.iloc[idx].to_dict() for idx in st.session_state.selected_rows]
                st.rerun()
            
            # FIXED: SIMPLE DELETE BUTTON - DIRECT ACTION
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
        
        # Mark as Sold Form
        if st.session_state.get('mark_sold_mode') and st.session_state.mark_sold_rows:
            show_mark_sold_form(st.session_state.mark_sold_rows)
            
    else:
        st.info("No listings match your filters")
    
    # NEW: Incomplete Listings Section
    st.markdown("---")
    st.subheader("❌ Incomplete Listings")
    
    if not df.empty:
        # Identify incomplete listings (missing required fields for WhatsApp)
        incomplete_listings = []
        for _, row in df.iterrows():
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
        
        if not incomplete_df.empty:
            st.info(f"Found {len(incomplete_df)} listings with missing information")
            
            # Display incomplete listings with checkboxes
            incomplete_display_df = incomplete_df.copy().reset_index(drop=True)
            incomplete_display_df.insert(0, "Select", False)
            
            # Action buttons for incomplete listings
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                incomplete_select_all = st.checkbox("Select All Incomplete", key="select_all_incomplete")
            with col2:
                incomplete_edit_btn = st.button("✏️ Edit Selected", use_container_width=True, key="edit_incomplete_btn")
            with col3:
                incomplete_delete_btn = st.button("🗑️ Delete Selected", type="primary", use_container_width=True, key="delete_incomplete_btn")
            
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
                use_container_width=True,
                disabled=incomplete_display_df.columns.difference(["Select"]).tolist(),
                key="incomplete_data_editor"
            )
            
            # Get selected incomplete rows
            incomplete_selected_indices = incomplete_edited_df[incomplete_edited_df["Select"]].index.tolist()
            
            if incomplete_select_all:
                incomplete_selected_indices = list(range(len(incomplete_display_df)))
            
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
            st.info("🎉 All listings have complete information!")
    else:
        st.info("No listings available to check for completeness")
    
    # NEW: Duplicate Listings Section with Checkboxes
    st.markdown("---")
    st.subheader("👥 Duplicate Listings")
    
    if not df_filtered.empty:
        styled_duplicates_df, duplicates_df = create_duplicates_view(df_filtered)
        
        if duplicates_df.empty:
            st.info("No duplicate listings found")
        else:
            st.info("Showing duplicate listings with matching Sector, Plot No, Street No and Plot Size")
            
            # Display duplicates with checkboxes
            duplicates_display_df = duplicates_df.copy().reset_index(drop=True)
            duplicates_display_df.insert(0, "Select", False)
            
            # Action buttons for duplicates
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                duplicates_select_all = st.checkbox("Select All Duplicates", key="select_all_duplicates")
            with col2:
                duplicates_edit_btn = st.button("✏️ Edit Selected", use_container_width=True, key="edit_duplicates_btn")
            with col3:
                duplicates_delete_btn = st.button("🗑️ Delete Selected", type="primary", use_container_width=True, key="delete_duplicates_btn")
            
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
                use_container_width=True,
                disabled=duplicates_display_df.columns.difference(["Select"]).tolist(),
                key="duplicates_data_editor"
            )
            
            # Get selected duplicate rows
            duplicates_selected_indices = duplicates_edited_df[duplicates_edited_df["Select"]].index.tolist()
            
            if duplicates_select_all:
                duplicates_selected_indices = list(range(len(duplicates_display_df)))
            
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

    # NEW: Sold Listings Section
    st.markdown("---")
    st.subheader("✅ Sold Listings")
    
    if not sold_df.empty:
        st.info(f"Showing {len(sold_df)} sold listings")
        
        # Display sold listings
        sold_display_df = sold_df.copy().reset_index(drop=True)
        sold_display_df.insert(0, "Select", False)
        
        # Action buttons for sold listings
        col1, col2 = st.columns([2, 1])
        with col1:
            sold_select_all = st.checkbox("Select All Sold", key="select_all_sold")
        with col2:
            sold_delete_btn = st.button("🗑️ Delete Selected", type="primary", use_container_width=True, key="delete_sold_btn")
        
        # Configure columns for sold data editor
        sold_column_config = {
            "Select": st.column_config.CheckboxColumn(required=True),
            "SheetRowNum": st.column_config.NumberColumn(disabled=True)
        }
        
        # Display sold listings with checkboxes
        sold_edited_df = st.data_editor(
            sold_display_df,
            column_config=sold_column_config,
            hide_index=True,
            use_container_width=True,
            disabled=sold_display_df.columns.difference(["Select"]).tolist(),
            key="sold_data_editor"
        )
        
        # Get selected sold rows
        sold_selected_indices = sold_edited_df[sold_edited_df["Select"]].index.tolist()
        
        if sold_select_all:
            sold_selected_indices = list(range(len(sold_display_df)))
        
        # Handle sold listing actions
        if sold_selected_indices:
            st.success(f"**{len(sold_selected_indices)} sold listing(s) selected**")
            
            if sold_delete_btn:
                selected_sold_rows = [sold_display_df.iloc[idx] for idx in sold_selected_indices]
                sold_row_nums = [int(row["SheetRowNum"]) for row in selected_sold_rows]
                
                st.warning(f"🗑️ Deleting {len(sold_row_nums)} selected sold listing(s)...")
                
                # Create updated sold dataframe without selected rows
                updated_sold_df = sold_df[~sold_df["SheetRowNum"].isin(sold_row_nums)]
                
                if save_sold_data(updated_sold_df):
                    st.success(f"✅ Successfully deleted {len(sold_row_nums)} sold listing(s)!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("❌ Failed to delete sold listings. Please try again.")
    else:
        st.info("No sold listings found")

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

def show_mark_sold_form(rows_data):
    """Show form to mark listings as sold"""
    st.markdown("---")
    st.subheader("✅ Mark as Sold")
    
    st.info(f"Marking {len(rows_data)} listing(s) as sold")
    
    with st.form("mark_sold_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            buyer_name = st.text_input("Buyer Name*", placeholder="Enter buyer's full name")
            buyer_contact = st.text_input("Buyer Contact", placeholder="Phone number")
            sale_date = st.date_input("Sale Date", value=datetime.now().date())
            agent = st.text_input("Agent", value="Current User", placeholder="Agent name")
        
        with col2:
            sale_price = st.number_input("Sale Price (₹)", min_value=0, value=0, step=1000)
            commission = st.number_input("Commission (₹)", min_value=0, value=0, step=1000)
            notes = st.text_area("Notes", placeholder="Any additional notes about the sale")
        
        submitted = st.form_submit_button("✅ Confirm Sale")
        cancel = st.form_submit_button("❌ Cancel")
        
        if submitted:
            if not buyer_name:
                st.error("❌ Buyer Name is required!")
            else:
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
                        "Buyer Name": buyer_name,
                        "Buyer Contact": buyer_contact,
                        "Sale Date": sale_date.strftime("%Y-%m-%d"),
                        "Sale Price": sale_price,
                        "Commission": commission,
                        "Agent": agent,
                        "Notes": notes,
                        "Original Row Num": row_data.get("SheetRowNum", "")
                    }
                    
                    sold_df = pd.concat([sold_df, pd.DataFrame([new_sold_record])], ignore_index=True)
                
                # Save sold data
                if save_sold_data(sold_df):
                    # Delete from plots sheet
                    row_nums = [row["SheetRowNum"] for row in rows_data]
                    if delete_rows_from_sheet(row_nums):
                        st.success(f"✅ Successfully marked {len(rows_data)} listing(s) as sold!")
                        st.session_state.mark_sold_mode = False
                        st.session_state.mark_sold_rows = None
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("❌ Failed to remove listings from plots sheet.")
                else:
                    st.error("❌ Failed to save sold data. Please try again.")
        
        if cancel:
            st.session_state.mark_sold_mode = False
            st.session_state.mark_sold_rows = None
            st.rerun()
