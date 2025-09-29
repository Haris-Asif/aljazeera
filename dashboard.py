import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from utils import load_plot_data, load_contacts, load_leads, load_lead_activities, load_tasks, load_appointments, load_sold_data

def show_dashboard():
    st.title("📊 Al-Jazeera Real Estate Dashboard")
    
    # Load data
    plots_df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    leads_df = load_leads()
    activities_df = load_lead_activities()
    tasks_df = load_tasks()
    appointments_df = load_appointments()
    sold_df = load_sold_data()
    
    # Today's date for filtering
    today = datetime.now().date()
    
    # Key Metrics with enhanced styling
    st.subheader("🎯 Today's Overview")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        # Today's new plots
        if not plots_df.empty and "Timestamp" in plots_df.columns:
            try:
                plots_df["Date"] = pd.to_datetime(plots_df["Timestamp"]).dt.date
                today_plots = len(plots_df[plots_df["Date"] == today])
                st.metric("📈 New Listings", today_plots)
            except:
                st.metric("📈 New Listings", 0)
        else:
            st.metric("📈 New Listings", 0)
    
    with col2:
        # Today's new contacts
        if not contacts_df.empty and "Timestamp" in contacts_df.columns:
            try:
                contacts_df["Date"] = pd.to_datetime(contacts_df["Timestamp"]).dt.date
                today_contacts = len(contacts_df[contacts_df["Date"] == today])
                st.metric("👥 New Contacts", today_contacts)
            except:
                st.metric("👥 New Contacts", 0)
        else:
            st.metric("👥 New Contacts", 0)
    
    with col3:
        # Today's new leads
        if not leads_df.empty and "Timestamp" in leads_df.columns:
            try:
                leads_df["Date"] = pd.to_datetime(leads_df["Timestamp"]).dt.date
                today_leads = len(leads_df[leads_df["Date"] == today])
                st.metric("🎯 New Leads", today_leads)
            except:
                st.metric("🎯 New Leads", 0)
        else:
            st.metric("🎯 New Leads", 0)
    
    with col4:
        # Today's activities
        if not activities_df.empty and "Timestamp" in activities_df.columns:
            try:
                activities_df["Date"] = pd.to_datetime(activities_df["Timestamp"]).dt.date
                today_activities = len(activities_df[activities_df["Date"] == today])
                st.metric("📞 Activities", today_activities)
            except:
                st.metric("📞 Activities", 0)
        else:
            st.metric("📞 Activities", 0)
    
    with col5:
        # Today's sales
        if not sold_df.empty and "Sale Date" in sold_df.columns:
            try:
                today_sales = len(sold_df[sold_df["Sale Date"] == today.strftime("%Y-%m-%d")])
                st.metric("💰 Sales Today", today_sales)
            except:
                st.metric("💰 Sales Today", 0)
        else:
            st.metric("💰 Sales Today", 0)
    
    # Business Overview Section
    st.subheader("🏢 Business Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_plots = len(plots_df)
        st.metric("🏠 Total Listings", total_plots)
    
    with col2:
        total_contacts = len(contacts_df)
        st.metric("📇 Total Contacts", total_contacts)
    
    with col3:
        total_leads = len(leads_df)
        st.metric("👥 Total Leads", total_leads)
    
    with col4:
        total_sold = len(sold_df)
        st.metric("✅ Total Sold", total_sold)
    
    # CRM Overview
    st.subheader("👥 CRM Overview")
    
    if not leads_df.empty:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            new_leads = len(leads_df[leads_df["Status"] == "New"]) if "Status" in leads_df.columns else 0
            st.metric("🆕 New Leads", new_leads)
        
        with col2:
            active_leads = len(leads_df[leads_df["Status"].isin(["Contacted", "Follow-up", "Meeting Scheduled", "Negotiation"])]) if "Status" in leads_df.columns else 0
            st.metric("🔄 Active Leads", active_leads)
        
        with col3:
            won_leads = len(leads_df[leads_df["Status"] == "Deal Closed (Won)"]) if "Status" in leads_df.columns else 0
            st.metric("🏆 Deals Closed", won_leads)
        
        with col4:
            if not tasks_df.empty:
                completed_tasks = len(tasks_df[tasks_df["Status"] == "Completed"])
                total_tasks = len(tasks_df)
                st.metric("✅ Tasks", f"{completed_tasks}/{total_tasks}")
            else:
                st.metric("✅ Tasks", "0/0")
    
    # Sales Performance
    st.subheader("💰 Sales Performance")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if not sold_df.empty and "Sale Price" in sold_df.columns:
            try:
                total_revenue = sold_df["Sale Price"].apply(lambda x: float(x) if str(x).replace('.', '').isdigit() else 0).sum()
                st.metric("💵 Total Revenue", f"₹{total_revenue:,.0f}")
            except:
                st.metric("💵 Total Revenue", "₹0")
        else:
            st.metric("💵 Total Revenue", "₹0")
    
    with col2:
        if not sold_df.empty and "Commission" in sold_df.columns:
            try:
                total_commission = sold_df["Commission"].apply(lambda x: float(x) if str(x).replace('.', '').isdigit() else 0).sum()
                st.metric("💸 Total Commission", f"₹{total_commission:,.0f}")
            except:
                st.metric("💸 Total Commission", "₹0")
        else:
            st.metric("💸 Total Commission", "₹0")
    
    with col3:
        if not sold_df.empty and "Sale Date" in sold_df.columns:
            try:
                current_month = datetime.now().strftime("%Y-%m")
                monthly_sales = len([date for date in sold_df["Sale Date"] if str(date).startswith(current_month)])
                st.metric("📈 Monthly Sales", monthly_sales)
            except:
                st.metric("📈 Monthly Sales", 0)
        else:
            st.metric("📈 Monthly Sales", 0)
    
    with col4:
        if not sold_df.empty and "Agent" in sold_df.columns:
            try:
                top_agent = sold_df["Agent"].value_counts().index[0] if not sold_df["Agent"].value_counts().empty else "N/A"
                st.metric("👑 Top Agent", top_agent)
            except:
                st.metric("👑 Top Agent", "N/A")
        else:
            st.metric("👑 Top Agent", "N/A")
    
    # Charts Section
    st.subheader("📈 Analytics & Insights")
    
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
                fig_status = px.pie(
                    status_df, 
                    values='Count', 
                    names='Status', 
                    title="📊 Lead Status Distribution",
                    color_discrete_sequence=px.colors.sequential.Blues_r
                )
                fig_status.update_traces(
                    textposition='inside', 
                    textinfo='percent+label',
                    marker=dict(line=dict(color='#000000', width=1))
                )
                fig_status.update_layout(
                    showlegend=True,
                    legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.1)
                )
                st.plotly_chart(fig_status, use_container_width=True)
        else:
            st.info("No lead data available for chart.")
    
    with col2:
        # Sales Trend (Last 30 days)
        if not sold_df.empty and "Sale Date" in sold_df.columns:
            try:
                sold_df["Sale Date"] = pd.to_datetime(sold_df["Sale Date"], errors='coerce')
                last_30_days = today - timedelta(days=30)
                recent_sales = sold_df[sold_df["Sale Date"].dt.date >= last_30_days]
                
                if not recent_sales.empty:
                    sales_by_date = recent_sales.groupby(recent_sales["Sale Date"].dt.date).size().reset_index(name="Count")
                    fig_sales = px.line(
                        sales_by_date, 
                        x="Sale Date", 
                        y="Count",
                        title="💰 Sales Trend (Last 30 Days)",
                        markers=True,
                        line_shape='spline'
                    )
                    fig_sales.update_layout(
                        xaxis_title="Date",
                        yaxis_title="Number of Sales",
                        plot_bgcolor='rgba(0,0,0,0)'
                    )
                    fig_sales.update_traces(line=dict(color='#d4af37', width=3))
                    st.plotly_chart(fig_sales, use_container_width=True)
                else:
                    st.info("No sales data for the last 30 days.")
            except Exception as e:
                st.info("Could not generate sales trend chart.")
        else:
            st.info("No sales data available.")
    
    # Additional Charts Row
    col1, col2 = st.columns(2)
    
    with col1:
        # Activities Trend (Last 7 days)
        if not activities_df.empty and "Timestamp" in activities_df.columns:
            try:
                activities_df["Date"] = pd.to_datetime(activities_df["Timestamp"]).dt.date
                last_7_days = today - timedelta(days=7)
                recent_activities = activities_df[activities_df["Date"] >= last_7_days]
                
                if not recent_activities.empty:
                    activities_by_date = recent_activities.groupby("Date").size().reset_index(name="Count")
                    fig_activities = px.bar(
                        activities_by_date, 
                        x="Date", 
                        y="Count",
                        title="📞 Daily Activities (Last 7 Days)",
                        color="Count",
                        color_continuous_scale='viridis'
                    )
                    fig_activities.update_layout(
                        xaxis_title="Date", 
                        yaxis_title="Number of Activities",
                        showlegend=False
                    )
                    st.plotly_chart(fig_activities, use_container_width=True)
            except:
                st.info("No activity data available for chart.")
    
    with col2:
        # Property Types Distribution
        if not plots_df.empty and "Property Type" in plots_df.columns:
            try:
                property_counts = plots_df["Property Type"].value_counts().head(8)
                if not property_counts.empty:
                    fig_property = px.pie(
                        values=property_counts.values,
                        names=property_counts.index,
                        title="🏠 Property Types Distribution",
                        hole=0.4
                    )
                    st.plotly_chart(fig_property, use_container_width=True)
            except:
                st.info("No property type data available.")
    
    # Recent Activity Feed with enhanced styling
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
                    "timestamp": plot["Timestamp"],
                    "color": "#E3F2FD"
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
                    "timestamp": contact["Timestamp"],
                    "color": "#E8F5E9"
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
                    "timestamp": lead["Timestamp"],
                    "color": "#FFF3E0"
                })
        except:
            pass
    
    # Recent sales
    if not sold_df.empty and "Timestamp" in sold_df.columns:
        try:
            sold_df_sorted = sold_df.sort_values("Timestamp", ascending=False).head(3)
            for _, sale in sold_df_sorted.iterrows():
                recent_items.append({
                    "type": "💰",
                    "title": "Property Sold",
                    "description": f"{sale.get('Sector', 'N/A')} to {sale.get('Buyer Name', 'N/A')}",
                    "timestamp": sale["Timestamp"],
                    "color": "#E8F5E9"
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
                    "timestamp": activity["Timestamp"],
                    "color": "#F3E5F5"
                })
        except:
            pass
    
    # Sort by timestamp and display
    if recent_items:
        recent_items.sort(key=lambda x: x["timestamp"], reverse=True)
        
        for item in recent_items[:8]:  # Show last 8 items
            with st.container():
                st.markdown(f"""
                <div style="background-color: {item['color']}; padding: 1rem; border-radius: 10px; margin-bottom: 0.5rem; border-left: 4px solid #1e3a5f;">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="font-size: 1.2rem;">{item['type']}</span>
                        <strong>{item['title']}</strong>
                    </div>
                    <p style="margin: 0.5rem 0 0 0; color: #555;">{item['description']}</p>
                    <small style="color: #777;">{item['timestamp']}</small>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No recent activities to display.")
    
    # Quick Actions with enhanced styling
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
        if st.button("✅ Closed Deals", use_container_width=True):
            st.session_state.active_tab = "Closed Deals"
            st.rerun()
    
    # Alerts and Notifications
    st.subheader("🔔 Notifications & Alerts")
    
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
                
                with st.expander("View Overdue Tasks", expanded=False):
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
                
                with st.expander("View Upcoming Appointments", expanded=False):
                    for _, appt in upcoming_appointments.iterrows():
                        st.write(f"**{appt['Title']}** - {appt['Date']} at {appt.get('Time', 'N/A')} - {appt.get('Location', 'N/A')}")
        except:
            pass
    
    # High Priority Leads
    if not leads_df.empty and "Priority" in leads_df.columns and "Status" in leads_df.columns:
        high_priority_leads = leads_df[
            (leads_df["Priority"] == "High") & 
            (~leads_df["Status"].isin(["Deal Closed (Won)", "Not Interested (Lost)"]))
        ].head(3)
        
        if not high_priority_leads.empty:
            st.error(f"🚨 You have {len(high_priority_leads)} high priority leads needing attention!")
            
            with st.expander("View High Priority Leads", expanded=False):
                for _, lead in high_priority_leads.iterrows():
                    st.write(f"**{lead['Name']}** - {lead.get('Phone', 'N/A')} - Next Action: {lead.get('Next Action', 'N/A')}")
