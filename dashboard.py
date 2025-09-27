import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from utils import load_plot_data, load_contacts, load_leads, load_lead_activities, load_tasks, load_appointments

def show_dashboard():
    st.title("🏡 Al-Jazeera Real Estate Dashboard")
    
    # Load data
    plots_df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    leads_df = load_leads()
    activities_df = load_lead_activities()
    tasks_df = load_tasks()
    appointments_df = load_appointments()
    
    # Today's date for filtering
    today = datetime.now().date()
    
    # Key Metrics
    st.subheader("📊 Today's Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # Today's new plots
        if not plots_df.empty and "Timestamp" in plots_df.columns:
            try:
                plots_df["Date"] = pd.to_datetime(plots_df["Timestamp"]).dt.date
                today_plots = len(plots_df[plots_df["Date"] == today])
                st.metric("📈 New Listings Today", today_plots)
            except:
                st.metric("📈 New Listings Today", 0)
        else:
            st.metric("📈 New Listings Today", 0)
    
    with col2:
        # Today's new contacts
        if not contacts_df.empty and "Timestamp" in contacts_df.columns:
            try:
                contacts_df["Date"] = pd.to_datetime(contacts_df["Timestamp"]).dt.date
                today_contacts = len(contacts_df[contacts_df["Date"] == today])
                st.metric("👥 New Contacts Today", today_contacts)
            except:
                st.metric("👥 New Contacts Today", 0)
        else:
            st.metric("👥 New Contacts Today", 0)
    
    with col3:
        # Today's new leads
        if not leads_df.empty and "Timestamp" in leads_df.columns:
            try:
                leads_df["Date"] = pd.to_datetime(leads_df["Timestamp"]).dt.date
                today_leads = len(leads_df[leads_df["Date"] == today])
                st.metric("🎯 New Leads Today", today_leads)
            except:
                st.metric("🎯 New Leads Today", 0)
        else:
            st.metric("🎯 New Leads Today", 0)
    
    with col4:
        # Today's activities
        if not activities_df.empty and "Timestamp" in activities_df.columns:
            try:
                activities_df["Date"] = pd.to_datetime(activities_df["Timestamp"]).dt.date
                today_activities = len(activities_df[activities_df["Date"] == today])
                st.metric("📞 Activities Today", today_activities)
            except:
                st.metric("📞 Activities Today", 0)
        else:
            st.metric("📞 Activities Today", 0)
    
    # CRM Overview
    st.subheader("👥 CRM Overview")
    
    if not leads_df.empty:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_leads = len(leads_df)
            st.metric("Total Leads", total_leads)
        
        with col2:
            new_leads = len(leads_df[leads_df["Status"] == "New"]) if "Status" in leads_df.columns else 0
            st.metric("New Leads", new_leads)
        
        with col3:
            active_leads = len(leads_df[leads_df["Status"].isin(["Contacted", "Follow-up", "Meeting Scheduled", "Negotiation"])]) if "Status" in leads_df.columns else 0
            st.metric("Active Leads", active_leads)
        
        with col4:
            won_leads = len(leads_df[leads_df["Status"] == "Deal Closed (Won)"]) if "Status" in leads_df.columns else 0
            st.metric("Deals Closed", won_leads)
    
    # Quick Stats Grid
    st.subheader("📈 Business Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_plots = len(plots_df)
        st.metric("🏠 Total Listings", total_plots)
    
    with col2:
        total_contacts = len(contacts_df)
        st.metric("📇 Total Contacts", total_contacts)
    
    with col3:
        if not tasks_df.empty:
            completed_tasks = len(tasks_df[tasks_df["Status"] == "Completed"])
            total_tasks = len(tasks_df)
            st.metric("✅ Tasks Completed", f"{completed_tasks}/{total_tasks}")
        else:
            st.metric("✅ Tasks Completed", "0/0")
    
    with col4:
        if not appointments_df.empty:
            upcoming_appointments = len(appointments_df[
                (pd.to_datetime(appointments_df["Date"]).dt.date >= today) &
                (pd.to_datetime(appointments_df["Date"]).dt.date <= today + timedelta(days=7))
            ])
            st.metric("📅 Upcoming Appointments", upcoming_appointments)
        else:
            st.metric("📅 Upcoming Appointments", 0)
    
    # Charts Section
    col1, col2 = st.columns(2)
    
    with col1:
        # Lead Status Chart
        if not leads_df.empty and "Status" in leads_df.columns:
            status_counts = leads_df["Status"].value_counts()
            if not status_counts.empty:
                status_df = pd.DataFrame({
                    'Status': status_counts.index,
                    'Count': status_counts.values
                })
                fig_status = px.pie(status_df, values='Count', names='Status', 
                                  title="Lead Status Distribution", hole=0.4)
                fig_status.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_status, use_container_width=True)
    
    with col2:
        # Activities Trend (Last 7 days)
        if not activities_df.empty and "Timestamp" in activities_df.columns:
            try:
                activities_df["Date"] = pd.to_datetime(activities_df["Timestamp"]).dt.date
                last_7_days = today - timedelta(days=7)
                recent_activities = activities_df[activities_df["Date"] >= last_7_days]
                
                if not recent_activities.empty:
                    activities_by_date = recent_activities.groupby("Date").size().reset_index(name="Count")
                    fig_activities = px.line(activities_by_date, x="Date", y="Count",
                                           title="Activities Trend (Last 7 Days)",
                                           markers=True)
                    fig_activities.update_layout(xaxis_title="Date", yaxis_title="Number of Activities")
                    st.plotly_chart(fig_activities, use_container_width=True)
            except:
                st.info("No activity data available for chart.")
    
    # Recent Activity Feed
    st.subheader("🕒 Recent Activity Feed")
    
    # Combine recent activities from different sources
    recent_items = []
    
    # Recent plots
    if not plots_df.empty and "Timestamp" in plots_df.columns:
        try:
            plots_df_sorted = plots_df.sort_values("Timestamp", ascending=False).head(3)
            for _, plot in plots_df_sorted.iterrows():
                recent_items.append({
                    "type": "📈",
                    "title": "New Listing Added",
                    "description": f"{plot.get('Sector', 'N/A')} - Plot {plot.get('Plot No', 'N/A')}",
                    "timestamp": plot["Timestamp"]
                })
        except:
            pass
    
    # Recent contacts
    if not contacts_df.empty and "Timestamp" in contacts_df.columns:
        try:
            contacts_df_sorted = contacts_df.sort_values("Timestamp", ascending=False).head(3)
            for _, contact in contacts_df_sorted.iterrows():
                recent_items.append({
                    "type": "👥",
                    "title": "New Contact Added",
                    "description": f"{contact.get('Name', 'N/A')} - {contact.get('Contact1', 'N/A')}",
                    "timestamp": contact["Timestamp"]
                })
        except:
            pass
    
    # Recent leads
    if not leads_df.empty and "Timestamp" in leads_df.columns:
        try:
            leads_df_sorted = leads_df.sort_values("Timestamp", ascending=False).head(3)
            for _, lead in leads_df_sorted.iterrows():
                recent_items.append({
                    "type": "🎯",
                    "title": "New Lead Created",
                    "description": f"{lead.get('Name', 'N/A')} - {lead.get('Status', 'N/A')}",
                    "timestamp": lead["Timestamp"]
                })
        except:
            pass
    
    # Recent activities
    if not activities_df.empty and "Timestamp" in activities_df.columns:
        try:
            activities_df_sorted = activities_df.sort_values("Timestamp", ascending=False).head(5)
            for _, activity in activities_df_sorted.iterrows():
                recent_items.append({
                    "type": "📞",
                    "title": f"{activity.get('Activity Type', 'Activity')}",
                    "description": f"With {activity.get('Lead Name', 'N/A')}",
                    "timestamp": activity["Timestamp"]
                })
        except:
            pass
    
    # Sort by timestamp and display
    if recent_items:
        recent_items.sort(key=lambda x: x["timestamp"], reverse=True)
        
        for item in recent_items[:10]:  # Show last 10 items
            with st.container():
                col1, col2 = st.columns([1, 10])
                with col1:
                    st.write(f"**{item['type']}**")
                with col2:
                    st.write(f"**{item['title']}**")
                    st.write(item['description'])
                    st.write(f"*{item['timestamp']}*")
                st.markdown("---")
    else:
        st.info("No recent activities to display.")
    
    # Quick Actions
    st.subheader("⚡ Quick Actions")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📊 View All Listings", use_container_width=True):
            st.session_state.active_tab = "Plots"
            st.rerun()
    
    with col2:
        if st.button("👥 Manage Contacts", use_container_width=True):
            st.session_state.active_tab = "Contacts"
            st.rerun()
    
    with col3:
        if st.button("🎯 CRM Dashboard", use_container_width=True):
            st.session_state.active_tab = "Leads Management"
            st.rerun()
    
    with col4:
        if st.button("📈 View Analytics", use_container_width=True):
            st.session_state.active_tab = "Leads Management"
            st.session_state.crm_subtab = "Analytics"
            st.rerun()
    
    # Overdue Tasks Warning
    if not tasks_df.empty and "Due Date" in tasks_df.columns and "Status" in tasks_df.columns:
        try:
            tasks_df["Due Date"] = pd.to_datetime(tasks_df["Due Date"], errors='coerce').dt.date
            overdue_tasks = tasks_df[
                (tasks_df["Status"] != "Completed") & 
                (tasks_df["Due Date"] < today)
            ]
            
            if not overdue_tasks.empty:
                st.warning(f"⚠️ You have {len(overdue_tasks)} overdue tasks that need attention!")
                
                with st.expander("View Overdue Tasks"):
                    for _, task in overdue_tasks.iterrows():
                        st.write(f"**{task['Title']}** - Due: {task['Due Date']} - Priority: {task.get('Priority', 'N/A')}")
        except:
            pass
    
    # Upcoming Appointments
    if not appointments_df.empty and "Date" in appointments_df.columns:
        try:
            appointments_df["Date"] = pd.to_datetime(appointments_df["Date"], errors='coerce').dt.date
            upcoming_appointments = appointments_df[
                (appointments_df["Date"] >= today) &
                (appointments_df["Date"] <= today + timedelta(days=3))
            ]
            
            if not upcoming_appointments.empty:
                st.info(f"📅 You have {len(upcoming_appointments)} appointments in the next 3 days")
                
                with st.expander("View Upcoming Appointments"):
                    for _, appt in upcoming_appointments.iterrows():
                        st.write(f"**{appt['Title']}** - {appt['Date']} at {appt.get('Time', 'N/A')} - {appt.get('Location', 'N/A')}")
        except:
            pass
