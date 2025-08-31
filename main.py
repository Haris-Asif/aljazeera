import streamlit as st
import pandas as pd
import gspread
import re
import difflib
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import urllib.parse
from typing import Dict, List, Tuple, Optional, Any, Set
import logging
from dataclasses import dataclass
from enum import Enum
import time
from functools import lru_cache

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
class SheetNames:
    SPREADSHEET = "Al-Jazeera"
    PLOTS = "Plots"
    CONTACTS = "Contacts"
    LEADS = "Leads"
    ACTIVITIES = "LeadActivities"
    TASKS = "Tasks"
    APPOINTMENTS = "Appointments"

class LeadStatus(Enum):
    NEW = "New"
    CONTACTED = "Contacted"
    FOLLOW_UP = "Follow-up"
    MEETING_SCHEDULED = "Meeting Scheduled"
    NEGOTIATION = "Negotiation"
    OFFER_MADE = "Offer Made"
    DEAL_CLOSED = "Deal Closed (Won)"
    NOT_INTERESTED = "Not Interested (Lost)"

class Priority(Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

class ActivityType(Enum):
    CALL = "Call"
    MEETING = "Meeting"
    EMAIL = "Email"
    WHATSAPP = "WhatsApp"
    SITE_VISIT = "Site Visit"
    STATUS_UPDATE = "Status Update"
    NOTE = "Note"

# Data classes for type safety
@dataclass
class Lead:
    id: str
    timestamp: str
    name: str
    phone: str
    email: str
    source: str
    status: LeadStatus
    priority: Priority
    property_interest: str
    budget: float
    location_preference: str
    last_contact: str
    next_action: str
    next_action_type: str
    notes: str
    assigned_to: str
    lead_score: int
    type: str
    timeline: str

@dataclass
class Plot:
    sector: str
    plot_no: str
    plot_size: str
    demand: str
    street_no: str
    extracted_contact: str
    features: str
    property_type: str
    timestamp: str
    sheet_row_num: int

# Streamlit setup
st.set_page_config(page_title="Al-Jazeera Real Estate CRM", layout="wide")

# Error handling decorator
def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            st.error(f"An error occurred in {func.__name__}: {str(e)}")
            return None
    return wrapper

# --- Enhanced Helpers ---
def clean_number(num: str) -> str:
    """Remove all non-digit characters from a phone number"""
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text: str) -> List[str]:
    """Extract all phone numbers from text"""
    text = str(text or "")
    parts = re.split(r"[,\s]+", text)
    return [clean_number(p) for p in parts if clean_number(p)]

def parse_price(price_str: str) -> Optional[float]:
    """Parse price string to float, handling various formats"""
    try:
        price_str = str(price_str).lower().replace(",", "").replace("cr", "00").replace("crore", "00")
        numbers = re.findall(r"\d+\.?\d*", price_str)
        return float(numbers[0]) if numbers else None
    except (ValueError, TypeError):
        return None

def get_all_unique_features(df: pd.DataFrame) -> List[str]:
    """Get all unique features from the dataframe"""
    feature_set = set()
    for f in df["Features"].fillna("").astype(str):
        parts = [p.strip().lower() for p in f.split(",") if p.strip()]
        feature_set.update(parts)
    return sorted(feature_set)

def fuzzy_feature_match(row_features: str, selected_features: List[str]) -> bool:
    """Fuzzy match features using difflib"""
    row_features = [f.strip().lower() for f in str(row_features or "").split(",")]
    for sel in selected_features:
        match = difflib.get_close_matches(sel.lower(), row_features, n=1, cutoff=0.7)
        if match:
            return True
    return False

def sector_matches(filter_sector: str, compare_sector: str) -> bool:
    """Check if sectors match with proper formatting"""
    if not filter_sector:
        return True
    filter_sector = filter_sector.replace(" ", "").upper()
    compare_sector = str(compare_sector).replace(" ", "").upper()
    return filter_sector in compare_sector if "/" not in filter_sector else filter_sector == compare_sector

def safe_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Create a safe copy of dataframe for display"""
    try:
        df = df.copy()
        df = df.drop(columns=["ParsedDate", "ParsedPrice"], errors="ignore")
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
        return df
    except Exception as e:
        logger.error(f"Error creating safe dataframe: {e}")
        st.error(f"⚠️ Error displaying table: {e}")
        return pd.DataFrame()
# Google Sheets Service with caching and error handling
class GoogleSheetsService:
    def __init__(self):
        self.scope = ["https://spreadsheets.google.com/feeds", 
                     "https://www.googleapis.com/auth/drive"]
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            try:
                creds_dict = st.secrets["gcp_service_account"]
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, self.scope)
                self._client = gspread.authorize(creds)
            except Exception as e:
                logger.error(f"Failed to initialize Google Sheets client: {e}")
                st.error("Failed to connect to Google Sheets. Please check your credentials.")
                raise
        return self._client
    
    @handle_errors
    def get_worksheet(self, sheet_name: str):
        """Get worksheet by name"""
        return self.client.open(SheetNames.SPREADSHEET).worksheet(sheet_name)
    
    @handle_errors
    def create_worksheet_if_not_exists(self, sheet_name: str, rows: int = 100, cols: int = 20):
        """Create worksheet if it doesn't exist"""
        try:
            return self.get_worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            try:
                spreadsheet = self.client.open(SheetNames.SPREADSHEET)
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=rows, cols=cols)
                logger.info(f"Created new worksheet: {sheet_name}")
                return worksheet
            except Exception as e:
                logger.error(f"Failed to create worksheet {sheet_name}: {e}")
                raise
    
    @handle_errors
    @lru_cache(maxsize=32)
    def load_data(self, sheet_name: str, expected_columns: List[str] = None) -> pd.DataFrame:
        """Load data from worksheet with caching"""
        try:
            worksheet = self.get_worksheet(sheet_name)
            records = worksheet.get_all_records()
            df = pd.DataFrame(records)
            
            if not df.empty and expected_columns:
                # Ensure all expected columns exist
                for col in expected_columns:
                    if col not in df.columns:
                        df[col] = ""
            
            return df
        except Exception as e:
            logger.error(f"Error loading data from {sheet_name}: {e}")
            return pd.DataFrame(columns=expected_columns or [])
    
    @handle_errors
    def save_data(self, sheet_name: str, df: pd.DataFrame, columns: List[str]) -> bool:
        """Save data to worksheet"""
        try:
            worksheet = self.get_worksheet(sheet_name)
            worksheet.clear()
            
            # Add header row
            worksheet.append_row(columns)
            
            # Add data rows in batches to avoid API limits
            batch_size = 100
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i+batch_size]
                for _, row in batch.iterrows():
                    row_data = [row.get(col, "") for col in columns]
                    worksheet.append_row(row_data)
                
                # Add delay to avoid rate limiting
                if i + batch_size < len(df):
                    time.sleep(1)
            
            logger.info(f"Successfully saved {len(df)} rows to {sheet_name}")
            return True
        except Exception as e:
            logger.error(f"Error saving data to {sheet_name}: {e}")
            st.error(f"Failed to save data to {sheet_name}: {str(e)}")
            return False

# Initialize Google Sheets service
gs_service = GoogleSheetsService()

# Data loading functions with proper error handling
@handle_errors
@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_plot_data() -> pd.DataFrame:
    """Load plot data from Google Sheets"""
    df = gs_service.load_data(SheetNames.PLOTS)
    if not df.empty:
        df["SheetRowNum"] = [i + 2 for i in range(len(df))]  # Start from row 2
    else:
        df = pd.DataFrame(columns=["SheetRowNum"])
    return df

@handle_errors
@st.cache_data(ttl=300)
def load_contacts() -> pd.DataFrame:
    """Load contacts data from Google Sheets"""
    return gs_service.load_data(SheetNames.CONTACTS)

@handle_errors
@st.cache_data(ttl=300)
def load_leads() -> pd.DataFrame:
    """Load leads data from Google Sheets"""
    expected_columns = [
        "ID", "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
        "Priority", "Property Interest", "Budget", "Location Preference",
        "Last Contact", "Next Action", "Next Action Type", "Notes", 
        "Assigned To", "Lead Score", "Type", "Timeline"
    ]
    
    # Ensure worksheet exists
    gs_service.create_worksheet_if_not_exists(SheetNames.LEADS, 100, len(expected_columns))
    
    return gs_service.load_data(SheetNames.LEADS, expected_columns)

@handle_errors
@st.cache_data(ttl=300)
def load_lead_activities() -> pd.DataFrame:
    """Load lead activities data from Google Sheets"""
    expected_columns = [
        "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
        "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
    ]
    
    # Ensure worksheet exists
    gs_service.create_worksheet_if_not_exists(SheetNames.ACTIVITIES, 100, len(expected_columns))
    
    return gs_service.load_data(SheetNames.ACTIVITIES, expected_columns)

@handle_errors
@st.cache_data(ttl=300)
def load_tasks() -> pd.DataFrame:
    """Load tasks data from Google Sheets"""
    expected_columns = [
        "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
        "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
    ]
    
    # Ensure worksheet exists
    gs_service.create_worksheet_if_not_exists(SheetNames.TASKS, 100, len(expected_columns))
    
    return gs_service.load_data(SheetNames.TASKS, expected_columns)

@handle_errors
@st.cache_data(ttl=300)
def load_appointments() -> pd.DataFrame:
    """Load appointments data from Google Sheets"""
    expected_columns = [
        "ID", "Timestamp", "Title", "Description", "Date", "Time", 
        "Duration", "Attendees", "Location", "Status", "Related To", 
        "Related ID", "Outcome"
    ]
    
    # Ensure worksheet exists
    gs_service.create_worksheet_if_not_exists(SheetNames.APPOINTMENTS, 100, len(expected_columns))
    
    return gs_service.load_data(SheetNames.APPOINTMENTS, expected_columns)

# Data saving functions
@handle_errors
def save_leads(df: pd.DataFrame) -> bool:
    """Save leads data to Google Sheets"""
    columns = [
        "ID", "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
        "Priority", "Property Interest", "Budget", "Location Preference",
        "Last Contact", "Next Action", "Next Action Type", "Notes", 
        "Assigned To", "Lead Score", "Type", "Timeline"
    ]
    return gs_service.save_data(SheetNames.LEADS, df, columns)

@handle_errors
def save_lead_activity(df: pd.DataFrame) -> bool:
    """Save lead activities data to Google Sheets"""
    columns = [
        "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
        "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
    ]
    return gs_service.save_data(SheetNames.ACTIVITIES, df, columns)

@handle_errors
def save_tasks(df: pd.DataFrame) -> bool:
    """Save tasks data to Google Sheets"""
    columns = [
        "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
        "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
    ]
    return gs_service.save_data(SheetNames.TASKS, df, columns)

@handle_errors
def save_appointments(df: pd.DataFrame) -> bool:
    """Save appointments data to Google Sheets"""
    columns = [
        "ID", "Timestamp", "Title", "Description", "Date", "Time", 
        "Duration", "Attendees", "Location", "Status", "Related To", 
        "Related ID", "Outcome"
    ]
    return gs_service.save_data(SheetNames.APPOINTMENTS, df, columns)
# Date filtering utility
def filter_by_date(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Filter dataframe by date range"""
    if label == "All":
        return df
    
    days_map = {
        "Last 7 Days": 7, 
        "Last 15 Days": 15, 
        "Last 30 Days": 30, 
        "Last 2 Months": 60
    }
    
    cutoff = datetime.now() - timedelta(days=days_map.get(label, 0))
    
    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            return None
    
    df["ParsedDate"] = df["Timestamp"].apply(try_parse)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

# Contact mapping utilities
def build_name_map(df: pd.DataFrame) -> Tuple[List[str], Dict[str, str]]:
    """Build mapping of contact numbers to names"""
    contact_to_name = {}
    
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name", "")).strip()
        contacts = extract_numbers(row.get("Extracted Contact", ""))
        
        for c in contacts:
            if c and c not in contact_to_name:
                contact_to_name[c] = name
    
    # Group by name
    name_groups = {}
    for c, name in contact_to_name.items():
        name_groups.setdefault(name, set()).add(c)
    
    # Create merged mapping
    merged = {}
    for name, numbers in name_groups.items():
        for c in numbers:
            merged[c] = name
    
    # Create numbered dealer list
    numbered_dealers = []
    for i, name in enumerate(sorted(name_groups.keys()), 1):
        numbered_dealers.append(f"{i}. {name}")
    
    return numbered_dealers, merged

# WhatsApp utilities
def _extract_int(val: str) -> int:
    """Extract first integer from a string for sorting"""
    try:
        m = re.search(r"\d+", str(val))
        return int(m.group()) if m else float("inf")
    except (ValueError, TypeError):
        return float("inf")

def _url_encode_for_whatsapp(text: str) -> str:
    """URL encode text for WhatsApp"""
    return urllib.parse.quote(text)

def _split_blocks_for_limits(blocks: List[str], plain_limit: int = 3000, encoded_limit: int = 1800) -> List[str]:
    """Split message blocks to respect WhatsApp limits"""
    chunks = []
    current = ""

    for block in blocks:
        candidate = current + block
        candidate_encoded = _url_encode_for_whatsapp(candidate)
        
        if len(candidate) > plain_limit or len(candidate_encoded) > encoded_limit:
            if current:
                chunks.append(current.rstrip())
                current = ""

            if len(block) > plain_limit or len(_url_encode_for_whatsapp(block)) > encoded_limit:
                lines = block.splitlines(keepends=True)
                small = ""
                for ln in lines:
                    cand2 = small + ln
                    cand2_encoded = _url_encode_for_whatsapp(cand2)
                    
                    if len(cand2) > plain_limit or len(cand2_encoded) > encoded_limit:
                        if small:
                            chunks.append(small.rstrip())
                            small = ""
                        
                        if len(ln) > plain_limit or len(_url_encode_for_whatsapp(ln)) > encoded_limit:
                            seg = ln
                            while seg:
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

def generate_whatsapp_messages(df: pd.DataFrame) -> List[str]:
    """Generate WhatsApp messages from plot data"""
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

    # Remove duplicates
    seen = set()
    unique = []
    for row in filtered:
        key = (row["Sector"], row["Plot No"], row["Plot Size"], row["Demand"])
        if key not in seen:
            seen.add(key)
            unique.append(row)

    # Group by sector and size
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    # Generate message blocks
    blocks = []
    for (sector, size), listings in grouped.items():
        # Sort by plot number
        listings = sorted(
            listings,
            key=lambda x: (_extract_int(x["Plot No"]), str(x["Plot No"]))
        )

        lines = []
        for r in listings:
            if sector.startswith("I-15/"):
                lines.append(f"St: {r['Street No']} | P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")
            else:
                lines.append(f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")

        header = f"*Available Options in {sector} Size: {size}*\n"
        block = header + "\n".join(lines) + "\n\n"
        blocks.append(block)

    # Split into chunks respecting limits
    messages = _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800)
    return messages

@handle_errors
def delete_rows_from_sheet(row_numbers: List[int]) -> bool:
    """Delete rows from Google Sheet"""
    try:
        sheet = gs_service.get_worksheet(SheetNames.PLOTS)
        
        valid_rows = [row_num for row_num in row_numbers if row_num > 1]
        if not valid_rows:
            return True
            
        valid_rows.sort(reverse=True)
        
        # Delete in batches to avoid API limits
        BATCH_SIZE = 10
        for i in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[i:i+BATCH_SIZE]
            for row_num in batch:
                try:
                    sheet.delete_rows(row_num)
                except Exception as e:
                    logger.error(f"Error deleting row {row_num}: {str(e)}")
                    continue
                    
            time.sleep(1)  # Avoid rate limiting
            
        return True
    except Exception as e:
        logger.error(f"Error in delete operation: {str(e)}")
        st.error(f"Error deleting rows: {str(e)}")
        return False

def create_duplicates_view(df: pd.DataFrame) -> Tuple[Optional[Any], pd.DataFrame]:
    """Create view of duplicate listings"""
    if df.empty:
        return None, pd.DataFrame()
    
    df["GroupKey"] = (
        df["Sector"].astype(str) + "|" + 
        df["Plot No"].astype(str) + "|" + 
        df["Street No"].astype(str) + "|" + 
        df["Plot Size"].astype(str)
    )
    
    group_counts = df["GroupKey"].value_counts()
    duplicate_groups = group_counts[group_counts >= 2].index
    duplicate_df = df[df["GroupKey"].isin(duplicate_groups)]
    
    if duplicate_df.empty:
        return None, duplicate_df
    
    duplicate_df = duplicate_df.sort_values(by="GroupKey")
    return None, duplicate_df  # Simplified for enterprise use

# ID generation utilities
def generate_lead_id() -> str:
    return f"L{int(datetime.now().timestamp())}"

def generate_activity_id() -> str:
    return f"A{int(datetime.now().timestamp())}"

def generate_task_id() -> str:
    return f"T{int(datetime.now().timestamp())}"

def generate_appointment_id() -> str:
    return f"AP{int(datetime.now().timestamp())}"

def calculate_lead_score(lead_data: Dict[str, Any], activities_df: pd.DataFrame) -> int:
    """Calculate lead score based on various factors"""
    score = 0
    
    # Score based on status
    status_scores = {
        LeadStatus.NEW.value: 10,
        LeadStatus.CONTACTED.value: 20,
        LeadStatus.FOLLOW_UP.value: 30,
        LeadStatus.MEETING_SCHEDULED.value: 50,
        LeadStatus.NEGOTIATION.value: 70,
        LeadStatus.OFFER_MADE.value: 80,
        LeadStatus.DEAL_CLOSED.value: 100,
        LeadStatus.NOT_INTERESTED.value: 0
    }
    score += status_scores.get(lead_data.get("Status", "New"), 10)
    
    # Score based on priority
    priority_scores = {
        Priority.LOW.value: 5, 
        Priority.MEDIUM.value: 10, 
        Priority.HIGH.value: 20
    }
    score += priority_scores.get(lead_data.get("Priority", "Low"), 5)
    
    # Score based on activities count
    lead_activities = activities_df[activities_df["Lead ID"] == lead_data.get("ID", "")]
    score += min(len(lead_activities) * 5, 30)  # Max 30 points for activities
    
    # Score based on budget
    if lead_data.get("Budget") and str(lead_data.get("Budget")).isdigit():
        budget = int(lead_data.get("Budget"))
        if budget > 5000000:  # Above 50 lakhs
            score += 20
        elif budget > 2000000:  # Above 20 lakhs
            score += 10
    
    return min(score, 100)  # Cap at 100
# Phone number utilities
def format_phone_number(phone: str) -> str:
    """Format phone number for dialer link"""
    if not phone:
        return ""
    
    # Clean the phone number
    clean_phone = re.sub(r'[^\d+]', '', str(phone))
    
    # Add country code if missing
    if clean_phone.startswith('0'):
        clean_phone = '+92' + clean_phone[1:]  # Pakistan country code
    elif not clean_phone.startswith('+'):
        clean_phone = '+92' + clean_phone  # Pakistan country code
    
    return clean_phone

def create_dialer_link(phone: str) -> str:
    """Create tel: link for phone number"""
    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return ""
    
    return f"tel:{formatted_phone}"

def display_phone_with_dialer(phone: str) -> str:
    """Display phone number with dialer link"""
    if not phone:
        return ""
    
    dialer_link = create_dialer_link(phone)
    if dialer_link:
        return f'<a href="{dialer_link}" style="color: #1f77b4; text-decoration: none;">{phone}</a>'
    else:
        return phone

def format_contact_column(contact_str: str) -> str:
    """Format Extracted Contact column with dialer links for each number"""
    if not contact_str:
        return ""
    
    numbers = extract_numbers(contact_str)
    formatted_numbers = []
    
    for num in numbers:
        dialer_link = create_dialer_link(num)
        if dialer_link:
            formatted_numbers.append(
                f'<a href="{dialer_link}" style="color: #1f77b4; text-decoration: none;">{num}</a>'
            )
        else:
            formatted_numbers.append(num)
    
    return ", ".join(formatted_numbers)

# UI Components
def display_lead_timeline(lead_id: str, lead_name: str, lead_phone: str):
    """Display timeline of activities for a lead"""
    st.subheader(f"📋 Timeline for: {lead_name}")
    
    activities_df = load_lead_activities()
    lead_activities = activities_df[(activities_df["Lead ID"] == lead_id)]
    
    if lead_activities.empty:
        st.info("No activities recorded for this lead yet.")
        return
    
    lead_activities = lead_activities.sort_values("Timestamp", ascending=False)
    
    for _, activity in lead_activities.iterrows():
        with st.container():
            col1, col2 = st.columns([1, 4])
            
            with col1:
                timestamp = activity["Timestamp"]
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        pass
                
                if isinstance(timestamp, datetime):
                    st.write(timestamp.strftime("%b %d, %Y"))
                    st.write(timestamp.strftime("%I:%M %p"))
                else:
                    st.write(str(timestamp))
            
            with col2:
                activity_type = activity["Activity Type"]
                color_map = {
                    ActivityType.CALL.value: "#E3F2FD",
                    ActivityType.MEETING.value: "#E8F5E9",
                    ActivityType.EMAIL.value: "#FFF3E0",
                    ActivityType.WHATSAPP.value: "#E8F5E9",
                    ActivityType.SITE_VISIT.value: "#E0F2F1",
                    ActivityType.STATUS_UPDATE.value: "#F3E5F5"
                }
                
                color = color_map.get(activity_type, "#F5F5F5")
                icon = "📞" if activity_type == ActivityType.CALL.value else \
                       "👥" if activity_type == ActivityType.MEETING.value else \
                       "📧" if activity_type == ActivityType.EMAIL.value else \
                       "💬" if activity_type == ActivityType.WHATSAPP.value else \
                       "🏠" if activity_type == ActivityType.SITE_VISIT.value else \
                       "🔄" if activity_type == ActivityType.STATUS_UPDATE.value else "📝"
                
                st.markdown(f"**{icon} {activity_type}**")
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
                
                if activity["Outcome"] and pd.notna(activity["Outcome"]):
                    st.markdown(f"**Outcome:** {activity['Outcome']}")
            
            st.markdown("---")

def display_lead_analytics(leads_df: pd.DataFrame, activities_df: pd.DataFrame):
    """Display lead analytics dashboard"""
    st.subheader("📊 Lead Analytics")
    
    if leads_df.empty:
        st.info("No leads data available for analytics.")
        return
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Lead status distribution
        if "Status" in leads_df.columns:
            status_counts = leads_df["Status"].value_counts()
            if not status_counts.empty:
                status_df = pd.DataFrame({
                    'Status': status_counts.index,
                    'Count': status_counts.values
                })
                fig_status = px.pie(status_df, values='Count', names='Status', title="Leads by Status")
                st.plotly_chart(fig_status, use_container_width=True)
            else:
                st.info("No status data available.")
    
    with col2:
        # Lead source distribution
        if "Source" in leads_df.columns:
            source_counts = leads_df["Source"].value_counts()
            if not source_counts.empty:
                source_df = pd.DataFrame({
                    'Source': source_counts.index,
                    'Count': source_counts.values
                })
                fig_source = px.bar(source_df, x='Count', y='Source', orientation='h',
                                  title="Leads by Source")
                st.plotly_chart(fig_source, use_container_width=True)
            else:
                st.info("No source data available.")
    
    with col3:
        # Lead score distribution
        if "Lead Score" in leads_df.columns:
            try:
                leads_df["Lead Score"] = pd.to_numeric(leads_df["Lead Score"], errors='coerce')
                score_data = leads_df["Lead Score"].dropna()
                if not score_data.empty:
                    fig_score = px.histogram(leads_df, x="Lead Score", nbins=10, 
                                           title="Lead Score Distribution")
                    st.plotly_chart(fig_score, use_container_width=True)
                else:
                    st.info("No lead score data available.")
            except (ValueError, TypeError):
                st.info("No lead score data available.")
    
    # Conversion funnel
    st.subheader("📈 Conversion Funnel")
    funnel_data = {
        "Stage": ["New", "Contacted", "Meeting", "Negotiation", "Closed Won"],
        "Count": [
            len(leads_df[leads_df["Status"] == "New"]) if "Status" in leads_df.columns else 0,
            len(leads_df[leads_df["Status"].isin(["Contacted", "Follow-up"])]) if "Status" in leads_df.columns else 0,
            len(leads_df[leads_df["Status"] == "Meeting Scheduled"]) if "Status" in leads_df.columns else 0,
            len(leads_df[leads_df["Status"].isin(["Negotiation", "Offer Made"])]) if "Status" in leads_df.columns else 0,
            len(leads_df[leads_df["Status"] == "Deal Closed (Won)"]) if "Status" in leads_df.columns else 0
        ]
    }
    
    funnel_df = pd.DataFrame(funnel_data)
    fig_funnel = px.funnel(funnel_df, x='Count', y='Stage', title="Lead Conversion Funnel")
    st.plotly_chart(fig_funnel, use_container_width=True)
    
    # Activities over time
    st.subheader("📅 Activities Over Time")
    if not activities_df.empty and "Timestamp" in activities_df.columns:
        try:
            activities_df["Date"] = pd.to_datetime(activities_df["Timestamp"]).dt.date
            activities_by_date = activities_df.groupby("Date").size().reset_index(name="Count")
            
            if not activities_by_date.empty:
                fig_activities = px.line(activities_by_date, x="Date", y="Count", 
                                        title="Daily Activities Trend")
                st.plotly_chart(fig_activities, use_container_width=True)
            else:
                st.info("No activities data available.")
        except (ValueError, TypeError):
            st.info("No activities data available.")
    else:
        st.info("No activities data available.")
