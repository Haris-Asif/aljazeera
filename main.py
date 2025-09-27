import streamlit as st
from dashboard import show_dashboard
from plots_manager import show_plots_manager
from contacts_manager import show_contacts_manager
from crm_manager import show_crm_manager

# Streamlit setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")

def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    
    # Initialize session state for tab management
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Dashboard"
    if "selected_contact" not in st.session_state:
        st.session_state.selected_contact = None
    if "crm_subtab" not in st.session_state:
        st.session_state.crm_subtab = None
    
    # Create sidebar navigation
    st.sidebar.title("Navigation")
    
    # Sidebar menu
    menu_options = ["Dashboard", "Plots", "Contacts", "Leads Management"]
    selected_tab = st.sidebar.radio("Go to", menu_options, index=menu_options.index(st.session_state.active_tab))
    
    # Update active tab
    if selected_tab != st.session_state.active_tab:
        st.session_state.active_tab = selected_tab
        st.rerun()
    
    # Display the selected module
    if st.session_state.active_tab == "Dashboard":
        show_dashboard()
    elif st.session_state.active_tab == "Plots":
        show_plots_manager()
    elif st.session_state.active_tab == "Contacts":
        show_contacts_manager()
    elif st.session_state.active_tab == "Leads Management":
        show_crm_manager()

if __name__ == "__main__":
    main()
