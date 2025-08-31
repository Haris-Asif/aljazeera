import streamlit as st
import pandas as pd
import gspread
import re
import difflib
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Constants
SPREADSHEET_NAME = "Al-Jazeera"
PLOTS_SHEET = "Plots"
CONTACTS_SHEET = "Contacts"
LEADS_SHEET = "Leads"
ACTIVITIES_SHEET = "LeadActivities"  # New sheet for tracking lead activities

# Streamlit setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

# --- Helpers ---
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text):
    text = str(text or "")
    parts = re.split(r"[,\s]+", text)
    return [clean_number(p) for p in parts if clean_number(p)]

def parse_price(price_str):
    try:
        price_str = str(price_str).lower().replace(",", "").replace("cr", "00").replace("crore", "00")
        numbers = re.findall(r"\d+\.?\d*", price_str)
        return float(numbers[0]) if numbers else None
    except:
        return None

def get_all_unique_features(df):
    feature_set = set()
    for f in df["Features"].fillna("").astype(str):
        parts = [p.strip().lower() for p in f.split(",") if p.strip()]
        feature_set.update(parts)
    return sorted(feature_set)

def fuzzy_feature_match(row_features, selected_features):
    row_features = [f.strip().lower() for f in str(row_features or "").split(",")]
    for sel in selected_features:
        match = difflib.get_close_matches(sel.lower(), row_features, n=1, cutoff=0.7)
        if match:
            return True
    return False

# Google Sheets
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def load_plot_data():
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
    df = pd.DataFrame(sheet.get_all_records())
    df["SheetRowNum"] = [i + 2 for i in range(len(df))]  # Start from row 2
    return df

def load_contacts():
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
    return pd.DataFrame(sheet.get_all_records())

def load_leads():
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(LEADS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty:
            # Initialize with empty dataframe with proper columns
            df = pd.DataFrame(columns=[
                "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
                "Priority", "Property Interest", "Last Contact", "Next Action", 
                "Notes", "Assigned To"
            ])
        return df
    except gspread.exceptions.WorksheetNotFound:
        # Create the worksheet if it doesn't exist
        sheet = get_gsheet_client().open(SPREADSHEET_NAME)
        worksheet = sheet.add_worksheet(title=LEADS_SHEET, rows=100, cols=12)
        # Add headers
        worksheet.append_row([
            "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
            "Priority", "Property Interest", "Last Contact", "Next Action", 
            "Notes", "Assigned To"
        ])
        return pd.DataFrame(columns=[
            "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
            "Priority", "Property Interest", "Last Contact", "Next Action", 
            "Notes", "Assigned To"
        ])

# NEW: Load lead activities
def load_lead_activities():
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(ACTIVITIES_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty:
            # Initialize with empty dataframe with proper columns
            df = pd.DataFrame(columns=[
                "Timestamp", "Lead Name", "Lead Phone", "Activity Type", 
                "Details", "Next Steps", "Follow-up Date"
            ])
        return df
    except gspread.exceptions.WorksheetNotFound:
        # Create the worksheet if it doesn't exist
        sheet = get_gsheet_client().open(SPREADSHEET_NAME)
        worksheet = sheet.add_worksheet(title=ACTIVITIES_SHEET, rows=100, cols=7)
        # Add headers
        worksheet.append_row([
            "Timestamp", "Lead Name", "Lead Phone", "Activity Type", 
            "Details", "Next Steps", "Follow-up Date"
        ])
        return pd.DataFrame(columns=[
            "Timestamp", "Lead Name", "Lead Phone", "Activity Type", 
            "Details", "Next Steps", "Follow-up Date"
        ])

# NEW: Save lead activity
def save_lead_activity(activity_df):
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(ACTIVITIES_SHEET)
    # Clear existing data
    sheet.clear()
    # Add headers
    sheet.append_row([
        "Timestamp", "Lead Name", "Lead Phone", "Activity Type", 
        "Details", "Next Steps", "Follow-up Date"
    ])
    # Add data
    for _, row in activity_df.iterrows():
        sheet.append_row([
            row.get("Timestamp", ""),
            row.get("Lead Name", ""),
            row.get("Lead Phone", ""),
            row.get("Activity Type", ""),
            row.get("Details", ""),
            row.get("Next Steps", ""),
            row.get("Follow-up Date", "")
        ])

def save_leads(df):
    sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(LEADS_SHEET)
    # Clear existing data
    sheet.clear()
    # Add headers
    sheet.append_row([
        "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
        "Priority", "Property Interest", "Last Contact", "Next Action", 
        "Notes", "Assigned To"
    ])
    # Add data
    for _, row in df.iterrows():
        sheet.append_row([
            row.get("Timestamp", ""),
            row.get("Name", ""),
            row.get("Phone", ""),
            row.get("Email", ""),
            row.get("Source", ""),
            row.get("Status", ""),
            row.get("Priority", ""),
            row.get("Property Interest", ""),
            row.get("Last Contact", ""),
            row.get("Next Action", ""),
            row.get("Notes", ""),
            row.get("Assigned To", "")
        ])

def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.now() - timedelta(days=days_map.get(label, 0))
    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            return None
    df["ParsedDate"] = df["Timestamp"].apply(try_parse)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

def build_name_map(df):
    contact_to_name = {}
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name")).strip()
        contacts = extract_numbers(row.get("Extracted Contact"))
        for c in contacts:
            if c and c not in contact_to_name:
                contact_to_name[c] = name
    name_groups = {}
    for c, name in contact_to_name.items():
        name_groups.setdefault(name, set()).add(c)
    merged = {}
    for name, numbers in name_groups.items():
        for c in numbers:
            merged[c] = name
    name_set = {}
    for _, row in df.iterrows():
        numbers = extract_numbers(row.get("Extracted Contact"))
        for c in numbers:
            if c in merged:
                name_set[merged[c]] = True
    
    # Create a list of dealer names with serial numbers
    numbered_dealers = []
    for i, name in enumerate(sorted(name_set.keys()), 1):
        numbered_dealers.append(f"{i}. {name}")
    
    return numbered_dealers, merged

def sector_matches(f, c):
    if not f:
        return True
    f = f.replace(" ", "").upper()
    c = str(c).replace(" ", "").upper())
    return f in c if "/" not in f else f == c

def safe_dataframe(df):
    try:
        df = df.copy()
        df = df.drop(columns=["ParsedDate", "ParsedPrice"], errors="ignore")
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
        return df
    except Exception as e:
        st.error(f"⚠️ Error displaying table: {e}")
        return pd.DataFrame()

# ---------- WhatsApp utilities (split + encode aware) ----------
def _extract_int(val):
    """Extract first integer from a string; used for numeric sorting of Plot No."""
    try:
        m = re.search(r"\d+", str(val))
        return int(m.group()) if m else float("inf")
    except:
        return float("inf")

def _url_encode_for_whatsapp(text: str) -> str:
    """Encode minimally for wa.me URL (matching your existing approach)."""
    # Keep same encoding style you used, so links behave consistently
    return text.replace(" ", "%20").replace("\n", "%0A")

def _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800):
    """
    Given a list of text blocks, accumulate them into chunks that
    satisfy both plain text and encoded URL length limits.
    """
    chunks = []
    current = ""

    for block in blocks:
        candidate = current + block
        # Check both plain and encoded limits
        if len(candidate) > plain_limit or len(_url_encode_for_whatsapp(candidate)) > encoded_limit:
            if current:
                chunks.append(current.rstrip())
                current = ""

            # If single block is still too large, split by lines
            if len(block) > plain_limit or len(_url_encode_for_whatsapp(block)) > encoded_limit:
                lines = block.splitlines(keepends=True)
                small = ""
                for ln in lines:
                    cand2 = small + ln
                    if len(cand2) > plain_limit or len(_url_encode_for_whatsapp(cand2)) > encoded_limit:
                        if small:
                            chunks.append(small.rstrip())
                            small = ""
                        # handle very long single line (rare): hard split
                        if len(ln) > plain_limit or len(_url_encode_for_whatsapp(ln)) > encoded_limit:
                            # split the line at safe slice points
                            seg = ln
                            while seg:
                                # pick a safe slice size
                                step = min(1000, len(seg))
                                piece = seg[:step]
                                while len(_url_encode_for_whatsapp(piece)) > encoded_limit and step > 10:
                                    step -= 10
                                    piece = seg[:step]
                                chunks.append(piece.rstrip())
                                seg = seg[step:]
                        else:
                            small = ln
                    else:
                        small = cand2
                if small:
                    chunks.append(small.rstrip())
            else:
                current = block
        else:
            current = candidate

    if current:
        chunks.append(current.rstrip())

    return chunks

# WhatsApp message generation (sorted by Plot No asc, URL-safe chunking)
def generate_whatsapp_messages(df):
    # Build list of eligible rows (keep your intentional filters)
    filtered = []
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

        filtered.append({
            "Sector": sector,
            "Plot No": plot_no,
            "Plot Size": size,
            "Demand": price,
            "Street No": street
        })

    # De-duplicate on (Sector, Plot No, Plot Size, Demand)
    seen = set()
    unique = []
    for row in filtered:
        key = (row["Sector"], row["Plot No"], row["Plot Size"], row["Demand"])
        if key not in seen:
            seen.add(key)
            unique.append(row)

    # Group by (Sector, Plot Size) as before
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    # Build per-group message blocks with sorting by Plot No ascending
    blocks = []
    for (sector, size), listings in grouped.items():
        # Sort primarily by Plot No ascending (numeric-first)
        listings = sorted(
            listings,
            key=lambda x: (_extract_int(x["Plot No"]), str(x["Plot No"]))
        )

        lines = []
        for r in listings:
            if sector.startswith("I-15/"):
                # Keep your I-15 line format but ordering still by Plot No due to sort above
                lines.append(f"St: {r['Street No']} | P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")
            else:
                lines.append(f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")

        header = f"*Available Options in {sector} Size: {size}*\n"
        block = header + "\n".join(lines) + "\n\n"
        blocks.append(block)

    # Split into URL-safe chunks
    # Conservative caps: plain <= 3000 chars, encoded <= 1800 chars
    messages = _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800)

    return messages

# Delete rows from Google Sheet
def delete_rows_from_sheet(row_numbers):
    try:
        client = get_gsheet_client()
        sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        
        valid_rows = [row_num for row_num in row_numbers if row_num > 1]
        if not valid_rows:
            return True
            
        valid_rows.sort(reverse=True)
        
        BATCH_SIZE = 10
        for i in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[i:i+BATCH_SIZE]
            for row_num in batch:
                try:
                    sheet.delete_rows(row_num)
                except Exception as e:
                    st.error(f"Error deleting row {row_num}: {str(e)}")
                    continue
                    
            import time
            time.sleep(1)
            
        return True
    except Exception as e:
        st.error(f"Error in delete operation: {str(e)}")
        return False

# Function to create grouped view with colors for duplicate entries
def create_duplicates_view(df):
    if df.empty:
        return None, pd.DataFrame()
    
    # Correct usage of astype
    df["GroupKey"] = df["Sector"].astype(str) + "|" + df["Plot No"].astype(str) + "|" + df["Street No"].astype(str) + "|" + df["Plot Size"].astype(str)
    
    group_counts = df["GroupKey"].value_counts()
    
    duplicate_groups = group_counts[group_counts >= 2].index
    duplicate_df = df[df["GroupKey"].isin(duplicate_groups)]
    
    if duplicate_df.empty:
        return None, duplicate_df
    
    duplicate_df = duplicate_df.sort_values(by="GroupKey")
    
    unique_groups = duplicate_df["GroupKey"].unique()
    color_map = {}
    colors = ["#FFCCCC", "#CCFFCC", "#CCCCFF", "#FFFFCC", "#FFCCFF", "#CCFFFF", "#FFE5CC", "#E5CCFF"]
    
    for i, group in enumerate(unique_groups):
        color_map[group] = colors[i % len(colors)]
    
    def apply_row_color(row):
        return [f"background-color: {color_map[row['GroupKey']]}"] * len(row)
    
    styled_df = duplicate_df.style.apply(apply_row_color, axis=1)
    return styled_df, duplicate_df

# --- NEW: Lead Timeline Functions ---
def display_lead_timeline(lead_name, lead_phone):
    st.subheader(f"Timeline for: {lead_name}")
    
    # Load activities
    activities_df = load_lead_activities()
    
    # Filter activities for this lead
    lead_activities = activities_df[
        (activities_df["Lead Name"] == lead_name) & 
        (activities_df["Lead Phone"] == lead_phone)
    ]
    
    if lead_activities.empty:
        st.info("No activities recorded for this lead yet.")
        return
    
    # Sort by timestamp (newest first)
    lead_activities = lead_activities.sort_values("Timestamp", ascending=False)
    
    # Display timeline
    for _, activity in lead_activities.iterrows():
        with st.container():
            col1, col2 = st.columns([1, 4])
            
            with col1:
                timestamp = activity["Timestamp"]
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    except:
                        pass
                
                if isinstance(timestamp, datetime):
                    st.write(timestamp.strftime("%b %d, %Y"))
                    st.write(timestamp.strftime("%I:%M %p"))
                else:
                    st.write(str(timestamp))
            
            with col2:
                activity_type = activity["Activity Type"]
                
                # Color code based on activity type
                if activity_type == "Call":
                    st.markdown(f"**📞 Phone Call**")
                    color = "#E3F2FD"
                elif activity_type == "Meeting":
                    st.markdown(f"**👥 Meeting**")
                    color = "#E8F5E9"
                elif activity_type == "Email":
                    st.markdown(f"**📧 Email**")
                    color = "#FFF3E0"
                elif activity_type == "WhatsApp":
                    st.markdown(f"**💬 WhatsApp**")
                    color = "#E8F5E9"
                elif activity_type == "Status Update":
                    st.markdown(f"**🔄 Status Update**")
                    color = "#F3E5F5"
                else:
                    st.markdown(f"**📝 Note**")
                    color = "#F5F5F5"
                
                st.markdown(
                    f"""<div style="background-color: {color}; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                    <p>{activity['Details']}</p>
                    </div>""", 
                    unsafe_allow_html=True
                )
                
                if activity["Next Steps"] and pd.notna(activity["Next Steps"]):
                    st.markdown(f"**Next Steps:** {activity['Next Steps']}")
                
                if activity["Follow-up Date"] and pd.notna(activity["Follow-up Date"]):
                    st.markdown(f"**Follow-up:** {activity['Follow-up Date']}")
            
            st.markdown("---")

# --- NEW: Lead Management Functions ---
def leads_page():
    st.header("👥 Lead Management")
    
    # Load leads data
    leads_df = load_leads()
    
    # Calculate metrics for dashboard
    total_leads = len(leads_df)
    
    # Count leads by status
    status_counts = leads_df["Status"].value_counts() if "Status" in leads_df.columns else pd.Series()
    new_leads = status_counts.get("New", 0)
    contacted_leads = status_counts.get("Contacted", 0)
    negotiation_leads = status_counts.get("Negotiation", 0)
    
    # Count overdue actions
    today = datetime.now().date()
    if "Next Action" in leads_df.columns:
        overdue_actions = sum(
            1 for date_str in leads_df["Next Action"] 
            if date_str and pd.notna(date_str) and 
            datetime.strptime(str(date_str), "%Y-%m-%d").date() < today
        )
    else:
        overdue_actions = 0
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Leads", total_leads)
    with col2:
        st.metric("New Leads", new_leads)
    with col3:
        st.metric("In Negotiation", negotiation_leads)
    with col4:
        st.metric("Overdue Actions", overdue_actions, delta=f"{overdue_actions} need attention", 
                 delta_color="inverse" if overdue_actions > 0 else "normal")
    
    # Display overdue actions as notifications
    if overdue_actions > 0:
        st.warning(f"⚠️ You have {overdue_actions} overdue follow-up actions. Check the 'Next Action' column.")
    
    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["All Leads", "Add New Lead", "Lead Timeline", "Reports"])
    
    with tab1:
        st.subheader("All Leads")
        
        if leads_df.empty:
            st.info("No leads found. Add your first lead in the 'Add New Lead' tab.")
        else:
            # Filters
            col1, col2, col3 = st.columns(3)
            with col1:
                status_filter = st.selectbox("Filter by Status", 
                                           options=["All"] + list(leads_df["Status"].unique()) if "Status" in leads_df.columns else ["All"])
            with col2:
                priority_filter = st.selectbox("Filter by Priority", 
                                             options=["All"] + list(leads_df["Priority"].unique()) if "Priority" in leads_df.columns else ["All"])
            with col3:
                source_filter = st.selectbox("Filter by Source", 
                                           options=["All"] + list(leads_df["Source"].unique()) if "Source" in leads_df.columns else ["All"])
            
            # Apply filters
            filtered_leads = leads_df.copy()
            if status_filter != "All":
                filtered_leads = filtered_leads[filtered_leads["Status"] == status_filter]
            if priority_filter != "All":
                filtered_leads = filtered_leads[filtered_leads["Priority"] == priority_filter]
            if source_filter != "All":
                filtered_leads = filtered_leads[filtered_leads["Source"] == source_filter]
            
            # Display leads table
            st.dataframe(filtered_leads, use_container_width=True)
            
            # Lead actions
            if not filtered_leads.empty:
                st.subheader("Update Lead")
                lead_names = filtered_leads["Name"].tolist()
                selected_lead = st.selectbox("Select Lead to Update", options=lead_names, key="update_lead_select")
                
                if selected_lead:
                    lead_data = filtered_leads[filtered_leads["Name"] == selected_lead].iloc[0]
                    
                    with st.form("update_lead_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_status = st.selectbox("Status", 
                                                    options=["New", "Contacted", "Follow-up", "Meeting Scheduled", 
                                                            "Negotiation", "Offer Made", "Deal Closed (Won)", "Not Interested (Lost)"],
                                                    index=0 if pd.isna(lead_data.get("Status")) else 
                                                    ["New", "Contacted", "Follow-up", "Meeting Scheduled", 
                                                     "Negotiation", "Offer Made", "Deal Closed (Won)", "Not Interested (Lost)"].index(lead_data.get("Status")))
                            new_priority = st.selectbox("Priority", 
                                                      options=["Low", "Medium", "High"],
                                                      index=0 if pd.isna(lead_data.get("Priority")) else 
                                                      ["Low", "Medium", "High"].index(lead_data.get("Priority")))
                            new_next_action = st.date_input("Next Action", 
                                                          value=datetime.strptime(lead_data.get("Next Action"), "%Y-%m-%d").date() 
                                                          if lead_data.get("Next Action") and pd.notna(lead_data.get("Next Action")) else datetime.now().date())
                        with col2:
                            new_last_contact = st.date_input("Last Contact", 
                                                           value=datetime.strptime(lead_data.get("Last Contact"), "%Y-%m-%d").date() 
                                                           if lead_data.get("Last Contact") and pd.notna(lead_data.get("Last Contact")) else datetime.now().date())
                            new_notes = st.text_area("Notes", value=lead_data.get("Notes", ""))
                        
                        if st.form_submit_button("Update Lead"):
                            # Update the lead in the dataframe
                            idx = leads_df[leads_df["Name"] == selected_lead].index[0]
                            leads_df.at[idx, "Status"] = new_status
                            leads_df.at[idx, "Priority"] = new_priority
                            leads_df.at[idx, "Next Action"] = new_next_action.strftime("%Y-%m-%d")
                            leads_df.at[idx, "Last Contact"] = new_last_contact.strftime("%Y-%m-%d")
                            leads_df.at[idx, "Notes"] = new_notes
                            
                            # Save to Google Sheets
                            save_leads(leads_df)
                            st.success("Lead updated successfully!")
                            st.rerun()
    
    with tab2:
        st.subheader("Add New Lead")
        
        with st.form("add_lead_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name*", placeholder="Client Name")
                phone = st.text_input("Phone*", placeholder="03XXXXXXXXX")
                email = st.text_input("Email", placeholder="client@example.com")
                source = st.selectbox("Source", 
                                    options=["Website", "WhatsApp", "Referral", "Walk-in", "Other"])
            with col2:
                status = st.selectbox("Status", 
                                    options=["New", "Contacted", "Follow-up", "Meeting Scheduled", 
                                            "Negotiation", "Offer Made", "Deal Closed (Won)", "Not Interested (Lost)"])
                priority = st.selectbox("Priority", 
                                      options=["Low", "Medium", "High"])
                property_interest = st.text_input("Property Interest", placeholder="e.g., I-10/4, 125 sq yd")
                next_action = st.date_input("Next Action", value=datetime.now().date() + timedelta(days=7))
            
            notes = st.text_area("Notes", placeholder="Any additional information about the lead")
            
            if st.form_submit_button("Add Lead"):
                if not name or not phone:
                    st.error("Name and Phone are required fields!")
                else:
                    # Create new lead entry
                    new_lead = {
                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Name": name,
                        "Phone": phone,
                        "Email": email,
                        "Source": source,
                        "Status": status,
                        "Priority": priority,
                        "Property Interest": property_interest,
                        "Last Contact": datetime.now().strftime("%Y-%m-%d"),
                        "Next Action": next_action.strftime("%Y-%m-%d"),
                        "Notes": notes,
                        "Assigned To": "Current User"  # You can modify this based on your user management
                    }
                    
                    # Add to dataframe
                    leads_df = pd.concat([leads_df, pd.DataFrame([new_lead])], ignore_index=True)
                    
                    # Save to Google Sheets
                    save_leads(leads_df)
                    st.success("Lead added successfully!")
                    st.rerun()
    
    with tab3:
        st.subheader("Lead Timeline")
        
        if leads_df.empty:
            st.info("No leads found. Add your first lead in the 'Add New Lead' tab.")
        else:
            # Select lead to view timeline
            lead_names = leads_df["Name"].tolist()
            selected_lead = st.selectbox("Select Lead", options=lead_names, key="timeline_lead_select")
            
            if selected_lead:
                lead_data = leads_df[leads_df["Name"] == selected_lead].iloc[0]
                lead_phone = lead_data["Phone"]
                
                # Display timeline
                display_lead_timeline(selected_lead, lead_phone)
                
                # Add new activity
                st.subheader("Add New Activity")
                
                with st.form("add_activity_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        activity_type = st.selectbox("Activity Type", 
                                                   options=["Call", "Meeting", "Email", "WhatsApp", "Status Update", "Note"])
                        follow_up_date = st.date_input("Follow-up Date", value=datetime.now().date() + timedelta(days=7))
                    with col2:
                        next_steps = st.text_input("Next Steps", placeholder="What needs to happen next?")
                    
                    details = st.text_area("Details*", placeholder="What was discussed?")
                    
                    if st.form_submit_button("Add Activity"):
                        if not details:
                            st.error("Details are required!")
                        else:
                            # Load existing activities
                            activities_df = load_lead_activities()
                            
                            # Create new activity
                            new_activity = {
                                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "Lead Name": selected_lead,
                                "Lead Phone": lead_phone,
                                "Activity Type": activity_type,
                                "Details": details,
                                "Next Steps": next_steps,
                                "Follow-up Date": follow_up_date.strftime("%Y-%m-%d")
                            }
                            
                            # Add to dataframe
                            activities_df = pd.concat([activities_df, pd.DataFrame([new_activity])], ignore_index=True)
                            
                            # Save to Google Sheets
                            save_lead_activity(activities_df)
                            
                            # Update last contact date in leads sheet
                            idx = leads_df[leads_df["Name"] == selected_lead].index[0]
                            leads_df.at[idx, "Last Contact"] = datetime.now().strftime("%Y-%m-%d")
                            save_leads(leads_df)
                            
                            st.success("Activity added successfully!")
                            st.rerun()
    
    with tab4:
        st.subheader("Lead Reports")
        
        if leads_df.empty:
            st.info("No leads data available for reports.")
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                # Status distribution
                st.write("**Leads by Status**")
                if "Status" in leads_df.columns:
                    status_counts = leads_df["Status"].value_counts()
                    st.bar_chart(status_counts)
                else:
                    st.info("No status data available.")
            
            with col2:
                # Source distribution
                st.write("**Leads by Source**")
                if "Source" in leads_df.columns:
                    source_counts = leads_df["Source"].value_counts()
                    st.bar_chart(source_counts)
                else:
                    st.info("No source data available.")
            
            # Upcoming actions
            st.write("**Upcoming Actions (Next 7 Days)**")
            upcoming_df = leads_df.copy()
            if "Next Action" in upcoming_df.columns:
                upcoming_df["Next Action"] = pd.to_datetime(upcoming_df["Next Action"], errors="coerce")
                next_week = datetime.now().date() + timedelta(days=7)
                upcoming_df = upcoming_df[
                    (upcoming_df["Next Action"].dt.date >= datetime.now().date()) & 
                    (upcoming_df["Next Action"].dt.date <= next_week)
                ]
                st.dataframe(upcoming_df[["Name", "Phone", "Next Action", "Status"]], use_container_width=True)
            else:
                st.info("No upcoming actions in the next 7 days.")

# --- Plots Page ---
def plots_page():
    st.header("🏡 Property Listings")
    
    # Load data
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()

    all_features = get_all_unique_features(df)

    with st.sidebar:
        st.header("🔍 Filters")
        sector_filter = st.text_input("Sector")
        plot_size_filter = st.text_input("Plot Size")
        street_filter = st.text_input("Street No")
        plot_no_filter = st.text_input("Plot No")
        contact_filter = st.text_input("Phone Number (03xxxxxxxxx)")
        price_from = st.number_input("Price From (in Lacs)", min_value=0.0, value=0.0, step=1.0)
        price_to = st.number_input("Price To (in Lacs)", min_value=0.0, value=1000.0, step=1.0)
        selected_features = st.multiselect("Select Feature(s)", options=all_features)
        date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

        # Property Type filter
        prop_type_options = ["All"]
        if "Property Type" in df.columns:
            prop_type_options += sorted([str(v).strip() for v in df["Property Type"].dropna().astype(str).unique()])
        selected_prop_type = st.selectbox("Property Type", prop_type_options)

        dealer_names, contact_to_name = build_name_map(df)
        selected_dealer = st.selectbox("Dealer Name (by contact)", [""] + dealer_names)

        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names)

    df_filtered = df.copy()

    if selected_dealer:
        actual_name = selected_dealer.split(". ", 1)[1] if ". " in selected_dealer else selected_dealer
        selected_contacts = [c for c, name in contact_to_name.items() if name == actual_name]
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(c in clean_number(x) for c in selected_contacts))]

    if selected_saved:
        row = contacts_df[contacts_df["Name"] == selected_saved].iloc[0] if not contacts_df[contacts_df["Name"] == selected_saved].empty else None
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
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street No"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No"].str.contains(plot_no_filter, case=False, na=False)]
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
            contact_row = contacts_df[contacts_df["Name"] == selected_name_whatsapp]
            if not contact_row.empty:
                row = contact_row.iloc[0]
                numbers = []
                for col in ["Contact1", "Contact2", "Contact3"]:
                    if col in row and pd.notna(row[col]):
                        numbers.append(clean_number(row[col]))
                cleaned = numbers[0] if numbers else ""

        if not cleaned:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
            return

        if len(cleaned) == 10 and cleaned.startswith("3"):
            wa_number = "92" + cleaned
        elif len(cleaned) == 11 and cleaned.startswith("03"):
            wa_number = "92" + cleaned[1:]
        elif len(cleaned) == 12 and cleaned.startswith("92"):
            wa_number = cleaned
        else:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
            return

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

# --- Main App ---
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    
    # Navigation
    page = st.sidebar.selectbox("Navigate", ["Plots", "Leads"])
    
    if page == "Plots":
        plots_page()
    else:
        leads_page()

if __name__ == "__main__":
    main()
