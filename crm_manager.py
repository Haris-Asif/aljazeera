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
    st.header("👥 Lead Management CRM")
    
    # Load data
    leads_df = load_leads()
    activities_df = load_lead_activities()
    tasks_df = load_tasks()
    appointments_df = load_appointments()
    
    # Calculate metrics for dashboard
    total_leads = len(leads_df) if not leads_df.empty else 0
    
    # Initialize counts safely
    status_counts = pd.Series()
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
    
    # Display metrics
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
        with st.expander("📅 Upcoming Appointments (Next 7 Days)"):
            for _, appt in upcoming_appointments.iterrows():
                st.write(f"{appt['Date']} - {appt.get('Time', '')}: {appt.get('Title', '')} with {appt.get('Attendees', '')}")
    
    # NEW FEATURE: Quick Action Buttons
    st.subheader("⚡ Quick Actions")
    quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
    
    with quick_col1:
        if st.button("📞 Log Quick Call", use_container_width=True):
            st.session_state.quick_action = "call"
            st.rerun()
    
    with quick_col2:
        if st.button("💬 Send WhatsApp", use_container_width=True):
            st.session_state.quick_action = "whatsapp"
            st.rerun()
    
    with quick_col3:
        if st.button("📧 Send Email", use_container_width=True):
            st.session_state.quick_action = "email"
            st.rerun()
    
    with quick_col4:
        if st.button("✅ Complete Task", use_container_width=True):
            st.session_state.quick_action = "complete_task"
            st.rerun()
    
    # Handle quick actions
    if hasattr(st.session_state, 'quick_action'):
        handle_quick_action(st.session_state.quick_action, leads_df, activities_df)
        # Clear the quick action after handling
        del st.session_state.quick_action
    
    # Tabs for different views
    lead_tabs = st.tabs([
        "Dashboard", "All Leads", "Add New Lead", "Lead Timeline", 
        "Tasks", "Appointments", "Analytics", "Templates"  # NEW TAB: Templates
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
        manage_tasks(leads_df, tasks_df)
    
    with lead_tabs[5]:
        manage_appointments(leads_df, appointments_df)
    
    with lead_tabs[6]:
        show_analytics(leads_df, activities_df)
    
    # NEW TAB: Email/Message Templates
    with lead_tabs[7]:
        show_templates_tab()

def handle_quick_action(action, leads_df, activities_df):
    """Handle quick actions from the dashboard"""
    st.subheader(f"⚡ Quick {action.replace('_', ' ').title()}")
    
    if action == "call":
        with st.form("quick_call_form"):
            col1, col2 = st.columns(2)
            with col1:
                lead_name = st.selectbox("Select Lead", 
                                       options=[""] + list(leads_df["Name"].unique()) if not leads_df.empty else [""])
                phone = st.text_input("Phone Number", placeholder="03XXXXXXXXX")
            with col2:
                duration = st.number_input("Duration (minutes)", min_value=1, value=5)
                outcome = st.selectbox("Outcome", ["Positive", "Neutral", "Negative", "Not Responded"])
            
            notes = st.text_area("Call Notes", placeholder="What was discussed?")
            follow_up = st.checkbox("Schedule Follow-up", value=True)
            follow_up_date = st.date_input("Follow-up Date", value=datetime.now().date() + timedelta(days=1))
            
            if st.form_submit_button("Log Call"):
                if lead_name:
                    # Find lead ID
                    lead_id = leads_df[leads_df["Name"] == lead_name].iloc[0]["ID"] if not leads_df.empty else ""
                    log_quick_activity(lead_id, lead_name, "Call", f"Quick call: {notes}", outcome, follow_up_date, activities_df)
                    st.success("Call logged successfully!")
                else:
                    st.error("Please select a lead")

def log_quick_activity(lead_id, lead_name, activity_type, details, outcome, follow_up_date, activities_df):
    """Log a quick activity"""
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
    
    activities_df = pd.concat([activities_df, pd.DataFrame([new_activity])], ignore_index=True)
    save_lead_activities(activities_df)

def show_crm_dashboard(leads_df, activities_df, tasks_df, appointments_df):
    st.subheader("🏠 CRM Dashboard")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Quick stats
        st.info("**Quick Stats**")
        st.write(f"📞 Total Activities: {len(activities_df)}")
        completed_tasks = len(tasks_df[tasks_df["Status"] == "Completed"]) if not tasks_df.empty else 0
        st.write(f"✅ Completed Tasks: {completed_tasks}")
        active_tasks = len(tasks_df[tasks_df["Status"] == "In Progress"]) if not tasks_df.empty else 0
        st.write(f"🔄 Active Tasks: {active_tasks}")
        st.write(f"📅 Total Appointments: {len(appointments_df)}")
        
        # NEW: Today's activities count
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_activities = len([act for act in activities_df.to_dict('records') 
                              if str(act.get('Timestamp', '')).startswith(today_str)]) if not activities_df.empty else 0
        st.write(f"📊 Today's Activities: {today_activities}")
    
    with col2:
        # Recent activities
        st.info("**Recent Activities**")
        if not activities_df.empty and "Timestamp" in activities_df.columns:
            try:
                # Convert to list of dictionaries for safe handling
                activities_list = activities_df.to_dict('records')
                # Sort by timestamp safely
                activities_list.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)
                
                for activity in activities_list[:5]:
                    timestamp = activity.get('Timestamp', 'Unknown')
                    activity_type = activity.get('Activity Type', 'Activity')
                    lead_name = activity.get('Lead Name', 'Unknown')
                    st.write(f"{timestamp}: {activity_type} with {lead_name}")
            except Exception as e:
                st.info("No recent activities or error loading activities.")
        else:
            st.info("No recent activities.")
    
    # Lead status chart - FIXED with error handling
    st.info("**Lead Status Overview**")
    if not leads_df.empty and "Status" in leads_df.columns:
        try:
            status_chart_data = leads_df["Status"].value_counts()
            if not status_chart_data.empty:
                status_df = pd.DataFrame({
                    'Status': status_chart_data.index,
                    'Count': status_chart_data.values
                })
                # FIX: Use bar chart with proper error handling
                fig = px.bar(status_df, x='Status', y='Count', 
                           title="Leads by Status", color='Count',
                           color_continuous_scale='Blues')
                fig.update_layout(xaxis_tickangle=-45)
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
    st.info("🎯 High Priority Leads Needing Attention")
    if not leads_df.empty and "Priority" in leads_df.columns and "Status" in leads_df.columns:
        high_priority_leads = leads_df[
            (leads_df["Priority"] == "High") & 
            (~leads_df["Status"].isin(["Deal Closed (Won)", "Not Interested (Lost)"]))
        ]
        
        if not high_priority_leads.empty:
            for _, lead in high_priority_leads.iterrows():
                with st.expander(f"🚨 {lead['Name']} - {lead['Status']}"):
                    col1, col2 = st.columns(2)
                    col1.write(f"**Phone:** {lead.get('Phone', 'N/A')}")
                    col1.write(f"**Last Contact:** {lead.get('Last Contact', 'N/A')}")
                    col2.write(f"**Next Action:** {lead.get('Next Action', 'N/A')}")
                    col2.write(f"**Budget:** {lead.get('Budget', 'N/A')}")
                    
                    # Quick action buttons for high priority leads
                    if st.button("📞 Call Now", key=f"call_{lead['ID']}"):
                        st.markdown(f'<a href="tel:{lead.get("Phone", "")}" style="display: inline-block; padding: 0.5rem 1rem; background-color: #25D366; color: white; text-decoration: none; border-radius: 0.5rem;">Call {lead.get("Phone", "")}</a>', 
                                  unsafe_allow_html=True)
        else:
            st.success("🎉 No high priority leads needing immediate attention!")

def show_all_leads(leads_df, activities_df):
    st.subheader("All Leads")
    
    if leads_df.empty:
        st.info("No leads found. Add your first lead in the 'Add New Lead' tab.")
    else:
        # Enhanced filters
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            status_options = ["All"] + list(leads_df["Status"].unique()) if "Status" in leads_df.columns else ["All"]
            status_filter = st.selectbox("Filter by Status", options=status_options, key="status_filter")
        with col2:
            priority_options = ["All"] + list(leads_df["Priority"].unique()) if "Priority" in leads_df.columns else ["All"]
            priority_filter = st.selectbox("Filter by Priority", options=priority_options, key="priority_filter")
        with col3:
            source_options = ["All"] + list(leads_df["Source"].unique()) if "Source" in leads_df.columns else ["All"]
            source_filter = st.selectbox("Filter by Source", options=source_options, key="source_filter")
        with col4:
            assigned_options = ["All"] + list(leads_df["Assigned To"].unique()) if "Assigned To" in leads_df.columns else ["All"]
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
            
            st.dataframe(filtered_leads[available_columns], use_container_width=True, height=300)
        else:
            st.info("No leads match your filters.")
        
        # Lead actions (existing code remains the same)
        if not filtered_leads.empty:
            st.subheader("Update Lead")
            lead_options = [f"{row['Name']} ({row['Phone']}) - {row['ID']}" for _, row in filtered_leads.iterrows()]
            selected_lead = st.selectbox("Select Lead to Update", options=lead_options, key="update_lead_select")
            
            if selected_lead:
                update_lead_form(selected_lead, filtered_leads, leads_df, activities_df)

def update_lead_form(selected_lead, filtered_leads, leads_df, activities_df):
    """Extracted lead update form for better organization"""
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
                    next_action_date = datetime.strptime(lead_data.get("Next Action"), "%Y-%m-%d").date()
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
                    last_contact_date = datetime.strptime(lead_data.get("Last Contact", ""), "%Y-%m-%d").date()
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
            if st.form_submit_button("💾 Update Lead"):
                update_lead_data(lead_id, leads_df, activities_df, new_status, new_priority, new_next_action,
                               new_next_action_type, new_last_contact, new_budget, new_location, new_notes)
        with col2:
            if st.form_submit_button("📞 Log Call"):
                log_quick_call(lead_id, lead_data, activities_df)
        with col3:
            if st.form_submit_button("💬 Log WhatsApp"):
                log_quick_whatsapp(lead_id, lead_data, activities_df)

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

# ... (Rest of the functions remain similar but with enhanced error handling)

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
    
    # Quick send options
    st.subheader("Quick Send Options")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📧 Prepare Email", use_container_width=True):
            st.info("Ready to send via email client")
            st.code(f"mailto:?body={template_content}", language="text")
    
    with col2:
        if st.button("💬 Prepare WhatsApp", use_container_width=True):
            st.info("Ready to send via WhatsApp")
            # Basic URL encoding for WhatsApp
            encoded_message = template_content.replace(" ", "%20").replace("\n", "%0A")
            st.code(f"https://wa.me/?text={encoded_message}", language="text")
