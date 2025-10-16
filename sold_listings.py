import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from utils import load_sold_data, load_marked_sold_data, sort_dataframe

def show_sold_listings():
    st.header("✅ Closed Deals & Sold Listings")
    
    # Load both sold data and marked sold data
    sold_df = load_sold_data()
    marked_sold_df = load_marked_sold_data()
    
    # Combine both datasets for display
    combined_df = pd.concat([sold_df, marked_sold_df], ignore_index=True)
    
    # Sort the combined data
    combined_df = sort_dataframe(combined_df)
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_sold = len(combined_df)
        st.metric("🏆 Total Sold", total_sold)
    
    with col2:
        if not combined_df.empty and "Sale Price" in combined_df.columns:
            try:
                total_revenue = combined_df["Sale Price"].apply(lambda x: float(x) if str(x).replace('.', '').isdigit() else 0).sum()
                st.metric("💰 Total Revenue", f"₹{total_revenue:,.0f}")
            except:
                st.metric("💰 Total Revenue", "₹0")
        else:
            st.metric("💰 Total Revenue", "₹0")
    
    with col3:
        if not combined_df.empty and "Sale Date" in combined_df.columns:
            try:
                current_month = datetime.now().strftime("%Y-%m")
                monthly_sales = len([date for date in combined_df["Sale Date"] if str(date).startswith(current_month)])
                st.metric("📈 This Month", monthly_sales)
            except:
                st.metric("📈 This Month", 0)
        else:
            st.metric("📈 This Month", 0)
    
    with col4:
        if not combined_df.empty and "Agent" in combined_df.columns:
            top_agent = combined_df["Agent"].value_counts().index[0] if not combined_df["Agent"].value_counts().empty else "N/A"
            st.metric("👑 Top Agent", top_agent)
        else:
            st.metric("👑 Top Agent", "N/A")
    
    # Filters
    st.subheader("🔍 Filter Sold Listings")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        sector_filter = st.text_input("Sector", key="sold_sector")
        agent_filter = st.text_input("Agent", key="sold_agent")
    
    with col2:
        buyer_filter = st.text_input("Buyer Name", key="sold_buyer")
        date_filter = st.selectbox("Time Period", ["All Time", "Last 30 Days", "Last 90 Days", "This Year"])
    
    with col3:
        min_price = st.number_input("Min Price", min_value=0, value=0, step=100000)
        max_price = st.number_input("Max Price", min_value=0, value=10000000, step=100000)
    
    # Apply filters
    filtered_sold = combined_df.copy()
    
    if sector_filter:
        filtered_sold = filtered_sold[filtered_sold["Sector"].str.contains(sector_filter, case=False, na=False)]
    
    if agent_filter:
        filtered_sold = filtered_sold[filtered_sold["Agent"].str.contains(agent_filter, case=False, na=False)]
    
    if buyer_filter:
        filtered_sold = filtered_sold[filtered_sold["Buyer Name"].str.contains(buyer_filter, case=False, na=False)]
    
    # Price filter
    if "Sale Price" in filtered_sold.columns:
        try:
            filtered_sold["Sale Price Num"] = filtered_sold["Sale Price"].apply(lambda x: float(x) if str(x).replace('.', '').isdigit() else 0)
            filtered_sold = filtered_sold[(filtered_sold["Sale Price Num"] >= min_price) & (filtered_sold["Sale Price Num"] <= max_price)]
        except:
            pass
    
    # Date filter
    if date_filter != "All Time" and "Sale Date" in filtered_sold.columns:
        cutoff_date = datetime.now()
        if date_filter == "Last 30 Days":
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - 30)
        elif date_filter == "Last 90 Days":
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - 90)
        elif date_filter == "This Year":
            cutoff_date = cutoff_date.replace(month=1, day=1)
        
        filtered_sold = filtered_sold[pd.to_datetime(filtered_sold["Sale Date"], errors='coerce') >= cutoff_date]
    
    # Display results
    st.subheader(f"📋 Sold Listings ({len(filtered_sold)} found)")
    
    if filtered_sold.empty:
        st.info("No sold listings found matching your criteria.")
        return
    
    # Create display columns
    display_columns = ["Sector", "Plot No", "Street No", "Plot Size", "Sale Price", "Buyer Name", "Agent", "Sale Date"]
    available_columns = [col for col in display_columns if col in filtered_sold.columns]
    
    # Display the dataframe
    st.dataframe(
        filtered_sold[available_columns],
        use_container_width=True,
        height=400
    )
    
    # Charts and analytics
    st.subheader("📊 Sales Analytics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if "Sector" in filtered_sold.columns and not filtered_sold.empty:
            sector_sales = filtered_sold["Sector"].value_counts().head(10)
            if not sector_sales.empty:
                fig_sector = px.bar(
                    x=sector_sales.values, 
                    y=sector_sales.index,
                    orientation='h',
                    title="Top Sectors by Sales Count",
                    color=sector_sales.values,
                    color_continuous_scale='viridis'
                )
                fig_sector.update_layout(
                    xaxis_title="Number of Sales",
                    yaxis_title="Sector",
                    showlegend=False
                )
                st.plotly_chart(fig_sector, use_container_width=True)
    
    with col2:
        if "Agent" in filtered_sold.columns and not filtered_sold.empty:
            agent_performance = filtered_sold["Agent"].value_counts().head(8)
            if not agent_performance.empty:
                fig_agent = px.pie(
                    values=agent_performance.values,
                    names=agent_performance.index,
                    title="Sales by Agent",
                    hole=0.4
                )
                st.plotly_chart(fig_agent, use_container_width=True)
    
    # Revenue trend
    if "Sale Date" in filtered_sold.columns and "Sale Price" in filtered_sold.columns and not filtered_sold.empty:
        try:
            filtered_sold["Sale Month"] = pd.to_datetime(filtered_sold["Sale Date"]).dt.to_period('M').astype(str)
            monthly_revenue = filtered_sold.groupby("Sale Month")["Sale Price Num"].sum().reset_index()
            
            if not monthly_revenue.empty:
                fig_revenue = px.line(
                    monthly_revenue,
                    x="Sale Month",
                    y="Sale Price Num",
                    title="Monthly Revenue Trend",
                    markers=True
                )
                fig_revenue.update_layout(
                    xaxis_title="Month",
                    yaxis_title="Revenue (₹)",
                    xaxis_tickangle=45
                )
                st.plotly_chart(fig_revenue, use_container_width=True)
        except:
            st.info("Could not generate revenue trend chart.")
    
    # Export option
    if st.button("📤 Export Sold Data to CSV"):
        csv = filtered_sold.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"sold_listings_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
