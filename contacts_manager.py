import streamlit as st
import pandas as pd
import time
from utils import (load_contacts, add_contact_to_sheet, add_contacts_batch, 
                  delete_contacts_from_sheet, parse_vcf_file, load_plot_data)

def show_contacts_manager():
    st.header("📇 Contact Management")
    
    # Load data
    contacts_df = load_contacts()
    plots_df = load_plot_data().fillna("")
    
    # Add row numbers to contacts for deletion
    if not contacts_df.empty:
        contacts_df["SheetRowNum"] = [i + 2 for i in range(len(contacts_df))]
    
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
                    st.write(f"**Name:** {contact['Name']}")
                    st.write(f"**Contact 1:** {contact['Contact1']}")
                    st.write(f"**Contact 2:** {contact['Contact2']}")
                    st.write(f"**Contact 3:** {contact['Contact3']}")
                    st.write(f"**Email:** {contact['Email']}")
            
            # Button to import all contacts
            if st.button("Import All Contacts", key="import_all"):
                success_count = 0
                total_contacts = len(contacts)
                
                # Create progress bar and status
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Process in batches to respect API limits
                for i in range(0, total_contacts, 10):  # Using BATCH_SIZE from utils
                    batch = contacts[i:i+10]
                    batch_success = 0
                    
                    for contact in batch:
                        contact_data = [
                            contact["Name"],
                            contact["Contact1"],
                            contact["Contact2"],
                            contact["Contact3"],
                            contact["Email"],
                            contact["Address"]
                        ]
                        if add_contact_to_sheet(contact_data):
                            batch_success += 1
                            success_count += 1
                    
                    # Update progress
                    progress = min((i + len(batch)) / total_contacts, 1.0)
                    progress_bar.progress(progress)
                    status_text.text(f"Processed {i + len(batch)}/{total_contacts} contacts...")
                    
                    # Small delay between batches
                    time.sleep(1)  # Using API_DELAY from utils
                
                # Final status update
                progress_bar.progress(1.0)
                if success_count == total_contacts:
                    status_text.success(f"✅ Successfully imported all {success_count} contacts!")
                else:
                    status_text.warning(f"⚠️ Imported {success_count} out of {total_contacts} contacts. Some may have failed due to API limits.")
                
                # Clear cache and refresh
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
        st.subheader("Contact Details")
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
                
                # Quick actions
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📞 Call", key=f"call_{idx}"):
                        phone = row.get('Contact1', '')
                        if phone:
                            st.markdown(f'<a href="tel:{phone}" style="display: inline-block; padding: 0.5rem 1rem; background-color: #25D366; color: white; text-decoration: none; border-radius: 0.5rem;">Call {phone}</a>', 
                                      unsafe_allow_html=True)
                
                with col2:
                    if st.button("💬 WhatsApp", key=f"whatsapp_{idx}"):
                        phone = row.get('Contact1', '')
                        if phone:
                            # Generate basic WhatsApp link
                            cleaned_phone = ''.join(filter(str.isdigit, phone))
                            if cleaned_phone.startswith('03') and len(cleaned_phone) == 11:
                                cleaned_phone = '92' + cleaned_phone[1:]
                            elif len(cleaned_phone) == 10:
                                cleaned_phone = '92' + cleaned_phone
                            
                            whatsapp_link = f"https://wa.me/{cleaned_phone}"
                            st.markdown(f'<a href="{whatsapp_link}" target="_blank" style="display: inline-block; padding: 0.5rem 1rem; background-color: #25D366; color: white; text-decoration: none; border-radius: 0.5rem;">Open WhatsApp</a>', 
                                      unsafe_allow_html=True)
    else:
        st.info("No contacts found. Add a new contact using the form above.")
