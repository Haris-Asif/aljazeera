import streamlit as st
import pandas as pd
import re
import quopri
from utils import (
    load_contacts, 
    delete_contacts_from_sheet, 
    add_contacts_batch, 
    add_contact_to_sheet
)

def parse_vcf_content(file_content):
    """
    Robust VCF parser specifically designed for VCF 2.1 files with 
    Quoted-Printable encoding and large Base64 photo blocks.
    """
    contacts = []
    current_contact = {}
    
    # Specific flags
    in_photo = False
    
    # Decode bytes to string, handling potential errors
    if isinstance(file_content, bytes):
        try:
            content_str = file_content.decode('utf-8')
        except UnicodeDecodeError:
            content_str = file_content.decode('latin-1') # Fallback for older encodings
    else:
        content_str = file_content

    lines = content_str.splitlines()

    for line in lines:
        line = line.strip()
        
        # 1. Skip empty lines
        if not line:
            continue
            
        # 2. Handle Photo Blocks (Skip them to prevent freezing)
        if line.startswith('PHOTO'):
            in_photo = True
            continue
        if in_photo:
            # If we are inside a photo block, look for the start of a new tag
            # (Capital letters followed by : or ;) or the end of the card.
            if re.match(r'^[A-Z]+(:|;)', line) or line == 'END:VCARD':
                in_photo = False
                # If it was a tag, don't skip this line, process it below
                if line == 'END:VCARD':
                    pass 
                else:
                    # It's a new tag, fall through to processing
                    pass
            else:
                # Still inside photo data, skip
                continue

        # 3. Start/End of Card
        if line == 'BEGIN:VCARD':
            current_contact = {'phones': []}
            continue
        elif line == 'END:VCARD':
            if current_contact and (current_contact.get('Name') or current_contact.get('phones')):
                # Flatten phone numbers into Contact1, Contact2, Contact3
                phones = current_contact.pop('phones', [])
                
                # Remove duplicates while preserving order
                unique_phones = []
                [unique_phones.append(p) for p in phones if p not in unique_phones]
                
                # Assign to specific keys
                current_contact['Contact1'] = unique_phones[0] if len(unique_phones) > 0 else ""
                current_contact['Contact2'] = unique_phones[1] if len(unique_phones) > 1 else ""
                current_contact['Contact3'] = unique_phones[2] if len(unique_phones) > 2 else ""
                
                # Ensure other fields exist
                current_contact.setdefault('Email', '')
                current_contact.setdefault('Address', '')
                
                contacts.append(current_contact)
            current_contact = {}
            continue

        # 4. Extract Full Name (FN)
        if line.startswith('FN'):
            # Remove "FN:" or "FN;CHARSET=...:" prefix
            raw_name = re.sub(r'^FN.*?:', '', line)
            
            # Decode quoted printable if detected (contains = and hex)
            if '=' in line or 'ENCODING=QUOTED-PRINTABLE' in line:
                try:
                    # quopri handles the =4D=20=32 conversion
                    raw_name = quopri.decodestring(raw_name).decode('utf-8')
                except:
                    pass
            
            current_contact['Name'] = raw_name.strip()

        # 5. Extract Name (N) as fallback if FN was missing
        elif line.startswith('N:') or line.startswith('N;'):
            if 'Name' not in current_contact:
                parts = line.split(':')[-1].split(';')
                # Join non-empty parts (Family;Given;Middle)
                name_parts = [p.strip() for p in parts if p.strip()]
                # Reverse to get "Given Family" order
                current_contact['Name'] = " ".join(name_parts[::-1])

        # 6. Extract Phone Numbers (TEL)
        elif line.startswith('TEL'):
            # Extract the number part after the last colon
            number_str = line.split(':')[-1]
            
            # CLEANING: Remove spaces, dashes, parentheses, non-numeric chars
            # Keep only digits and the plus sign
            clean_number = re.sub(r'[^0-9+]', '', number_str)
            
            # Fix leading 00 to +
            if clean_number.startswith('00'):
                clean_number = '+' + clean_number[2:]
            
            # Optional: You can add specific logic here to format numbers 
            # e.g. removing +92 and adding 0, but standard clean is usually best.
            
            if clean_number:
                current_contact['phones'].append(clean_number)
                
        # 7. Extract Email
        elif line.startswith('EMAIL'):
            email_str = line.split(':')[-1]
            if '@' in email_str:
                current_contact['Email'] = email_str.strip()

    return contacts

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
        contacts_with_email = 0
        if not contacts_df.empty and "Email" in contacts_df.columns:
            contacts_with_email = len(contacts_df[contacts_df["Email"].notna() & (contacts_df["Email"] != "")])
        st.metric("📧 With Email", contacts_with_email)
    
    with col3:
        contacts_with_address = 0
        if not contacts_df.empty and "Address" in contacts_df.columns:
            contacts_with_address = len(contacts_df[contacts_df["Address"].notna() & (contacts_df["Address"] != "")])
        st.metric("🏠 With Address", contacts_with_address)
    
    with col4:
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
        # Create a boolean mask for search
        mask = filtered_contacts["Name"].str.contains(search_term, case=False, na=False)
        mask |= filtered_contacts["Contact1"].str.contains(search_term, case=False, na=False)
        
        if "Contact2" in filtered_contacts.columns:
            mask |= filtered_contacts["Contact2"].str.contains(search_term, case=False, na=False)
        if "Contact3" in filtered_contacts.columns:
            mask |= filtered_contacts["Contact3"].str.contains(search_term, case=False, na=False)
            
        filtered_contacts = filtered_contacts[mask]
    
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
    
    st.info(f"**Showing {len(filtered_contacts)} of {len(contacts_df)} contacts**")
    
    if filtered_contacts.empty:
        st.warning("No contacts found matching your criteria.")
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
    """Import contacts from VCF file with Robust Parsing"""
    st.subheader("📤 Import Contacts from VCF")
    
    st.info("""
    **Instructions:**
    - Upload a VCF (vCard) file exported from your phone contacts.
    - The system will **automatically clean** names (fix encoding like '=4D') and numbers (remove dashes).
    - It supports parsing up to **3 numbers** per contact.
    """)
    
    uploaded_file = st.file_uploader("Choose a VCF file", type=['vcf'], key="vcf_uploader")
    
    if uploaded_file is not None:
        # Read file bytes
        file_bytes = uploaded_file.read()
        
        # Parse using the new robust function
        contacts = parse_vcf_content(file_bytes)
        
        if contacts:
            st.success(f"✅ Successfully parsed {len(contacts)} contacts from VCF file!")
            
            # Convert to DataFrame for preview
            preview_df = pd.DataFrame(contacts)
            
            # Ensure columns exist for display even if empty
            required_cols = ['Name', 'Contact1', 'Contact2', 'Contact3', 'Email']
            for col in required_cols:
                if col not in preview_df.columns:
                    preview_df[col] = ""
            
            # Reorder for clean preview
            cols_to_show = [c for c in required_cols if c in preview_df.columns]
            
            st.subheader("📋 Preview (Cleaned Data)")
            st.dataframe(preview_df[cols_to_show].head(20), use_container_width=True)
            
            if len(contacts) > 20:
                st.info(f"... and {len(contacts) - 20} more contacts")
            
            # Import options
            st.subheader("🚀 Import Options")
            
            col1, col2 = st.columns(2)
            
            with col1:
                import_all = st.button("📥 Import All Contacts to Sheet", use_container_width=True, type="primary")
            
            if import_all:
                import_contacts_to_sheet(contacts)
        
        else:
            st.error("❌ No valid contacts found. The file might be empty, encrypted, or corrupted.")

def import_contacts_to_sheet(contacts):
    """Import parsed contacts to Google Sheets"""
    if not contacts:
        st.error("❌ No contacts to import!")
        return
    
    # Convert contacts to list of lists for batch import
    contacts_batch = []
    for contact in contacts:
        contacts_batch.append([
            contact.get("Name", "Unknown"),
            contact.get("Contact1", ""),
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
