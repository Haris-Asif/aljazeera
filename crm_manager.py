import streamlit as st
import pandas as pd
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
    
    # Tabs for different views
    lead_tabs = st.tabs([
        "Dashboard", "All Leads", "Add New Lead", "Lead Timeline", 
        "Tasks", "Appointments", "Analytics"
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
    
    with col2:
        # Recent activities
        st.info("**Recent Activities**")
        if not activities_df.empty and "Timestamp" in activities_df.columns:
            try:
                recent_activities = activities_df.sort_values("Timestamp", ascending=False).head(5)
                for _, activity in recent_activities.iterrows():
                    st.write(f"{activity['Timestamp']}: {activity.get('Activity Type', '')} with {activity.get('Lead Name', '')}")
            except:
                st.info("No recent activities.")
        else:
            st.info("No recent activities.")
    
    # Lead status chart
    st.info("**Lead Status Overview**")
    if not leads_df.empty and "Status" in leads_df.columns:
        status_chart_data = leads_df["Status"].value_counts()
        if not status_chart_data.empty:
            status_df = pd.DataFrame({
                'Status': status_chart_data.index,
                'Count': status_chart_data.values
            })
            fig = px.bar(status_df, x='Status', y='Count', title="Leads by Status")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No status data available.")
    else:
        st.info("No status data available.")

def show_all_leads(leads_df, activities_df):
    st.subheader("All Leads")
    
    if leads_df.empty:
        st.info("No leads found. Add your first lead in the 'Add New Lead' tab.")
    else:
        # Filters
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
        
        # Display leads table
        st.dataframe(filtered_leads, use_container_width=True)
        
        # Lead actions
        if not filtered_leads.empty:
            st.subheader("Update Lead")
            lead_options = [f"{row['Name']} ({row['Phone']}) - {row['ID']}" for _, row in filtered_leads.iterrows()]
            selected_lead = st.selectbox("Select Lead to Update", options=lead_options, key="update_lead_select")
            
            if selected_lead:
                # Extract the ID from the selected option
                lead_id = selected_lead.split(" - ")[-1]
                
                # Find the lead by ID
                lead_match = filtered_leads[filtered_leads["ID"] == lead_id]
                if lead_match.empty:
                    st.warning("Selected lead not found. Please select another lead.")
                else:
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
                        
                        submit_button = st.form_submit_button("Update Lead")
                        if submit_button:
                            # Update the lead in the dataframe
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
                                    # Clear cache to refresh data
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("Failed to update lead. Please try again.")
                            else:
                                st.error("Lead not found in database. Please try again.")

def add_new_lead(leads_df, activities_df):
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
    else:
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

def manage_tasks(leads_df, tasks_df):
    st.subheader("Tasks")
    
    if leads_df.empty:
        st.info("No leads found. Add your first lead to create tasks.")
    else:
        # Create new task
        with st.form("add_task_form"):
            col1, col2 = st.columns(2)
            with col1:
                task_title = st.text_input("Task Title*")
                due_date = st.date_input("Due Date*", value=datetime.now().date() + timedelta(days=1))
                priority = st.selectbox("Priority", options=["Low", "Medium", "High"])
            with col2:
                related_to = st.selectbox("Related To", options=["Lead", "Appointment", "Other"])
                if related_to == "Lead":
                    lead_options = [f"{row['Name']} ({row['Phone']}) - {row['ID']}" for _, row in leads_df.iterrows()]
                    related_id = st.selectbox("Select Lead", options=lead_options)
                else:
                    related_id = st.text_input("Related ID")
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

def manage_appointments(leads_df, appointments_df):
    st.subheader("Appointments")
    
    if leads_df.empty:
        st.info("No leads found. Add your first lead to create appointments.")
    else:
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
                if related_to == "Lead":
                    lead_options = [f"{row['Name']} ({row['Phone']}) - {row['ID']}" for _, row in leads_df.iterrows()]
                    related_id = st.selectbox("Select Lead", options=lead_options)
                else:
                    related_id = st.text_input("Related ID")
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
