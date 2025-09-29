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
                    lead_options.extend(list(leads_df["Name"].unique()))
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
                    
                    log_quick_activity(lead_id, lead_name, "Call", f"Quick call: {notes}", outcome, follow_up_date, activities_df)
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

# ... (rest of the existing crm_manager.py functions remain the same with updated styling)
# The remaining functions (show_all_leads, update_lead_form, etc.) would follow the same pattern
# with the enhanced styling applied throughout

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
            status_options.extend(list(leads_df["Status"].unique()))
        status_filter = st.selectbox("Filter by Status", options=status_options, key="status_filter")
    with col2:
        priority_options = ["All"]
        if "Priority" in leads_df.columns:
            priority_options.extend(list(leads_df["Priority"].unique()))
        priority_filter = st.selectbox("Filter by Priority", options=priority_options, key="priority_filter")
    with col3:
        source_options = ["All"]
        if "Source" in leads_df.columns:
            source_options.extend(list(leads_df["Source"].unique()))
        source_filter = st.selectbox("Filter by Source", options=source_options, key="source_filter")
    with col4:
        assigned_options = ["All"]
        if "Assigned To" in leads_df.columns:
            assigned_options.extend(list(leads_df["Assigned To"].unique()))
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
        
        # Lead update form
        st.subheader("Update Lead")
        lead_options = [f"{row['Name']} ({row['Phone']}) - {row['ID']}" for _, row in filtered_leads.iterrows()]
        selected_lead = st.selectbox("Select Lead to Update", options=lead_options, key="update_lead_select")
        
        if selected_lead:
            update_lead_form(selected_lead, filtered_leads, leads_df, activities_df)
    else:
        st.info("No leads match your filters.")

# ... Continue with the rest of the existing functions with similar styling enhancements
