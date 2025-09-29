import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from utils import (load_leads, load_lead_activities, load_tasks, load_appointments,
                  save_leads, save_lead_activities, save_tasks, save_appointments,
                  generate_lead_id, generate_activity_id, generate_task_id, 
                  generate_appointment_id, calculate_lead_score, display_lead_timeline,
                  display_lead_analytics)

def show_crm_manager():
    st.header("🎯 Lead Management CRM")
    
    # Load data
    leads_df = load_leads()
    activities_df = load_lead_activities()
    tasks_df = load_tasks()
    appointments_df = load_appointments()
    
    # Calculate metrics for dashboard
    total_leads = len(leads_df) if not leads_df.empty else 0
    
    # Initialize counts safely
    new_leads = 0
    contacted_leads = 0
    negotiation_leads = 0
    won_leads = 0
    
    if not leads_df.empty and "Status" in leads_df.columns:
        status_counts = leads_df["Status"].value_counts()
        new_leads = status_counts.get("New", 0)
        contacted_leads = status_counts.get("Contacted", 0) + status_counts.get("Follow-up", 0)
        negotiation_leads = status_counts.get("Negotiation", 0) + status_counts.get("Offer Made", 0)
        won_leads = status_counts.get("Deal Closed (Won)", 0)
    
    # Count overdue actions
    today = datetime.now().date()
    overdue_tasks = 0
    if not tasks_df.empty and "Due Date" in tasks_df.columns and "Status" in tasks_df.columns:
        try:
            tasks_df["Due Date"] = pd.to_datetime(tasks_df["Due Date"], errors='coerce').dt.date
            overdue_tasks = len(tasks_df[
                (tasks_df["Status"] != "Completed") & 
                (tasks_df["Due Date"] < today)
            ])
        except:
            overdue_tasks = 0
    
    # Display metrics with enhanced styling
    st.subheader("📊 CRM Overview")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Leads", total_leads)
    with col2:
        st.metric("New Leads", new_leads)
    with col3:
        st.metric("In Negotiation", negotiation_leads)
    with col4:
        st.metric("Deals Closed", won_leads)
    with col5:
        st.metric("Overdue Tasks", overdue_tasks, delta=f"{overdue_tasks} need attention", 
                 delta_color="inverse" if overdue_tasks > 0 else "normal")
    
    # Display notifications
    if overdue_tasks > 0:
        st.warning(f"⚠️ You have {overdue_tasks} overdue tasks. Check the Tasks tab.")
    
    # Upcoming appointments
    upcoming_appointments = pd.DataFrame()
    if not appointments_df.empty and "Date" in appointments_df.columns:
        try:
            appointments_df["Date"] = pd.to_datetime(appointments_df["Date"], errors='coerce').dt.date
            upcoming_appointments = appointments_df[
                (appointments_df["Date"] >= today) &
                (appointments_df["Date"] <= today + timedelta(days=7))
            ]
        except:
            upcoming_appointments = pd.DataFrame()
    
    if len(upcoming_appointments) > 0:
        with st.expander("📅 Upcoming Appointments (Next 7 Days)", expanded=False):
            for _, appt in upcoming_appointments.iterrows():
                st.write(f"**{appt['Date']}** - {appt.get('Time', '')}: {appt.get('Title', '')} with {appt.get('Attendees', '')}")
    
    # NEW FEATURE: Quick Action Buttons with enhanced styling
    st.subheader("⚡ Quick Actions")
    quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
    
    with quick_col1:
        if st.button("📞 Log Quick Call", use_container_width=True):
            st.session_state.quick_action = "call"
    
    with quick_col2:
        if st.button("💬 Send WhatsApp", use_container_width=True):
            st.session_state.quick_action = "whatsapp"
    
    with quick_col3:
        if st.button("📧 Send Email", use_container_width=True):
            st.session_state.quick_action = "email"
    
    with quick_col4:
        if st.button("✅ Complete Task", use_container_width=True):
            st.session_state.quick_action = "complete_task"
    
    # Handle quick actions
    if hasattr(st.session_state, 'quick_action'):
        handle_quick_action(st.session_state.quick_action, leads_df, activities_df)
    
    # Tabs for different views with icons
    lead_tabs = st.tabs([
        "📊 Dashboard", "👥 All Leads", "➕ Add New Lead", "📋 Lead Timeline", 
        "✅ Tasks", "📅 Appointments", "📈 Analytics", "📝 Templates"
    ])
    
    with lead_tabs[0]:
        show_crm_dashboard(leads_df, activities_df, tasks_df, appointments_df)
    
    with lead_tabs[1]:
        show_all_leads(leads_df, activities_df)
    
    with lead_tabs[2]:
        add_new_lead(leads_df, activities_df)
    
    with lead_tabs[3]:
        show_lead_timeline(leads_df, activities_df)
    
    with lead_tabs[4]:
        manage_tasks(tasks_df)
    
    with lead_tabs[5]:
        manage_appointments(appointments_df)
    
    with lead_tabs[6]:
        show_analytics(leads_df, activities_df)
    
    with lead_tabs[7]:
        show_templates_tab()

def handle_quick_action(action, leads_df, activities_df):
    """Handle quick actions from the dashboard"""
    st.subheader(f"⚡ Quick {action.replace('_', ' ').title()}")
    
    if action == "call":
        with st.form("quick_call_form"):
            col1, col2 = st.columns(2)
            with col1:
                # Safe lead selection
                lead_options = [""]
                if not leads_df.empty and "Name" in leads_df.columns:
                    lead_options.extend([name for name in leads_df["Name"].unique() if pd.notna(name)])
                lead_name = st.selectbox("Select Lead", options=lead_options)
                phone = st.text_input("Phone Number", placeholder="03XXXXXXXXX")
            with col2:
                duration = st.number_input("Duration (minutes)", min_value=1, value=5)
                outcome = st.selectbox("Outcome", ["Positive", "Neutral", "Negative", "Not Responded"])
            
            notes = st.text_area("Call Notes", placeholder="What was discussed?")
            follow_up = st.checkbox("Schedule Follow-up", value=True)
            follow_up_date = st.date_input("Follow-up Date", value=datetime.now().date() + timedelta(days=1))
            
            if st.form_submit_button("📞 Log Call"):
                if lead_name:
                    # Find lead ID safely
                    lead_id = ""
                    if not leads_df.empty and "Name" in leads_df.columns and "ID" in leads_df.columns:
                        matching_leads = leads_df[leads_df["Name"] == lead_name]
                        if not matching_leads.empty:
                            lead_id = matching_leads.iloc[0]["ID"]
                    
                    if log_quick_activity(lead_id, lead_name, "Call", f"Quick call: {notes}", outcome, follow_up_date, activities_df):
                        st.success("Call logged successfully!")
                        # Clear the quick action after handling
                        del st.session_state.quick_action
                        st.rerun()
                else:
                    st.error("Please select a lead")

def log_quick_activity(lead_id, lead_name, activity_type, details, outcome, follow_up_date, activities_df):
    """Log a quick activity"""
    try:
        new_activity = {
            "ID": generate_activity_id(),
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Lead ID": lead_id,
            "Lead Name": lead_name,
            "Lead Phone": "",
            "Activity Type": activity_type,
            "Details": details,
            "Next Steps": "Follow up as needed",
            "Follow-up Date": follow_up_date.strftime("%Y-%m-%d"),
            "Duration": "5",
            "Outcome": outcome
        }
        
        # Safely concatenate dataframes
        if activities_df.empty:
            activities_df = pd.DataFrame([new_activity])
        else:
            activities_df = pd.concat([activities_df, pd.DataFrame([new_activity])], ignore_index=True)
        
        if save_lead_activities(activities_df):
            return True
        return False
    except Exception as e:
        st.error(f"Error logging activity: {str(e)}")
        return False

def show_crm_dashboard(leads_df, activities_df, tasks_df, appointments_df):
    st.subheader("🏠 CRM Dashboard")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Quick stats in card style
        st.markdown("""
        <div class='custom-card'>
            <h4>📊 Quick Stats</h4>
        </div>
        """, unsafe_allow_html=True)
        
        st.write(f"📞 **Total Activities:** {len(activities_df)}")
        
        completed_tasks = 0
        if not tasks_df.empty and "Status" in tasks_df.columns:
            completed_tasks = len(tasks_df[tasks_df["Status"] == "Completed"])
        st.write(f"✅ **Completed Tasks:** {completed_tasks}")
        
        active_tasks = 0
        if not tasks_df.empty and "Status" in tasks_df.columns:
            active_tasks = len(tasks_df[tasks_df["Status"] == "In Progress"])
        st.write(f"🔄 **Active Tasks:** {active_tasks}")
        
        st.write(f"📅 **Total Appointments:** {len(appointments_df)}")
        
        # Today's activities count
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_activities = 0
        if not activities_df.empty and "Timestamp" in activities_df.columns:
            today_activities = len([act for act in activities_df.to_dict('records') 
                                  if str(act.get('Timestamp', '')).startswith(today_str)])
        st.write(f"📊 **Today's Activities:** {today_activities}")
    
    with col2:
        # Recent activities in card style
        st.markdown("""
        <div class='custom-card'>
            <h4>🕒 Recent Activities</h4>
        </div>
        """, unsafe_allow_html=True)
        
        if not activities_df.empty and "Timestamp" in activities_df.columns:
            try:
                # Convert to list of dictionaries for safe handling
                activities_list = activities_df.to_dict('records')
                # Sort by timestamp safely
                activities_list.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)
                
                for activity in activities_list[:5]:
                    timestamp = activity.get('Timestamp', 'Unknown')[:19]  # Truncate if long
                    activity_type = activity.get('Activity Type', 'Activity')
                    lead_name = activity.get('Lead Name', 'Unknown')
                    st.write(f"**{timestamp}:** {activity_type} with {lead_name}")
            except Exception as e:
                st.info("No recent activities or error loading activities.")
        else:
            st.info("No recent activities.")
    
    # Lead status chart - FIXED with error handling
    st.markdown("""
    <div class='custom-card'>
        <h4>📈 Lead Status Overview</h4>
    </div>
    """, unsafe_allow_html=True)
    
    if not leads_df.empty and "Status" in leads_df.columns:
        try:
            status_chart_data = leads_df["Status"].value_counts()
            if not status_chart_data.empty and len(status_chart_data) > 0:
                status_df = pd.DataFrame({
                    'Status': status_chart_data.index,
                    'Count': status_chart_data.values
                })
                # Use bar chart with proper error handling
                fig = px.bar(status_df, x='Status', y='Count', 
                           title="Leads by Status", color='Count',
                           color_continuous_scale='Blues')
                fig.update_layout(
                    xaxis_tickangle=-45,
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No status data available for chart.")
        except Exception as e:
            st.error(f"Error creating status chart: {str(e)}")
            # Fallback: show simple value counts
            if not leads_df.empty and "Status" in leads_df.columns:
                status_counts = leads_df["Status"].value_counts()
                st.write("**Lead Status Counts:**")
                for status, count in status_counts.items():
                    st.write(f"- {status}: {count}")
    else:
        st.info("No status data available.")
    
    # NEW FEATURE: Priority Leads Section
    st.markdown("""
    <div class='custom-card'>
        <h4>🎯 High Priority Leads Needing Attention</h4>
    </div>
    """, unsafe_allow_html=True)
    
    if not leads_df.empty and "Priority" in leads_df.columns and "Status" in leads_df.columns:
        high_priority_leads = leads_df[
            (leads_df["Priority"] == "High") & 
            (~leads_df["Status"].isin(["Deal Closed (Won)", "Not Interested (Lost)"]))
        ]
        
        if not high_priority_leads.empty:
            for _, lead in high_priority_leads.iterrows():
                with st.expander(f"🚨 {lead['Name']} - {lead['Status']}", expanded=False):
                    col1, col2 = st.columns(2)
                    col1.write(f"**Phone:** {lead.get('Phone', 'N/A')}")
                    col1.write(f"**Last Contact:** {lead.get('Last Contact', 'N/A')}")
                    col2.write(f"**Next Action:** {lead.get('Next Action', 'N/A')}")
                    col2.write(f"**Budget:** {lead.get('Budget', 'N/A')}")
                    
                    # Quick action buttons for high priority leads
                    if st.button("📞 Call Now", key=f"call_{lead['ID']}"):
                        phone_num = lead.get("Phone", "")
                        if phone_num:
                            st.markdown(f'<a href="tel:{phone_num}" style="display: inline-block; padding: 0.5rem 1rem; background-color: #25D366; color: white; text-decoration: none; border-radius: 0.5rem; font-weight: 600;">Call {phone_num}</a>', 
                                      unsafe_allow_html=True)
        else:
            st.success("🎉 No high priority leads needing immediate attention!")

def show_all_leads(leads_df, activities_df):
    st.subheader("👥 All Leads")
    
    if leads_df.empty:
        st.info("No leads found. Add your first lead in the 'Add New Lead' tab.")
        return
    
    # Enhanced filters in a card
    st.markdown("""
    <div class='custom-card'>
        <h4>🔍 Filter Leads</h4>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        status_options = ["All"] 
        if "Status" in leads_df.columns:
            status_options.extend([status for status in leads_df["Status"].unique() if pd.notna(status)])
        status_filter = st.selectbox("Filter by Status", options=status_options, key="status_filter")
    with col2:
        priority_options = ["All"]
        if "Priority" in leads_df.columns:
            priority_options.extend([priority for priority in leads_df["Priority"].unique() if pd.notna(priority)])
        priority_filter = st.selectbox("Filter by Priority", options=priority_options, key="priority_filter")
    with col3:
        source_options = ["All"]
        if "Source" in leads_df.columns:
            source_options.extend([source for source in leads_df["Source"].unique() if pd.notna(source)])
        source_filter = st.selectbox("Filter by Source", options=source_options, key="source_filter")
    with col4:
        assigned_options = ["All"]
        if "Assigned To" in leads_df.columns:
            assigned_options.extend([assigned for assigned in leads_df["Assigned To"].unique() if pd.notna(assigned)])
        assigned_filter = st.selectbox("Filter by Assigned To", options=assigned_options, key="assigned_filter")
    
    # NEW: Search by name or phone
    search_term = st.text_input("🔍 Search by Name or Phone", placeholder="Enter name or phone number")
    
    # Apply filters
    filtered_leads = leads_df.copy()
    if status_filter != "All" and "Status" in filtered_leads.columns:
        filtered_leads = filtered_leads[filtered_leads["Status"] == status_filter]
    if priority_filter != "All" and "Priority" in filtered_leads.columns:
        filtered_leads = filtered_leads[filtered_leads["Priority"] == priority_filter]
    if source_filter != "All" and "Source" in filtered_leads.columns:
        filtered_leads = filtered_leads[filtered_leads["Source"] == source_filter]
    if assigned_filter != "All" and "Assigned To" in filtered_leads.columns:
        filtered_leads = filtered_leads[filtered_leads["Assigned To"] == assigned_filter]
    
    # Apply search filter
    if search_term:
        filtered_leads = filtered_leads[
            filtered_leads["Name"].str.contains(search_term, case=False, na=False) |
            filtered_leads["Phone"].str.contains(search_term, case=False, na=False)
        ]
    
    # Display leads count
    st.write(f"**Showing {len(filtered_leads)} of {len(leads_df)} leads**")
    
    # Display leads table with better formatting
    if not filtered_leads.empty:
        # Create a simplified view for better readability
        display_columns = ["Name", "Phone", "Status", "Priority", "Source", "Last Contact", "Next Action"]
        available_columns = [col for col in display_columns if col in filtered_leads.columns]
        
        # Display the dataframe
        st.dataframe(filtered_leads[available_columns], use_container_width=True, height=300)
        
        # Lead update form - FIXED: Only show if leads exist
        if len(filtered_leads) > 0:
            st.subheader("Update Lead")
            lead_options = [f"{row['Name']} ({row['Phone']}) - {row['ID']}" for _, row in filtered_leads.iterrows()]
            selected_lead = st.selectbox("Select Lead to Update", options=lead_options, key="update_lead_select")
            
            if selected_lead:
                update_lead_form(selected_lead, filtered_leads, leads_df, activities_df)
    else:
        st.info("No leads match your filters.")

def update_lead_form(selected_lead, filtered_leads, leads_df, activities_df):
    """Extracted lead update form for better organization"""
    try:
        lead_id = selected_lead.split(" - ")[-1]
        lead_match = filtered_leads[filtered_leads["ID"] == lead_id]
        
        if lead_match.empty:
            st.warning("Selected lead not found. Please select another lead.")
            return
        
        lead_data = lead_match.iloc[0]
        
        with st.form("update_lead_form"):
            col1, col2 = st.columns(2)
            with col1:
                status_options = ["New", "Contacted", "Follow-up", "Meeting Scheduled", 
                                "Negotiation", "Offer Made", "Deal Closed (Won)", "Not Interested (Lost)"]
                current_status = lead_data.get("Status", "New")
                status_index = status_options.index(current_status) if current_status in status_options else 0
                new_status = st.selectbox("Status", options=status_options, index=status_index)
                
                priority_options = ["Low", "Medium", "High"]
                current_priority = lead_data.get("Priority", "Low")
                priority_index = priority_options.index(current_priority) if current_priority in priority_options else 0
                new_priority = st.selectbox("Priority", options=priority_options, index=priority_index)
                
                # Next action date
                next_action_date = datetime.now().date()
                if lead_data.get("Next Action") and pd.notna(lead_data.get("Next Action")):
                    try:
                        next_action_date = datetime.strptime(str(lead_data.get("Next Action")), "%Y-%m-%d").date()
                    except:
                        pass
                new_next_action = st.date_input("Next Action", value=next_action_date)
                
                # Next action type
                action_type_options = ["Call", "Email", "Meeting", "Site Visit", "Follow-up"]
                current_action_type = lead_data.get("Next Action Type", "Call")
                action_type_index = action_type_options.index(current_action_type) if current_action_type in action_type_options else 0
                new_next_action_type = st.selectbox("Next Action Type", options=action_type_options, index=action_type_index)
            
            with col2:
                # Last contact date
                last_contact_date = datetime.now().date()
                if lead_data.get("Last Contact") and pd.notna(lead_data.get("Last Contact")):
                    try:
                        last_contact_date = datetime.strptime(str(lead_data.get("Last Contact", "")), "%Y-%m-%d").date()
                    except:
                        pass
                new_last_contact = st.date_input("Last Contact", value=last_contact_date)
                
                # Budget
                current_budget = lead_data.get("Budget", 0)
                if isinstance(current_budget, str) and current_budget.isdigit():
                    current_budget = int(current_budget)
                elif not isinstance(current_budget, (int, float)):
                    current_budget = 0
                new_budget = st.number_input("Budget (₹)", value=current_budget)
                
                new_location = st.text_input("Location Preference", value=lead_data.get("Location Preference", ""))
                new_notes = st.text_area("Notes", value=lead_data.get("Notes", ""))
            
            # NEW: Quick action buttons in the form
            col1, col2, col3 = st.columns(3)
            with col1:
                update_btn = st.form_submit_button("💾 Update Lead")
            with col2:
                log_call_btn = st.form_submit_button("📞 Log Call")
            with col3:
                log_whatsapp_btn = st.form_submit_button("💬 Log WhatsApp")
            
            if update_btn:
                update_lead_data(lead_id, leads_df, activities_df, new_status, new_priority, new_next_action,
                               new_next_action_type, new_last_contact, new_budget, new_location, new_notes)
            
            if log_call_btn:
                log_quick_call(lead_id, lead_data, activities_df)
            
            if log_whatsapp_btn:
                log_quick_whatsapp(lead_id, lead_data, activities_df)
    except Exception as e:
        st.error(f"Error in update form: {str(e)}")

def update_lead_data(lead_id, leads_df, activities_df, new_status, new_priority, new_next_action,
                   new_next_action_type, new_last_contact, new_budget, new_location, new_notes):
    """Update lead data in the system"""
    idx = leads_df[leads_df["ID"] == lead_id].index
    if len(idx) > 0:
        idx = idx[0]
        leads_df.at[idx, "Status"] = new_status
        leads_df.at[idx, "Priority"] = new_priority
        leads_df.at[idx, "Next Action"] = new_next_action.strftime("%Y-%m-%d")
        leads_df.at[idx, "Next Action Type"] = new_next_action_type
        leads_df.at[idx, "Last Contact"] = new_last_contact.strftime("%Y-%m-%d")
        leads_df.at[idx, "Budget"] = new_budget
        leads_df.at[idx, "Location Preference"] = new_location
        leads_df.at[idx, "Notes"] = new_notes
        
        # Recalculate lead score
        leads_df.at[idx, "Lead Score"] = calculate_lead_score(leads_df.iloc[idx], activities_df)
        
        # Save to Google Sheets
        if save_leads(leads_df):
            st.success("Lead updated successfully!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("Failed to update lead. Please try again.")
    else:
        st.error("Lead not found in database. Please try again.")

def log_quick_call(lead_id, lead_data, activities_df):
    """Log a quick call activity"""
    new_activity = {
        "ID": generate_activity_id(),
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Lead ID": lead_id,
        "Lead Name": lead_data["Name"],
        "Lead Phone": lead_data.get("Phone", ""),
        "Activity Type": "Call",
        "Details": "Quick call logged from lead update form",
        "Next Steps": "Follow up as discussed",
        "Follow-up Date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "Duration": "5",
        "Outcome": "Positive"
    }
    
    activities_df = pd.concat([activities_df, pd.DataFrame([new_activity])], ignore_index=True)
    if save_lead_activities(activities_df):
        st.success("Call logged successfully!")
        st.cache_data.clear()
        st.rerun()

def log_quick_whatsapp(lead_id, lead_data, activities_df):
    """Log a quick WhatsApp activity"""
    new_activity = {
        "ID": generate_activity_id(),
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Lead ID": lead_id,
        "Lead Name": lead_data["Name"],
        "Lead Phone": lead_data.get("Phone", ""),
        "Activity Type": "WhatsApp",
        "Details": "WhatsApp message sent from lead update form",
        "Next Steps": "Wait for response",
        "Follow-up Date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
        "Duration": "2",
        "Outcome": "Pending"
    }
    
    activities_df = pd.concat([activities_df, pd.DataFrame([new_activity])], ignore_index=True)
    if save_lead_activities(activities_df):
        st.success("WhatsApp activity logged successfully!")
        st.cache_data.clear()
        st.rerun()

def add_new_lead(leads_df, activities_df):
    """Add a new lead to the system"""
    st.subheader("Add New Lead")
    
    with st.form("add_lead_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name*", placeholder="Client Name")
            phone = st.text_input("Phone*", placeholder="03XXXXXXXXX")
            email = st.text_input("Email", placeholder="client@example.com")
            source = st.selectbox("Source", 
                                options=["Website", "WhatsApp", "Referral", "Walk-in", "Social Media", "Existing Client", "Other"])
            lead_type = st.selectbox("Lead Type", 
                                   options=["Buyer", "Seller", "Investor", "Renter"])
        with col2:
            status = st.selectbox("Status", 
                                options=["New", "Contacted", "Follow-up", "Meeting Scheduled", 
                                        "Negotiation", "Offer Made", "Deal Closed (Won)", "Not Interested (Lost)"])
            priority = st.selectbox("Priority", 
                                  options=["Low", "Medium", "High"])
            property_interest = st.text_input("Property Interest", placeholder="e.g., I-10/4, 125 sq yd")
            budget = st.number_input("Budget (₹)", value=0)
            location_preference = st.text_input("Location Preference", placeholder="Preferred sectors/areas")
        
        notes = st.text_area("Notes", placeholder="Any additional information about the lead")
        assigned_to = st.text_input("Assigned To", value="Current User", placeholder="Agent name")
        
        submit_button = st.form_submit_button("Add Lead")
        if submit_button:
            if not name or not phone:
                st.error("Name and Phone are required fields!")
            else:
                # Create new lead entry
                lead_id = generate_lead_id()
                new_lead = {
                    "ID": lead_id,
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Name": name,
                    "Phone": phone,
                    "Email": email,
                    "Source": source,
                    "Status": status,
                    "Priority": priority,
                    "Property Interest": property_interest,
                    "Budget": budget,
                    "Location Preference": location_preference,
                    "Last Contact": datetime.now().strftime("%Y-%m-%d"),
                    "Next Action": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                    "Next Action Type": "Call",
                    "Notes": notes,
                    "Assigned To": assigned_to,
                    "Lead Score": 10,  # Initial score
                    "Type": lead_type,
                    "Timeline": ""
                }
                
                # Add to dataframe
                leads_df = pd.concat([leads_df, pd.DataFrame([new_lead])], ignore_index=True)
                
                # Save to Google Sheets
                if save_leads(leads_df):
                    # Create initial activity
                    new_activity = {
                        "ID": generate_activity_id(),
                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Lead ID": lead_id,
                        "Lead Name": name,
                        "Lead Phone": phone,
                        "Activity Type": "Status Update",
                        "Details": f"New lead created. Status: {status}, Priority: {priority}",
                        "Next Steps": "Initial contact",
                        "Follow-up Date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                        "Duration": "5",
                        "Outcome": "Lead created"
                    }
                    
                    activities_df = pd.concat([activities_df, pd.DataFrame([new_activity])], ignore_index=True)
                    if save_lead_activities(activities_df):
                        st.success("Lead added successfully!")
                        # Clear cache to refresh data
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Lead added but failed to create activity. Please check activities sheet.")
                else:
                    st.error("Failed to add lead. Please try again.")

def show_lead_timeline(leads_df, activities_df):
    st.subheader("Lead Timeline")
    
    if leads_df.empty:
        st.info("No leads found. Add your first lead in the 'Add New Lead' tab.")
        return
    
    # Select lead to view timeline
    lead_options = [f"{row['Name']} ({row['Phone']}) - {row['ID']}" for _, row in leads_df.iterrows()]
    selected_lead = st.selectbox("Select Lead", options=lead_options, key="timeline_lead_select")
    
    if selected_lead:
        # Extract the ID from the selected option
        lead_id = selected_lead.split(" - ")[-1]
        
        # Find the lead by ID
        lead_match = leads_df[leads_df["ID"] == lead_id]
        if lead_match.empty:
            st.warning("Selected lead not found. Please select another lead.")
        else:
            lead_data = lead_match.iloc[0]
            lead_name = lead_data["Name"]
            lead_phone = lead_data["Phone"]
            
            # Display timeline with proper error handling
            display_lead_timeline(lead_id, lead_name, lead_phone, activities_df)
            
            # Add new activity
            st.subheader("Add New Activity")
            
            with st.form("add_activity_form"):
                col1, col2 = st.columns(2)
                with col1:
                    activity_type = st.selectbox("Activity Type", 
                                               options=["Call", "Meeting", "Email", "WhatsApp", "Site Visit", "Status Update", "Note"])
                    follow_up_date = st.date_input("Follow-up Date", value=datetime.now().date() + timedelta(days=7))
                    duration = st.number_input("Duration (minutes)", min_value=0, value=15)
                with col2:
                    next_steps = st.text_input("Next Steps", placeholder="What needs to happen next?")
                    outcome = st.selectbox("Outcome", 
                                         options=["Positive", "Neutral", "Negative", "Not Responded", "Scheduled", "Completed"])
                
                details = st.text_area("Details*", placeholder="What was discussed?")
                
                submit_button = st.form_submit_button("Add Activity")
                if submit_button:
                    if not details:
                        st.error("Details are required!")
                    else:
                        # Create new activity
                        new_activity = {
                            "ID": generate_activity_id(),
                            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Lead ID": lead_id,
                            "Lead Name": lead_name,
                            "Lead Phone": lead_phone,
                            "Activity Type": activity_type,
                            "Details": details,
                            "Next Steps": next_steps,
                            "Follow-up Date": follow_up_date.strftime("%Y-%m-%d"),
                            "Duration": str(duration),
                            "Outcome": outcome
                        }
                        
                        # Add to dataframe
                        activities_df = pd.concat([activities_df, pd.DataFrame([new_activity])], ignore_index=True)
                        
                        # Save to Google Sheets
                        if save_lead_activities(activities_df):
                            # Update last contact date in leads sheet
                            idx = leads_df[leads_df["ID"] == lead_id].index
                            if len(idx) > 0:
                                idx = idx[0]
                                leads_df.at[idx, "Last Contact"] = datetime.now().strftime("%Y-%m-%d")
                                
                                # Update lead score
                                leads_df.at[idx, "Lead Score"] = calculate_lead_score(leads_df.iloc[idx], activities_df)
                                
                                if save_leads(leads_df):
                                    st.success("Activity added successfully!")
                                    # Clear cache to refresh data
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("Activity added but failed to update lead. Please check leads sheet.")
                            else:
                                st.error("Lead not found in database. Please try again.")
                        else:
                            st.error("Failed to add activity. Please try again.")

def manage_tasks(tasks_df):
    st.subheader("Tasks")
    
    # Create new task
    with st.form("add_task_form"):
        col1, col2 = st.columns(2)
        with col1:
            task_title = st.text_input("Task Title*")
            due_date = st.date_input("Due Date*", value=datetime.now().date() + timedelta(days=1))
            priority = st.selectbox("Priority", options=["Low", "Medium", "High"])
        with col2:
            related_to = st.selectbox("Related To", options=["Lead", "Appointment", "Other"])
            related_id = st.text_input("Related ID", placeholder="ID or reference")
            status = st.selectbox("Status", options=["Not Started", "In Progress", "Completed"])
        
        description = st.text_area("Description")
        assigned_to = st.text_input("Assigned To", value="Current User")
        
        submit_button = st.form_submit_button("Add Task")
        if submit_button:
            if not task_title:
                st.error("Task title is required!")
            else:
                # Create new task
                new_task = {
                    "ID": generate_task_id(),
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Title": task_title,
                    "Description": description,
                    "Due Date": due_date.strftime("%Y-%m-%d"),
                    "Priority": priority,
                    "Status": status,
                    "Assigned To": assigned_to,
                    "Related To": related_to,
                    "Related ID": related_id,
                    "Completed Date": datetime.now().strftime("%Y-%m-%d") if status == "Completed" else ""
                }
                
                # Add to dataframe
                tasks_df = pd.concat([tasks_df, pd.DataFrame([new_task])], ignore_index=True)
                
                # Save to Google Sheets
                if save_tasks(tasks_df):
                    st.success("Task added successfully!")
                    # Clear cache to refresh data
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Failed to add task. Please try again.")
    
    # Display tasks
    st.subheader("All Tasks")
    
    # Filter tasks
    task_status_filter = st.selectbox("Filter by Status", 
                                    options=["All", "Not Started", "In Progress", "Completed"],
                                    key="task_status_filter")
    
    filtered_tasks = tasks_df.copy()
    if task_status_filter != "All" and "Status" in filtered_tasks.columns:
        filtered_tasks = filtered_tasks[filtered_tasks["Status"] == task_status_filter]
    
    if filtered_tasks.empty:
        st.info("No tasks found.")
    else:
        for _, task in filtered_tasks.iterrows():
            with st.expander(f"{task['Title']} - {task['Status']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Due Date:** {task.get('Due Date', 'N/A')}")
                    st.write(f"**Priority:** {task.get('Priority', 'N/A')}")
                    st.write(f"**Assigned To:** {task.get('Assigned To', 'N/A')}")
                with col2:
                    st.write(f"**Related To:** {task.get('Related To', 'N/A')}")
                    st.write(f"**Status:** {task.get('Status', 'N/A')}")
                    if task.get('Status') == "Completed" and task.get('Completed Date'):
                        st.write(f"**Completed On:** {task['Completed Date']}")
                
                st.write(f"**Description:** {task.get('Description', 'No description')}")
                
                # Update task status
                current_status = task.get('Status', 'Not Started')
                new_status = st.selectbox("Update Status", 
                                        options=["Not Started", "In Progress", "Completed"],
                                        index=["Not Started", "In Progress", "Completed"].index(current_status) if current_status in ["Not Started", "In Progress", "Completed"] else 0,
                                        key=f"status_{task['ID']}")
                
                if st.button("Update", key=f"update_{task['ID']}"):
                    idx = tasks_df[tasks_df["ID"] == task['ID']].index
                    if len(idx) > 0:
                        idx = idx[0]
                        tasks_df.at[idx, "Status"] = new_status
                        if new_status == "Completed":
                            tasks_df.at[idx, "Completed Date"] = datetime.now().strftime("%Y-%m-%d")
                        if save_tasks(tasks_df):
                            st.success("Task updated successfully!")
                            # Clear cache to refresh data
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Failed to update task. Please try again.")
                    else:
                        st.error("Task not found in database. Please try again.")

def manage_appointments(appointments_df):
    st.subheader("Appointments")
    
    # Create new appointment
    with st.form("add_appointment_form"):
        col1, col2 = st.columns(2)
        with col1:
            appointment_title = st.text_input("Appointment Title*")
            appointment_date = st.date_input("Date*", value=datetime.now().date() + timedelta(days=1))
            appointment_time = st.time_input("Time*", value=datetime.now().time())
            duration = st.number_input("Duration (minutes)*", min_value=15, value=30)
        with col2:
            related_to = st.selectbox("Related To", options=["Lead", "Other"])
            related_id = st.text_input("Related ID", placeholder="ID or reference")
            status_options = ["Scheduled", "Confirmed", "Completed", "Cancelled"]
            status = st.selectbox("Status", options=status_options)
            location = st.text_input("Location", placeholder="Meeting location")
        
        description = st.text_area("Description")
        attendees = st.text_input("Attendees", placeholder="Names of attendees")
        
        submit_button = st.form_submit_button("Add Appointment")
        if submit_button:
            if not appointment_title:
                st.error("Appointment title is required!")
            else:
                # Create new appointment
                new_appointment = {
                    "ID": generate_appointment_id(),
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Title": appointment_title,
                    "Description": description,
                    "Date": appointment_date.strftime("%Y-%m-%d"),
                    "Time": appointment_time.strftime("%H:%M"),
                    "Duration": str(duration),
                    "Attendees": attendees,
                    "Location": location,
                    "Status": status,
                    "Related To": related_to,
                    "Related ID": related_id,
                    "Outcome": ""
                }
                
                # Add to dataframe
                appointments_df = pd.concat([appointments_df, pd.DataFrame([new_appointment])], ignore_index=True)
                
                # Save to Google Sheets
                if save_appointments(appointments_df):
                    st.success("Appointment added successfully!")
                    # Clear cache to refresh data
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Failed to add appointment. Please try again.")
    
    # Display appointments
    st.subheader("All Appointments")
    
    # Filter appointments
    appointment_status_filter = st.selectbox("Filter by Status", 
                                           options=["All", "Scheduled", "Confirmed", "Completed", "Cancelled"],
                                           key="appointment_status_filter")
    
    filtered_appointments = appointments_df.copy()
    if appointment_status_filter != "All" and "Status" in filtered_appointments.columns:
        filtered_appointments = filtered_appointments[filtered_appointments["Status"] == appointment_status_filter]
    
    if filtered_appointments.empty:
        st.info("No appointments found.")
    else:
        for _, appointment in filtered_appointments.iterrows():
            with st.expander(f"{appointment['Title']} - {appointment['Status']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Date:** {appointment.get('Date', 'N/A')}")
                    st.write(f"**Time:** {appointment.get('Time', 'N/A')}")
                    st.write(f"**Duration:** {appointment.get('Duration', 'N/A')} minutes")
                    st.write(f"**Location:** {appointment.get('Location', 'N/A')}")
                with col2:
                    st.write(f"**Related To:** {appointment.get('Related To', 'N/A')}")
                    st.write(f"**Status:** {appointment.get('Status', 'N/A')}")
                    st.write(f"**Attendees:** {appointment.get('Attendees', 'N/A')}")
                
                st.write(f"**Description:** {appointment.get('Description', 'No description')}")
                
                # Update appointment status
                current_status = appointment.get('Status', 'Scheduled')
                new_status = st.selectbox("Update Status", 
                                        options=["Scheduled", "Confirmed", "Completed", "Cancelled"],
                                        index=["Scheduled", "Confirmed", "Completed", "Cancelled"].index(current_status) if current_status in ["Scheduled", "Confirmed", "Completed", "Cancelled"] else 0,
                                        key=f"status_{appointment['ID']}")
                
                if st.button("Update", key=f"update_{appointment['ID']}"):
                    idx = appointments_df[appointments_df["ID"] == appointment['ID']].index
                    if len(idx) > 0:
                        idx = idx[0]
                        appointments_df.at[idx, "Status"] = new_status
                        if save_appointments(appointments_df):
                            st.success("Appointment updated successfully!")
                            # Clear cache to refresh data
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Failed to update appointment. Please try again.")
                    else:
                        st.error("Appointment not found in database. Please try again.")

def show_analytics(leads_df, activities_df):
    display_lead_analytics(leads_df, activities_df)

def show_templates_tab():
    """NEW FEATURE: Email and message templates"""
    st.subheader("📝 Communication Templates")
    
    template_type = st.selectbox("Select Template Type", 
                               ["Welcome Email", "Follow-up", "Meeting Confirmation", 
                                "Property Details", "Thank You", "Custom"])
    
    # Template examples
    templates = {
        "Welcome Email": """
        Subject: Welcome to Al-Jazeera Real Estate!
        
        Dear {name},
        
        Thank you for your interest in Al-Jazeera Real Estate. We're excited to help you find your perfect property!
        
        Based on your preferences for {preference}, we have several options that might interest you.
        
        Best regards,
        Al-Jazeera Team
        {phone}
        """,
        
        "Follow-up": """
        Hi {name},
        
        Just following up on our conversation about properties in {sector}. 
        I have some new listings that match your criteria perfectly!
        
        Would you be available for a quick call this week?
        
        Best,
        {agent_name}
        """,
        
        "Property Details": """
        Property Details for {sector}:
        
        * Plot No: {plot_no}
        * Size: {size}
        * Price: {price}
        * Features: {features}
        
        Let me know if you'd like to schedule a site visit!
        """
    }
    
    if template_type in templates:
        template_content = st.text_area("Template Content", value=templates[template_type], height=200)
    else:
        template_content = st.text_area("Create Custom Template", height=200, 
                                      placeholder="Enter your custom template here...")
    
    # Template variables
    st.subheader("Template Variables")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Contact Variables:**")
        st.write("- {name} - Client name")
        st.write("- {phone} - Client phone")
        st.write("- {email} - Client email")
    with col2:
        st.write("**Property Variables:**")
        st.write("- {sector} - Property sector")
        st.write("- {plot_no} - Plot number")
        st.write("- {size} - Plot size")
        st.write("- {price} - Property price")
    
    # Copy to clipboard functionality
    if st.button("📋 Copy Template to Clipboard"):
        st.code(template_content, language="text")
        st.success("Template copied! You can now paste it into your email or messaging app.")
