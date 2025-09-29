import streamlit as st
import pandas as pd
import tempfile
import os
from utils import load_contacts, delete_contacts_from_sheet, add_contacts_batch, parse_vcf_file, add_contact_to_sheet

def show_contacts_manager():
    st.header("👥 Contacts Management")
    
    # Load contacts data
    contacts_df = load_contacts()
    
    # Add row numbers for deletion
    if not contacts_df.empty:
        contacts_df["SheetRowNum"] = [i + 2 for i in range(len(contacts_df))]
    
    # Display metrics with safe column access
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_contacts = len(contacts_df)
        st.metric("📇 Total Contacts", total_contacts)
    
    with col2:
        # Safe column access for Email
        contacts_with_email = 0
        if not contacts_df.empty and "Email" in contacts_df.columns:
            contacts_with_email = len(contacts_df[contacts_df["Email"].notna() & (contacts_df["Email"] != "")])
        st.metric("📧 With Email", contacts_with_email)
    
    with col3:
        # Safe column access for Address
        contacts_with_address = 0
        if not contacts_df.empty and "Address" in contacts_df.columns:
            contacts_with_address = len(contacts_df[contacts_df["Address"].notna() & (contacts_df["Address"] != "")])
        st.metric("🏠 With Address", contacts_with_address)
    
    with col4:
        # Safe column access for multiple contacts
        multiple_contacts = 0
        if not contacts_df.empty:
            if "Contact2" in contacts_df.columns and "Contact3" in contacts_df.columns:
                multiple_contacts = len(contacts_df[
                    (contacts_df["Contact2"].notna() & (contacts_df["Contact2"] != "")) |
                    (contacts_df["Contact3"].notna() & (contacts_df["Contact3"] != ""))
                ])
        st.metric("📱 Multiple Numbers", multiple_contacts)
    
    # Main content in tabs
    tab1, tab2, tab3 = st.tabs(["📋 View Contacts", "➕ Add Contacts", "📤 Import Contacts"])
    
    with tab1:
        show_contacts_view(contacts_df)
    
    with tab2:
        show_add_contact_form()
    
    with tab3:
        show_import_contacts()

def show_contacts_view(contacts_df):
    """Display and manage existing contacts"""
    st.subheader("📋 All Contacts")
    
    if contacts_df.empty:
        st.info("No contacts found. Add your first contact in the 'Add Contacts' tab.")
        return
    
    # Search and filters
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        search_term = st.text_input("🔍 Search by Name or Contact", placeholder="Enter name or phone number")
    
    with col2:
        filter_by = st.selectbox("Filter by", ["All", "With Email", "With Address", "Multiple Numbers"])
    
    with col3:
        sort_by = st.selectbox("Sort by", ["Name A-Z", "Name Z-A", "Recent First", "Oldest First"])
    
    # Apply filters
    filtered_contacts = contacts_df.copy()
    
    if search_term:
        filtered_contacts = filtered_contacts[
            filtered_contacts["Name"].str.contains(search_term, case=False, na=False) |
            filtered_contacts["Contact1"].str.contains(search_term, case=False, na=False) |
            (filtered_contacts["Contact2"].str.contains(search_term, case=False, na=False) if "Contact2" in filtered_contacts.columns else False) |
            (filtered_contacts["Contact3"].str.contains(search_term, case=False, na=False) if "Contact3" in filtered_contacts.columns else False)
        ]
    
    if filter_by == "With Email":
        if "Email" in filtered_contacts.columns:
            filtered_contacts = filtered_contacts[filtered_contacts["Email"].notna() & (filtered_contacts["Email"] != "")]
    elif filter_by == "With Address":
        if "Address" in filtered_contacts.columns:
            filtered_contacts = filtered_contacts[filtered_contacts["Address"].notna() & (filtered_contacts["Address"] != "")]
    elif filter_by == "Multiple Numbers":
        if "Contact2" in filtered_contacts.columns and "Contact3" in filtered_contacts.columns:
            filtered_contacts = filtered_contacts[
                (filtered_contacts["Contact2"].notna() & (filtered_contacts["Contact2"] != "")) |
                (filtered_contacts["Contact3"].notna() & (filtered_contacts["Contact3"] != ""))
            ]
    
    # Apply sorting
    if sort_by == "Name A-Z":
        filtered_contacts = filtered_contacts.sort_values("Name", ascending=True)
    elif sort_by == "Name Z-A":
        filtered_contacts = filtered_contacts.sort_values("Name", ascending=False)
    elif sort_by == "Recent First":
        if "Timestamp" in filtered_contacts.columns:
            filtered_contacts = filtered_contacts.sort_values("Timestamp", ascending=False)
    elif sort_by == "Oldest First":
        if "Timestamp" in filtered_contacts.columns:
            filtered_contacts = filtered_contacts.sort_values("Timestamp", ascending=True)
    
    # Display contacts count
    st.info(f"**Showing {len(filtered_contacts)} of {len(contacts_df)} contacts**")
    
    if filtered_contacts.empty:
        st.info("No contacts found matching your criteria.")
        return
    
    # Create display dataframe with selection
    display_df = filtered_contacts.copy().reset_index(drop=True)
    display_df.insert(0, "Select", False)
    
    # Select all checkbox
    select_all = st.checkbox("Select All Contacts", key="select_all_contacts")
    if select_all:
        display_df["Select"] = True
    
    # Configure columns for data editor
    column_config = {
        "Select": st.column_config.CheckboxColumn(required=True),
        "SheetRowNum": st.column_config.NumberColumn(disabled=True)
    }
    
    # Display contacts table
    edited_df = st.data_editor(
        display_df,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        disabled=display_df.columns.difference(["Select"]).tolist(),
        key="contacts_data_editor"
    )
    
    # Get selected rows
    selected_rows = edited_df[edited_df["Select"]]
    
    if not selected_rows.empty:
        st.success(f"**{len(selected_rows)} contact(s) selected**")
        
        # Action buttons
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🗑️ Delete Selected", use_container_width=True, type="primary"):
                delete_selected_contacts(selected_rows)
        
        with col2:
            if st.button("📞 Use in Plots", use_container_width=True):
                use_in_plots(selected_rows)

def delete_selected_contacts(selected_rows):
    """Delete selected contacts from sheet"""
    row_nums = selected_rows["SheetRowNum"].tolist()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    success = delete_contacts_from_sheet(row_nums)
    
    if success:
        progress_bar.progress(100)
        status_text.success(f"✅ Successfully deleted {len(selected_rows)} contact(s)!")
        st.cache_data.clear()
        st.rerun()
    else:
        status_text.error("❌ Failed to delete some contacts. Please try again.")

def use_in_plots(selected_rows):
    """Set selected contact to be used in Plots section"""
    if not selected_rows.empty:
        # Take the first selected contact
        contact_name = selected_rows.iloc[0]["Name"]
        st.session_state.selected_contact = contact_name
        st.session_state.active_tab = "Plots"
        st.success(f"✅ Contact '{contact_name}' selected for use in Plots section!")
        st.rerun()

def show_add_contact_form():
    """Form to add a new contact"""
    st.subheader("➕ Add New Contact")
    
    with st.form("add_contact_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Name*", placeholder="Full name")
            contact1 = st.text_input("Primary Contact*", placeholder="03XXXXXXXXX")
            contact2 = st.text_input("Secondary Contact", placeholder="Optional")
            email = st.text_input("Email", placeholder="email@example.com")
        
        with col2:
            contact3 = st.text_input("Tertiary Contact", placeholder="Optional")
            address = st.text_area("Address", placeholder="Full address", height=100)
            notes = st.text_area("Notes", placeholder="Any additional notes", height=80)
        
        submitted = st.form_submit_button("💾 Add Contact")
        
        if submitted:
            if not name or not contact1:
                st.error("❌ Name and Primary Contact are required fields!")
            else:
                # Create contact data
                contact_data = [
                    name, contact1, contact2 or "", contact3 or "", email or "", address or "", notes or ""
                ]
                
                # Add to Google Sheets
                if add_contact_to_sheet(contact_data):
                    st.success("✅ Contact added successfully!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("❌ Failed to add contact. Please try again.")

def show_import_contacts():
    """Import contacts from VCF file"""
    st.subheader("📤 Import Contacts from VCF")
    
    st.info("""
    **Instructions:**
    - Upload a VCF (vCard) file exported from your phone contacts
    - The system will extract names and phone numbers automatically
    - You can review before importing
    """)
    
    uploaded_file = st.file_uploader("Choose a VCF file", type=['vcf'], key="vcf_uploader")
    
    if uploaded_file is not None:
        # Parse VCF file
        contacts = parse_vcf_file(uploaded_file)
        
        if contacts:
            st.success(f"✅ Successfully parsed {len(contacts)} contacts from VCF file!")
            
            # Display preview
            st.subheader("📋 Preview (First 10 Contacts)")
            preview_df = pd.DataFrame(contacts[:10])
            st.dataframe(preview_df, use_container_width=True)
            
            if len(contacts) > 10:
                st.info(f"... and {len(contacts) - 10} more contacts")
            
            # Import options
            st.subheader("🚀 Import Options")
            
            col1, col2 = st.columns(2)
            
            with col1:
                import_all = st.button("📥 Import All Contacts", use_container_width=True)
            
            with col2:
                import_selected = st.button("📋 Import Selected", use_container_width=True, disabled=True)
                st.caption("Selective import coming soon")
            
            if import_all:
                import_contacts_to_sheet(contacts)
        
        else:
            st.error("❌ No contacts found in the VCF file or file format is not supported.")

def import_contacts_to_sheet(contacts):
    """Import parsed contacts to Google Sheets"""
    if not contacts:
        st.error("❌ No contacts to import!")
        return
    
    # Convert contacts to list of lists for batch import
    contacts_batch = []
    for contact in contacts:
        contacts_batch.append([
            contact["Name"],
            contact["Contact1"],
            contact.get("Contact2", ""),
            contact.get("Contact3", ""),
            contact.get("Email", ""),
            contact.get("Address", ""),
            ""  # Notes field
        ])
    
    # Show progress
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    status_text.info(f"🔄 Importing {len(contacts_batch)} contacts...")
    
    # Batch import
    success_count = add_contacts_batch(contacts_batch)
    
    if success_count > 0:
        progress_bar.progress(100)
        status_text.success(f"✅ Successfully imported {success_count} contacts!")
        if success_count < len(contacts_batch):
            st.warning(f"⚠️ {len(contacts_batch) - success_count} contacts failed to import (possibly due to API limits)")
        st.cache_data.clear()
        st.rerun()
    else:
        status_text.error("❌ Failed to import any contacts. Please try again.")
