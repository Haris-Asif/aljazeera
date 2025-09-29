import streamlit as st
from dashboard import show_dashboard
from plots_manager import show_plots_manager
from contacts_manager import show_contacts_manager
from crm_manager import show_crm_manager
from sold_listings import show_sold_listings

# Custom CSS for modern navy blue and gold theme
def inject_custom_css():
    st.markdown("""
    <style>
    /* Main theme colors */
    :root {
        --navy: #1e3a5f;
        --navy-dark: #0f2a4a;
        --navy-light: #2d4f7c;
        --gold: #d4af37;
        --gold-light: #e6c350;
        --gold-dark: #b8941f;
        --white: #ffffff;
        --gray-light: #f8f9fa;
    }
    
    /* Main background */
    .stApp {
        background-color: #f5f7fa;
    }
    
    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        color: var(--navy) !important;
        font-weight: 600 !important;
    }
    
    /* Sidebar */
    .css-1d391kg, .css-1lcbmhc {
        background-color: var(--navy) !important;
    }
    
    .css-1d391kg p, .css-1lcbmhc p {
        color: var(--white) !important;
    }
    
    /* Buttons */
    .stButton button {
        background-color: var(--gold) !important;
        color: var(--navy) !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton button:hover {
        background-color: var(--gold-light) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2) !important;
    }
    
    /* Metrics */
    .stMetric {
        background: linear-gradient(135deg, var(--navy), var(--navy-light)) !important;
        color: white !important;
        border-radius: 10px !important;
        padding: 1rem !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
    }
    
    .stMetric label {
        color: var(--gold) !important;
        font-weight: 600 !important;
    }
    
    .stMetric div {
        color: white !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }
    
    /* Dataframes and tables */
    .dataframe {
        border-radius: 10px !important;
        overflow: hidden !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: var(--navy-light) !important;
        color: white !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 0.5rem 1rem !important;
        font-weight: 500 !important;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: var(--gold) !important;
        color: var(--navy) !important;
        font-weight: 600 !important;
    }
    
    /* Select boxes and inputs */
    .stSelectbox, .stTextInput, .stNumberInput, .stDateInput, .stTextArea {
        border-radius: 8px !important;
    }
    
    /* Success messages */
    .stAlert [data-testid="stMarkdownContainer"] {
        color: var(--navy) !important;
    }
    
    /* Custom header */
    .main-header {
        background: linear-gradient(135deg, var(--navy), var(--navy-light));
        padding: 2rem;
        border-radius: 0 0 20px 20px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        color: white;
        text-align: center;
    }
    
    .business-name {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        color: var(--gold);
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .business-tagline {
        font-size: 1.2rem;
        opacity: 0.9;
        font-weight: 300;
    }
    
    /* Cards */
    .custom-card {
        background: white;
        border-radius: 15px;
        padding: 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        border-left: 4px solid var(--gold);
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# Streamlit setup
st.set_page_config(
    page_title="Al-Jazeera Real Estate Tool", 
    layout="wide",
    page_icon="🏡"
)

def main():
    # Inject custom CSS
    inject_custom_css()
    
    # Custom header with business name
    st.markdown("""
    <div class="main-header">
        <div class="business-name">🏡 Al-Jazeera Real Estate</div>
        <div class="business-tagline">Your Trusted Partner in Real Estate Excellence</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize session state for tab management
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Dashboard"
    if "selected_contact" not in st.session_state:
        st.session_state.selected_contact = None
    if "crm_subtab" not in st.session_state:
        st.session_state.crm_subtab = None
    
    # Create sidebar navigation
    with st.sidebar:
        st.markdown("""
        <div style='text-align: center; margin-bottom: 2rem;'>
            <h2 style='color: #d4af37; margin-bottom: 0;'>Navigation</h2>
            <hr style='border-color: #d4af37; margin: 0.5rem 0;'>
        </div>
        """, unsafe_allow_html=True)
        
        # Sidebar menu with icons
        menu_options = [
            ("📊 Dashboard", "Dashboard"),
            ("🏠 Plots", "Plots"), 
            ("👥 Contacts", "Contacts"),
            ("🎯 Leads Management", "Leads Management"),
            ("✅ Closed Deals", "Closed Deals")
        ]
        
        for icon, tab_name in menu_options:
            if st.button(
                f"{icon} {tab_name}", 
                key=f"btn_{tab_name}",
                use_container_width=True,
                type="primary" if st.session_state.active_tab == tab_name else "secondary"
            ):
                st.session_state.active_tab = tab_name
                st.rerun()
        
        # Add some spacing and info
        st.markdown("---")
        st.markdown("""
        <div style='text-align: center; color: #d4af37; font-size: 0.8rem;'>
            <p>Al-Jazeera Real Estate Tool</p>
            <p>v2.0 • Premium Edition</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Display the selected module
    if st.session_state.active_tab == "Dashboard":
        show_dashboard()
    elif st.session_state.active_tab == "Plots":
        show_plots_manager()
    elif st.session_state.active_tab == "Contacts":
        show_contacts_manager()
    elif st.session_state.active_tab == "Leads Management":
        show_crm_manager()
    elif st.session_state.active_tab == "Closed Deals":
        show_sold_listings()

if __name__ == "__main__":
    main()
