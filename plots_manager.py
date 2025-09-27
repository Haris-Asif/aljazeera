import streamlit as st
import pandas as pd
from utils import (load_plot_data, load_contacts, delete_rows_from_sheet, 
                  generate_whatsapp_messages, build_name_map, sector_matches,
                  extract_numbers, clean_number, format_phone_link, 
                  get_all_unique_features, filter_by_date, create_duplicates_view,
                  parse_price)

def show_plots_manager():
    st.header("🏠 Plots Management")
    
    # Load data
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    
    # Add row numbers to contacts for deletion
    if not contacts_df.empty:
        contacts_df["SheetRowNum"] = [i + 2 for i in range(len(contacts_df))]
    
    # Sidebar Filters
    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street No")
        plot_no_filter = st.text_input("Plot No")
        contact_filter = st.text_input("Phone Number (03xxxxxxxxx)")
        price_from = st.number_input("Price From (in Lacs)", min_value=0.0, value=0.0, step=1.0)
        price_to = st.number_input("Price To (in Lacs)", min_value=0.0, value=1000.0, step=1.0)
        
        all_features = get_all_unique_features(df)
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
        if st.session_state.get("selected_contact"):
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

    # Apply filters
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

# Import required modules
import re
from utils import fuzzy_feature_match
