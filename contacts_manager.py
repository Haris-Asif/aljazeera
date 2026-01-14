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

# --- HELPER FUNCTIONS ---

def clean_phone_number(phone_str):
    """
    Standardizes phone numbers to 03xxxxxxxxx format.
    - Removes non-digits.
    - Replaces 92 prefix with 0.
    - Adds leading 0 if missing.
    """
    if not phone_str:
        return ""
    
    # 1. Remove all non-numeric characters
    clean = re.sub(r'\D', '', str(phone_str))
    
    # 2. Handle Country Code (92... -> 0...)
    if clean.startswith('92'):
        clean = '0' + clean[2:]
        
    # 3. Handle Missing Leading Zero (300... -> 0300...)
    # Logic: If it's 10 digits and starts with 3, assume it's a mobile missing the 0
    if len(clean) == 10 and clean.startswith('3'):
        clean = '0' + clean
        
    return clean

def parse_vcf_content(file_content):
    """
    Robust VCF parser. Handles VCF 2.1, Quoted-Printable, and massive photos.
    Returns a list of dicts with keys: Name, Contact1, Contact2, Contact3, Email, Address.
    """
    contacts = []
    current_contact = {}
    in_photo = False
    
    # Decode content safely
    if isinstance(file_content, bytes):
        try:
            content_str = file_content.decode('utf-8')
        except UnicodeDecodeError:
            content_str = file_content.decode('latin-1')
    else:
        content_str = file_content

    lines = content_str.splitlines()

    for line in lines:
        line = line.strip()
        if not line: continue
            
        # --- 1. Skip Photo Blocks ---
        if line.startswith('PHOTO'):
            in_photo = True
            continue
        if in_photo:
            # Detect end of photo block (start of new field or end of card)
            if re.match(r'^[A-Z]+(:|;)', line) or line == 'END:VCARD':
                in_photo = False
                if line == 'END:VCARD': pass 
                else: pass # Process this line as a new tag
            else:
                continue

        # --- 2. Start/End Logic ---
        if line == 'BEGIN:VCARD':
            current_contact = {'phones': [], 'raw_phones': []}
            continue
        elif line == 'END:VCARD':
            if current_contact and (current_contact.get('Name') or current_contact.get('phones')):
                # Process collected phones
                unique_phones = []
                for p in current_contact['phones']:
                    if p not in unique_phones:
                        unique_phones.append(p)
                
                # Fill slots
                current_contact['Contact1'] = unique_phones[0] if len(unique_phones) > 0 else ""
                current_contact['Contact2'] = unique_phones[1] if len(unique_phones) > 1 else ""
                current_contact['Contact3'] = unique_phones[2] if len(unique_phones) > 2 else ""
                
                # Defaults
                current_contact.setdefault('Name', 'Unknown')
                current_contact.setdefault('Email', '')
                current_contact.setdefault('Address', '')
                
                # Cleanup internal keys
                current_contact.pop('phones', None)
                current_contact.pop('raw_phones', None)
                
                contacts.append(current_contact)
            current_contact = {}
            continue

        # --- 3. Extract Name ---
        if line.startswith('FN'):
            raw_name = re.sub(r'^FN.*?:', '', line)
            # Decode quoted printable
            if '=' in line or 'ENCODING=QUOTED-PRINTABLE' in line:
                try:
                    raw_name = quopri.decodestring(raw_name).decode('utf-8')
                except: pass
            current_contact['Name'] = raw_name.strip()

        elif line.startswith('N:') or line.startswith('N;'):
            if 'Name' not in current_contact:
                parts = line.split(':')[-1].split(';')
                name_parts = [p.strip() for p in parts if p.strip()]
                current_contact['Name'] = " ".join(name_parts[::-1]) # First Last

        # --- 4. Extract & Clean Phones ---
        elif line.startswith('TEL'):
            number_part = line.split(':')[-1]
            cleaned = clean_phone_number(number_part)
            if cleaned:
                current_contact['phones'].append(cleaned)

        # --- 5. Extract Email ---
        elif line.startswith('EMAIL'):
            email_part = line.split(':')[-1]
            if '@' in email_part:
                current_contact['Email'] = email_part.strip()

    return contacts

# --- UI COMPONENTS ---

def show_contacts_manager():
    st.header("👥 Contacts Management")
    
    # 1. Load Data
    contacts_df = load_contacts()
    if not contacts_df.empty:
        contacts_df["SheetRowNum"] = [i + 2 for i in range(len(contacts_df))]
    
    # 2. Metrics Bar
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📇 Total Contacts", len(contacts_df))
    with col2:
        if not contacts_df.empty and "Email" in contacts_df.columns:
            cnt = len(contacts_df[contacts_df["Email"].notna() & (contacts_df["Email"] != "")])
            st.metric("📧 With Email", cnt)
    with col3:
        if not contacts_df.empty and "Address" in contacts_df.columns:
            cnt = len(contacts_df[contacts_df["Address"].notna() & (contacts_df["Address"] != "")])
            st.metric("🏠 With Address", cnt)
    with col4:
        dup_cnt = 0
        if not contacts_df.empty and "Contact2" in contacts_df.columns:
             dup_cnt = len(contacts_df[contacts_df["Contact2"].notna() & (contacts_df["Contact2"] != "")])
        st.metric("📱 Multiple Numbers", dup_cnt)
    
    # 3. Tabs
    tab1, tab2, tab3 = st.tabs(["📋 View & Edit", "➕ Add Manual", "📤 Bulk Import (VCF)"])
    
    with tab1:
        show_contacts_view(contacts_df)
    with tab2:
        show_add_contact_form(contacts_df) # Pass DF for duplicate checking
    with tab3:
        show_import_contacts(contacts_df)  # Pass DF for duplicate checking

def show_contacts_view(contacts_df):
    """View, Search, and Delete Contacts"""
    st.subheader("📋 Directory")
    
    if contacts_df.empty:
        st.info("Directory is empty.")
        return
    
    # Search/Filter UI
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search = st.text_input("🔍 Search", placeholder="Name or Number...")
    with c2:
        filter_opt = st.selectbox("Filter", ["All", "With Email", "With Address"])
    with c3:
        sort_opt = st.selectbox("Sort", ["Name A-Z", "Recent"])
        
    # Logic
    df_show = contacts_df.copy()
    
    # Filter
    if search:
        mask = df_show["Name"].str.contains(search, case=False, na=False)
        for col in ["Contact1", "Contact2", "Contact3"]:
            if col in df_show.columns:
                mask |= df_show[col].astype(str).str.contains(search, case=False, na=False)
        df_show = df_show[mask]
        
    if filter_opt == "With Email" and "Email" in df_show.columns:
        df_show = df_show[df_show["Email"].str.len() > 0]
    elif filter_opt == "With Address" and "Address" in df_show.columns:
        df_show = df_show[df_show["Address"].str.len() > 0]
        
    # Sort
    if sort_opt == "Name A-Z":
        df_show = df_show.sort_values("Name")
    elif sort_opt == "Recent":
        # Assuming row order implies recency if no timestamp
        df_show = df_show.sort_index(ascending=False)
        
    st.caption(f"Showing {len(df_show)} contacts")
    
    # Editor
    df_show.insert(0, "Select", False)
    edited = st.data_editor(
        df_show, 
        hide_index=True, 
        column_config={"Select": st.column_config.CheckboxColumn(required=True)},
        use_container_width=True,
        key="editor_contacts"
    )
    
    # Actions
    selected = edited[edited["Select"]]
    if not selected.empty:
        st.error(f"{len(selected)} contacts selected for action.")
        if st.button("🗑️ Delete Selected", type="primary"):
            rows = selected["SheetRowNum"].tolist()
            if delete_contacts_from_sheet(rows):
                st.success("Deleted!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Delete failed.")

def show_add_contact_form(existing_df):
    """Manual Entry with Duplicate Check"""
    st.subheader("➕ New Contact")
    
    with st.form("manual_add"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Name*")
            con1 = st.text_input("Primary Phone*", placeholder="03xxxxxxxxx")
            con2 = st.text_input("Secondary Phone")
        with c2:
            email = st.text_input("Email")
            addr = st.text_area("Address", height=105)
            
        btn = st.form_submit_button("Save Contact")
        
    if btn:
        if not name or not con1:
            st.error("Name and Primary Phone are required.")
            return
            
        # Clean Inputs
        c1_clean = clean_phone_number(con1)
        c2_clean = clean_phone_number(con2)
        
        # Check Duplicate
        is_dup = False
        if not existing_df.empty:
            all_existing = set(existing_df["Contact1"].astype(str))
            if "Contact2" in existing_df.columns:
                all_existing.update(existing_df["Contact2"].astype(str))
            
            if c1_clean in all_existing:
                st.warning(f"⚠️ Contact with number {c1_clean} already exists!")
                is_dup = True
        
        if not is_dup:
            data = [name, c1_clean, c2_clean, "", email, addr, ""]
            if add_contact_to_sheet(data):
                st.success("Saved!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Save failed.")

def show_import_contacts(existing_df):
    """
    Enterprise Grade VCF Import
    - Checks duplicates against DB
    - Shows stats before commit
    - Auto-cleans formats
    """
    st.subheader("📤 Import VCF")
    
    uploaded = st.file_uploader("Upload .vcf file", type=["vcf"])
    
    if uploaded:
        bytes_data = uploaded.read()
        parsed_raw = parse_vcf_content(bytes_data)
        
        if not parsed_raw:
            st.error("No contacts parsed.")
            return
            
        # --- DUPLICATE CHECKING LOGIC ---
        new_contacts = []
        duplicate_log = []
        
        # Build Set of Existing Numbers for O(1) Lookup
        existing_numbers = set()
        if not existing_df.empty:
            # Gather all numbers from all columns, drop empties/NaNs
            for col in ["Contact1", "Contact2", "Contact3"]:
                if col in existing_df.columns:
                    # clean while loading to set to ensure match
                    cleaned_series = existing_df[col].astype(str).apply(lambda x: clean_phone_number(x))
                    existing_numbers.update(cleaned_series.dropna().tolist())
        # Remove empty string if it got in
        existing_numbers.discard("")

        for contact in parsed_raw:
            # Check all 3 possible numbers of the new contact
            c1 = contact.get('Contact1', '')
            c2 = contact.get('Contact2', '')
            c3 = contact.get('Contact3', '')
            
            # Check if ANY of the new contact's numbers exist in DB
            is_dup = False
            if c1 and c1 in existing_numbers: is_dup = True
            if c2 and c2 in existing_numbers: is_dup = True
            if c3 and c3 in existing_numbers: is_dup = True
            
            if is_dup:
                duplicate_log.append(contact)
            else:
                new_contacts.append(contact)
                # Add to set so we don't import duplicates within the VCF itself
                if c1: existing_numbers.add(c1)
        
        # --- DISPLAY STATS ---
        st.divider()
        col1, col2, col3 = st.columns(3)
        col1.metric("📂 VCF Total", len(parsed_raw))
        col2.metric("✨ New Contacts", len(new_contacts))
        col3.metric("🚫 Duplicates Skipped", len(duplicate_log))
        
        # --- ACTION AREA ---
        if new_contacts:
            st.success(f"Ready to import **{len(new_contacts)}** new contacts.")
            
            # Preview Toggle
            with st.expander("View Data Preview"):
                st.dataframe(pd.DataFrame(new_contacts).head(50), use_container_width=True)
            
            if st.button("🚀 Import New Contacts Only", type="primary"):
                # Prepare Batch
                batch_data = []
                for c in new_contacts:
                    batch_data.append([
                        c.get("Name", "Unknown"),
                        c.get("Contact1", ""),
                        c.get("Contact2", ""),
                        c.get("Contact3", ""),
                        c.get("Email", ""),
                        c.get("Address", ""),
                        "" # Notes
                    ])
                
                # Execute
                with st.spinner("Importing..."):
                    added = add_contacts_batch(batch_data)
                
                if added > 0:
                    st.balloons()
                    st.success(f"Successfully imported {added} contacts!")
                    st.cache_data.clear()
                    # Optional: Rerun to refresh view
                    # st.rerun() 
                else:
                    st.error("Import failed via API.")
        else:
            st.warning("All contacts in this file already exist in your system!")
            
        # Show duplicates list if requested
        if duplicate_log:
            with st.expander(f"View Skipped Duplicates ({len(duplicate_log)})"):
                st.dataframe(pd.DataFrame(duplicate_log), use_container_width=True)
