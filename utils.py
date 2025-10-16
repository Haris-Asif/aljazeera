import streamlit as st
import pandas as pd
import gspread
import re
import difflib
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
import tempfile
import os
import numpy as np
import chardet
import time
from googleapiclient.errors import HttpError
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import urllib.parse
from typing import Dict, List, Tuple, Optional, Any, Set, Union
import logging
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
SPREADSHEET_NAME = "Al-Jazeera"
PLOTS_SHEET = "Plots"
CONTACTS_SHEET = "Contacts"
LEADS_SHEET = "Leads"
ACTIVITIES_SHEET = "LeadActivities"
TASKS_SHEET = "Tasks"
APPOINTMENTS_SHEET = "Appointments"
SOLD_SHEET = "Sold"
MARKED_SOLD_SHEET = "MarkedSold"
BATCH_SIZE = 10
API_DELAY = 1

# Enums
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

class TaskStatus(Enum):
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"

class AppointmentStatus(Enum):
    SCHEDULED = "Scheduled"
    CONFIRMED = "Confirmed"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

# Helper Functions
def clean_number(num):
    return re.sub(r"[^\d]", "", str(num or ""))

def extract_numbers(text):
    text = str(text or "")
    parts = re.split(r"[,\s]+", text)
    return [clean_number(p) for p in parts if clean_number(p)]

def parse_price(price_str):
    try:
        price_str = str(price_str).lower().replace(",", "").replace("cr", "00").replace("crore", "00")
        numbers = re.findall(r"\d+\.?\d*", price_str)
        return float(numbers[0]) if numbers else None
    except:
        return None

def get_all_unique_features(df):
    feature_set = set()
    if "Features" in df.columns:
        for f in df["Features"].fillna("").astype(str):
            parts = [p.strip().lower() for p in f.split(",") if p.strip()]
            feature_set.update(parts)
    return sorted(feature_set)

def fuzzy_feature_match(row_features, selected_features):
    row_features = [f.strip().lower() for f in str(row_features or "").split(",")]
    for sel in selected_features:
        match = difflib.get_close_matches(sel.lower(), row_features, n=1, cutoff=0.7)
        if match:
            return True
    return False

def sector_matches(f, c):
    if not f:
        return True
    f = f.replace(" ", "").upper()
    c = str(c).replace(" ", "").upper()
    return f in c if "/" not in f else f == c

def safe_dataframe(df):
    """Ensure DataFrame has consistent data types for Arrow compatibility"""
    try:
        df = df.copy()
        df = df.drop(columns=["ParsedDate", "ParsedPrice"], errors="ignore")
        
        # Convert all object columns to string to avoid mixed type issues
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
        
        return df
    except Exception as e:
        st.error(f"⚠️ Error displaying table: {e}")
        return pd.DataFrame()

def safe_dataframe_for_display(df):
    """Ensure DataFrame has consistent data types for Arrow compatibility in data editor"""
    try:
        df = df.copy()
        
        # Convert all object columns to string to avoid mixed type issues
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
        
        # Ensure specific problematic columns are properly handled
        if "Demand" in df.columns:
            df["Demand"] = df["Demand"].astype(str)
        if "Plot No" in df.columns:
            df["Plot No"] = df["Plot No"].astype(str)
        if "Street No" in df.columns:
            df["Street No"] = df["Street No"].astype(str)
        if "Plot Size" in df.columns:
            df["Plot Size"] = df["Plot Size"].astype(str)
        
        return df
    except Exception as e:
        st.error(f"⚠️ Error preparing table for display: {e}")
        return df

def filter_by_date(df, label):
    if df.empty or label == "All":
        return df
        
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.now() - timedelta(days=days_map.get(label, 0))
    
    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            try:
                return datetime.strptime(val.strip(), "%m/%d/%Y %H:%M:%S")
            except:
                return None
                
    if "Timestamp" in df.columns:
        df["ParsedDate"] = df["Timestamp"].apply(try_parse)
        return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]
    else:
        return df

def build_name_map(df):
    contact_to_name = {}
    if df.empty or "Extracted Name" not in df.columns or "Extracted Contact" not in df.columns:
        return [], {}
        
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name", "")).strip()
        contacts = extract_numbers(row.get("Extracted Contact", ""))
        for c in contacts:
            if c and c not in contact_to_name:
                contact_to_name[c] = name
                
    name_groups = {}
    for c, name in contact_to_name.items():
        name_groups.setdefault(name, set()).add(c)
        
    merged = {}
    for c in contact_to_name:
        merged[c] = contact_to_name[c]
        
    name_set = {}
    for _, row in df.iterrows():
        numbers = extract_numbers(row.get("Extracted Contact", ""))
        for c in numbers:
            if c in merged:
                name_set[merged[c]] = True
    
    numbered_dealers = []
    for i, name in enumerate(sorted(name_set.keys()), 1):
        numbered_dealers.append(f"{i}. {name}")
    
    return numbered_dealers, merged

def _extract_int(val):
    """Extract first integer from a string; used for numeric sorting of Plot No."""
    try:
        m = re.search(r"\d+", str(val))
        return int(m.group()) if m else float("inf")
    except:
        return float("inf")

def _url_encode_for_whatsapp(text: str) -> str:
    """Encode minimally for wa.me URL (matching your existing approach)."""
    return text.replace(" ", "%20").replace("\n", "%0A")

def format_phone_link(phone):
    cleaned = clean_number(phone)
    if len(cleaned) == 10 and cleaned.startswith('3'):
        return f"92{cleaned}"
    elif len(cleaned) == 11 and cleaned.startswith('03'):
        return f"92{cleaned[1:]}"
    elif len(cleaned) == 12 and cleaned.startswith('92'):
        return cleaned
    else:
        return cleaned

def parse_vcf_file(vcf_file):
    contacts = []
    
    try:
        content = vcf_file.getvalue()
        detected = chardet.detect(content)
        encoding = detected.get('encoding', 'utf-8')
        
        try:
            text_content = content.decode(encoding)
        except UnicodeDecodeError:
            text_content = content.decode('latin-1')
        
        vcard_texts = text_content.split('END:VCARD')
        
        for vcard_text in vcard_texts:
            if not vcard_text.strip():
                continue
                
            vcard_text = vcard_text.strip() + 'END:VCARD'
            name = ""
            phone = ""
            
            fn_match = re.search(r'FN:(.*?)(?:\n|$)', vcard_text, re.IGNORECASE)
            if fn_match:
                name = fn_match.group(1).strip()
            
            tel_match = re.search(r'TEL;CELL:(.*?)(?:\n|$)', vcard_text, re.IGNORECASE)
            if not tel_match:
                tel_match = re.search(r'TEL[^:]*:(.*?)(?:\n|$)', vcard_text, re.IGNORECASE)
            
            if tel_match:
                phone = tel_match.group(1).strip()
            
            if name or phone:
                contacts.append({
                    "Name": name,
                    "Contact1": phone,
                    "Contact2": "",
                    "Contact3": "",
                    "Email": "",
                    "Address": ""
                })
                
    except Exception as e:
        st.error(f"Error parsing VCF file: {e}")
    
    return contacts

def create_duplicates_view(df):
    if df.empty:
        return None, pd.DataFrame()
    
    required_cols = ["Sector", "Plot No", "Street No", "Plot Size"]
    for col in required_cols:
        if col not in df.columns:
            st.warning(f"Cannot check duplicates: Missing column '{col}'")
            return None, pd.DataFrame()
    
    df["GroupKey"] = df["Sector"].astype(str) + "|" + df["Plot No"].astype(str) + "|" + df["Street No"].astype(str) + "|" + df["Plot Size"].astype(str)
    
    group_counts = df["GroupKey"].value_counts()
    duplicate_groups = group_counts[group_counts >= 2].index
    duplicate_df = df[df["GroupKey"].isin(duplicate_groups)]
    
    if duplicate_df.empty:
        return None, duplicate_df
    
    duplicate_df = duplicate_df.sort_values(by="GroupKey")
    
    unique_groups = duplicate_df["GroupKey"].unique()
    color_map = {}
    colors = ["#FFCCCC", "#CCFFCC", "#CCCCFF", "#FFFFCC", "#FFCCFF", "#CCFFFF", "#FFE5CC", "#E5CCFF"]
    
    for i, group in enumerate(unique_groups):
        color_map[group] = colors[i % len(colors)]
    
    def apply_row_color(row):
        return [f"background-color: {color_map[row['GroupKey']]}"] * len(row)
    
    styled_df = duplicate_df.style.apply(apply_row_color, axis=1)
    return styled_df, duplicate_df

def create_duplicates_view_updated(df):
    """Updated duplicate detection with new criteria - matching Sector, Plot No, Street No, Plot Size but different Contact/Name/Demand"""
    if df.empty:
        return None, pd.DataFrame()
    
    required_cols = ["Sector", "Plot No", "Street No", "Plot Size", 
                    "Extracted Contact", "Extracted Name", "Demand"]
    for col in required_cols:
        if col not in df.columns:
            st.warning(f"Cannot check duplicates: Missing column '{col}'")
            return None, pd.DataFrame()
    
    # Create group key based on location details only
    df["GroupKey"] = df["Sector"].astype(str) + "|" + df["Plot No"].astype(str) + "|" + df["Street No"].astype(str) + "|" + df["Plot Size"].astype(str)
    
    # Find groups with same location but different contact/name/demand
    duplicate_groups = []
    
    for group_key in df["GroupKey"].unique():
        group_df = df[df["GroupKey"] == group_key]
        if len(group_df) > 1:
            # Check if there are differences in contact, name, or demand
            contact_variation = len(group_df["Extracted Contact"].unique()) > 1
            name_variation = len(group_df["Extracted Name"].unique()) > 1
            demand_variation = len(group_df["Demand"].unique()) > 1
            
            if contact_variation or name_variation or demand_variation:
                duplicate_groups.append(group_key)
    
    duplicate_df = df[df["GroupKey"].isin(duplicate_groups)]
    
    if duplicate_df.empty:
        return None, duplicate_df
    
    duplicate_df = duplicate_df.sort_values(by=["GroupKey", "Extracted Contact", "Extracted Name", "Demand"])
    
    unique_groups = duplicate_df["GroupKey"].unique()
    color_map = {}
    colors = ["#FFCCCC", "#CCFFCC", "#CCCCFF", "#FFFFCC", "#FFCCFF", "#CCFFFF", "#FFE5CC", "#E5CCFF"]
    
    for i, group in enumerate(unique_groups):
        color_map[group] = colors[i % len(colors)]
    
    def apply_row_color(row):
        return [f"background-color: {color_map[row['GroupKey']]}"] * len(row)
    
    styled_df = duplicate_df.style.apply(apply_row_color, axis=1)
    return styled_df, duplicate_df

def sort_dataframe(df):
    """Sort dataframe by Sector, Plot No, Street No, Plot Size in ascending order"""
    if df.empty:
        return df
    
    # Create a copy to avoid modifying the original
    sorted_df = df.copy()
    
    # Extract numeric values for proper sorting
    if "Plot No" in sorted_df.columns:
        sorted_df["Plot_No_Numeric"] = sorted_df["Plot No"].apply(_extract_int)
    
    if "Street No" in sorted_df.columns:
        sorted_df["Street_No_Numeric"] = sorted_df["Street No"].apply(_extract_int)
    
    if "Plot Size" in sorted_df.columns:
        sorted_df["Plot_Size_Numeric"] = sorted_df["Plot Size"].apply(_extract_int)
    
    # Sort by the specified columns
    sort_columns = ["Sector"]
    
    # Add numeric columns for sorting if they exist
    if "Plot_No_Numeric" in sorted_df.columns:
        sort_columns.append("Plot_No_Numeric")
    if "Street_No_Numeric" in sorted_df.columns:
        sort_columns.append("Street_No_Numeric")
    if "Plot_Size_Numeric" in sorted_df.columns:
        sort_columns.append("Plot_Size_Numeric")
    
    # Add original columns as fallback
    sort_columns.extend(["Plot No", "Street No", "Plot Size"])
    
    # Remove duplicates
    sort_columns = list(dict.fromkeys(sort_columns))
    
    try:
        sorted_df = sorted_df.sort_values(by=sort_columns, ascending=True)
    except Exception as e:
        st.warning(f"Could not sort dataframe: {e}")
        return df
    
    # Drop temporary numeric columns
    sorted_df = sorted_df.drop(columns=["Plot_No_Numeric", "Street_No_Numeric", "Plot_Size_Numeric"], errors="ignore")
    
    return sorted_df

# Google Sheets Functions
@st.cache_resource(show_spinner=False)
def get_gsheet_client():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {str(e)}")
        return None

@st.cache_data(ttl=300, show_spinner="Loading plot data...")
def load_plot_data():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if not df.empty:
            df["SheetRowNum"] = [i + 2 for i in range(len(df))]
            
            # Ensure consistent data types for problematic columns
            if "Plot No" in df.columns:
                df["Plot No"] = df["Plot No"].astype(str)
            if "Street No" in df.columns:
                df["Street No"] = df["Street No"].astype(str)
            if "Plot Size" in df.columns:
                df["Plot Size"] = df["Plot Size"].astype(str)
            if "Sector" in df.columns:
                df["Sector"] = df["Sector"].astype(str)
                
        return df
    except Exception as e:
        st.error(f"Error loading plot data: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner="Loading contacts...")
def load_contacts():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if not df.empty:
            df["SheetRowNum"] = [i + 2 for i in range(len(df))]
            
            # Ensure consistent data types
            for col in df.columns:
                if df[col].dtype == "object":
                    df[col] = df[col].astype(str)
                    
        return df
    except Exception as e:
        st.error(f"Error loading contacts: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner="Loading sold data...")
def load_sold_data():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(SOLD_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=SOLD_SHEET, rows=100, cols=25)
            headers = [
                "ID", "Timestamp", "Sector", "Plot No", "Street No", "Plot Size", "Demand", 
                "Features", "Property Type", "Extracted Name", "Extracted Contact", 
                "Buyer Name", "Buyer Contact", "Sale Date", "Sale Price", "Commission",
                "Agent", "Notes", "Original Row Num"
            ]
            sheet.append_row(headers)
            return pd.DataFrame(columns=headers)
            
        df = pd.DataFrame(sheet.get_all_records())
        if not df.empty:
            df["SheetRowNum"] = [i + 2 for i in range(len(df))]
            
            # Ensure consistent data types
            if "Plot No" in df.columns:
                df["Plot No"] = df["Plot No"].astype(str)
            if "Street No" in df.columns:
                df["Street No"] = df["Street No"].astype(str)
                
        return df
    except Exception as e:
        st.error(f"Error loading sold data: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner="Loading marked sold data...")
def load_marked_sold_data():
    """Load marked sold data from Google Sheets"""
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(MARKED_SOLD_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=MARKED_SOLD_SHEET, rows=100, cols=20)
            # Add headers if sheet is newly created
            headers = [
                "ID", "Timestamp", "Sector", "Plot No", "Street No", "Plot Size", "Demand", 
                "Features", "Property Type", "Extracted Name", "Extracted Contact", 
                "Marked Sold Date", "Original Row Num"
            ]
            sheet.append_row(headers)
            return pd.DataFrame(columns=headers)
            
        df = pd.DataFrame(sheet.get_all_records())
        if not df.empty:
            df["SheetRowNum"] = [i + 2 for i in range(len(df))]
            
            # Ensure consistent data types
            if "Plot No" in df.columns:
                df["Plot No"] = df["Plot No"].astype(str)
            if "Street No" in df.columns:
                df["Street No"] = df["Street No"].astype(str)
                
        return df
    except Exception as e:
        st.error(f"Error loading marked sold data: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner="Loading leads...")
def load_leads():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(LEADS_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=LEADS_SHEET, rows=100, cols=20)
            headers = [
                "ID", "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
                "Priority", "Property Interest", "Budget", "Location Preference",
                "Last Contact", "Next Action", "Next Action Type", "Notes", 
                "Assigned To", "Lead Score", "Type", "Timeline"
            ]
            sheet.append_row(headers)
            return pd.DataFrame(columns=headers)
            
        df = pd.DataFrame(sheet.get_all_records())
        
        # Ensure consistent data types
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
                
        return df
    except Exception as e:
        st.error(f"Error loading leads: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner="Loading lead activities...")
def load_lead_activities():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(ACTIVITIES_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=ACTIVITIES_SHEET, rows=100, cols=20)
            headers = [
                "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
                "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
            ]
            sheet.append_row(headers)
            return pd.DataFrame(columns=headers)
            
        df = pd.DataFrame(sheet.get_all_records())
        
        # Ensure consistent data types
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
                
        return df
    except Exception as e:
        st.error(f"Error loading lead activities: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner="Loading tasks...")
def load_tasks():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(TASKS_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=TASKS_SHEET, rows=100, cols=20)
            headers = [
                "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
                "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
            ]
            sheet.append_row(headers)
            return pd.DataFrame(columns=headers)
            
        df = pd.DataFrame(sheet.get_all_records())
        
        # Ensure consistent data types
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
                
        return df
    except Exception as e:
        st.error(f"Error loading tasks: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner="Loading appointments...")
def load_appointments():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(APPOINTMENTS_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=APPOINTMENTS_SHEET, rows=100, cols=20)
            headers = [
                "ID", "Timestamp", "Title", "Description", "Date", "Time", 
                "Duration", "Attendees", "Location", "Status", "Related To", 
                "Related ID", "Outcome"
            ]
            sheet.append_row(headers)
            return pd.DataFrame(columns=headers)
            
        df = pd.DataFrame(sheet.get_all_records())
        
        # Ensure consistent data types
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
                
        return df
    except Exception as e:
        st.error(f"Error loading appointments: {str(e)}")
        return pd.DataFrame()

def save_leads(df):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(LEADS_SHEET)
        sheet.clear()
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        for i in range(0, len(df), BATCH_SIZE):
            batch = df.iloc[i:i+BATCH_SIZE]
            rows = []
            for _, row in batch.iterrows():
                rows.append(row.tolist())
            sheet.append_rows(rows)
            time.sleep(API_DELAY)
            
        return True
    except Exception as e:
        st.error(f"Error saving leads: {str(e)}")
        return False

def save_lead_activities(df):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(ACTIVITIES_SHEET)
        sheet.clear()
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        for i in range(0, len(df), BATCH_SIZE):
            batch = df.iloc[i:i+BATCH_SIZE]
            rows = []
            for _, row in batch.iterrows():
                rows.append(row.tolist())
            sheet.append_rows(rows)
            time.sleep(API_DELAY)
            
        return True
    except Exception as e:
        st.error(f"Error saving lead activities: {str(e)}")
        return False

def save_tasks(df):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(TASKS_SHEET)
        sheet.clear()
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        for i in range(0, len(df), BATCH_SIZE):
            batch = df.iloc[i:i+BATCH_SIZE]
            rows = []
            for _, row in batch.iterrows():
                rows.append(row.tolist())
            sheet.append_rows(rows)
            time.sleep(API_DELAY)
            
        return True
    except Exception as e:
        st.error(f"Error saving tasks: {str(e)}")
        return False

def save_appointments(df):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(APPOINTMENTS_SHEET)
        sheet.clear()
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        for i in range(0, len(df), BATCH_SIZE):
            batch = df.iloc[i:i+BATCH_SIZE]
            rows = []
            for _, row in batch.iterrows():
                rows.append(row.tolist())
            sheet.append_rows(rows)
            time.sleep(API_DELAY)
            
        return True
    except Exception as e:
        st.error(f"Error saving appointments: {str(e)}")
        return False

def save_sold_data(df):
    """Save sold data to Google Sheets"""
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(SOLD_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=SOLD_SHEET, rows=100, cols=25)
            headers = [
                "ID", "Timestamp", "Sector", "Plot No", "Street No", "Plot Size", "Demand", 
                "Features", "Property Type", "Extracted Name", "Extracted Contact", 
                "Buyer Name", "Buyer Contact", "Sale Date", "Sale Price", "Commission",
                "Agent", "Notes", "Original Row Num"
            ]
            sheet.append_row(headers)
        
        sheet.clear()
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        for i in range(0, len(df), BATCH_SIZE):
            batch = df.iloc[i:i+BATCH_SIZE]
            rows = []
            for _, row in batch.iterrows():
                rows.append(row.tolist())
            sheet.append_rows(rows)
            time.sleep(API_DELAY)
            
        st.cache_data.clear()  # Clear cache to refresh data
        return True
    except Exception as e:
        st.error(f"Error saving sold data: {str(e)}")
        return False

def save_marked_sold_data(df):
    """Save marked sold data to Google Sheets"""
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(MARKED_SOLD_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=MARKED_SOLD_SHEET, rows=100, cols=20)
            headers = [
                "ID", "Timestamp", "Sector", "Plot No", "Street No", "Plot Size", "Demand", 
                "Features", "Property Type", "Extracted Name", "Extracted Contact", 
                "Marked Sold Date", "Original Row Num"
            ]
            sheet.append_row(headers)
        
        sheet.clear()
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        for i in range(0, len(df), BATCH_SIZE):
            batch = df.iloc[i:i+BATCH_SIZE]
            rows = []
            for _, row in batch.iterrows():
                rows.append(row.tolist())
            sheet.append_rows(rows)
            time.sleep(API_DELAY)
            
        st.cache_data.clear()  # Clear cache to refresh data
        return True
    except Exception as e:
        st.error(f"Error saving marked sold data: {str(e)}")
        return False

def update_plot_data(updated_row):
    """Update a specific plot row in Google Sheets"""
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        
        # Get all data to find the row
        all_data = sheet.get_all_records()
        row_num = updated_row.get("SheetRowNum")
        
        if row_num and row_num >= 2:
            # Update the specific row
            row_values = []
            headers = sheet.row_values(1)
            
            for header in headers:
                row_values.append(updated_row.get(header, ""))
            
            sheet.update(f"A{row_num}:{chr(64 + len(headers))}{row_num}", [row_values])
            st.cache_data.clear()  # Clear cache to refresh data
            return True
        else:
            st.error("Invalid row number for update")
            return False
            
    except Exception as e:
        st.error(f"Error updating plot data: {str(e)}")
        return False

def add_contact_to_sheet(contact_data):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        sheet.append_row(contact_data)
        time.sleep(API_DELAY)
        return True
    except Exception as e:
        st.error(f"Error adding contact: {str(e)}")
        return False

def add_contacts_batch(contacts_batch):
    try:
        client = get_gsheet_client()
        if not client:
            return 0
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        success_count = 0
        
        for contact in contacts_batch:
            try:
                sheet.append_row(contact)
                success_count += 1
                time.sleep(API_DELAY)
            except HttpError as e:
                if e.resp.status == 429:
                    st.warning("Google Sheets API quota exceeded. Waiting before retrying...")
                    time.sleep(10)
                    try:
                        sheet.append_row(contact)
                        success_count += 1
                        time.sleep(API_DELAY)
                    except:
                        continue
                else:
                    continue
            except Exception:
                continue
                
        return success_count
    except Exception as e:
        st.error(f"Error in batch operation: {str(e)}")
        return 0

# SIMPLIFIED DELETE FUNCTIONS - FIXED
def delete_contacts_from_sheet(row_numbers):
    """Delete rows from Contacts sheet"""
    try:
        client = get_gsheet_client()
        if not client:
            st.error("❌ Failed to connect to Google Sheets")
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        
        # Delete rows in reverse order to avoid index shifting
        for row_num in sorted(row_numbers, reverse=True):
            try:
                sheet.delete_rows(row_num)
                time.sleep(API_DELAY)
            except Exception as e:
                st.error(f"❌ Error deleting row {row_num}: {str(e)}")
                continue
        
        # Clear cache to refresh data
        st.cache_data.clear()
        return True
        
    except Exception as e:
        st.error(f"❌ Error in delete operation: {str(e)}")
        return False

def delete_rows_from_sheet(row_numbers):
    """Delete rows from Plots sheet - SIMPLIFIED AND FIXED"""
    try:
        client = get_gsheet_client()
        if not client:
            st.error("❌ Failed to connect to Google Sheets")
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        
        # Delete rows in reverse order to avoid index shifting issues
        for row_num in sorted(row_numbers, reverse=True):
            try:
                sheet.delete_rows(row_num)
                time.sleep(API_DELAY)  # Small delay to avoid API limits
            except Exception as e:
                st.error(f"❌ Error deleting row {row_num}: {str(e)}")
                continue
        
        # Clear cache to refresh data
        st.cache_data.clear()
        return True
        
    except Exception as e:
        st.error(f"❌ Error in delete operation: {str(e)}")
        return False

# WhatsApp message generation with I-15 Street No sorting fix
def generate_whatsapp_messages(df):
    if df.empty:
        return []
        
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

    seen = set()
    unique = []
    for row in filtered:
        key = (row["Sector"], row["Plot No"], row["Plot Size"], row["Demand"])
        if key not in seen:
            seen.add(key)
            unique.append(row)

    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    blocks = []
    for (sector, size), listings in grouped.items():
        # FIX: Sort I-15 sectors by Street No, others by Plot No
        if sector.startswith("I-15"):
            # Sort by Street No ascending for I-15 sectors
            listings = sorted(
                listings,
                key=lambda x: (_extract_int(x["Street No"]), str(x["Street No"]))
            )
        else:
            # Sort by Plot No ascending for other sectors
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

    # Combine all blocks into a single message
    full_message = "\n".join(blocks)
    
    # Split if too long (WhatsApp limit ~4096 chars)
    if len(full_message) > 4000:
        # Simple split by blocks if too long
        messages = []
        current_message = ""
        for block in blocks:
            if len(current_message + block) > 4000:
                if current_message:
                    messages.append(current_message.strip())
                current_message = block
            else:
                current_message += block
        if current_message:
            messages.append(current_message.strip())
        return messages
    else:
        return [full_message]

# Lead Management Utilities
def generate_lead_id():
    return f"L{int(datetime.now().timestamp())}"

def generate_activity_id():
    return f"A{int(datetime.now().timestamp())}"

def generate_task_id():
    return f"T{int(datetime.now().timestamp())}"

def generate_appointment_id():
    return f"AP{int(datetime.now().timestamp())}"

def generate_sold_id():
    return f"S{int(datetime.now().timestamp())}"

def calculate_lead_score(lead_data, activities_df):
    score = 0
    
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
    
    priority_scores = {
        Priority.LOW.value: 5, 
        Priority.MEDIUM.value: 10, 
        Priority.HIGH.value: 20
    }
    score += priority_scores.get(lead_data.get("Priority", "Low"), 5)
    
    lead_activities = activities_df[activities_df["Lead ID"] == lead_data.get("ID", "")]
    score += min(len(lead_activities) * 5, 30)
    
    if lead_data.get("Budget") and str(lead_data.get("Budget")).isdigit():
        budget = int(lead_data.get("Budget"))
        if budget > 5000000:
            score += 20
        elif budget > 2000000:
            score += 10
    
    return min(score, 100)

def display_lead_timeline(lead_id, lead_name, lead_phone, activities_df):
    st.subheader(f"📋 Timeline for: {lead_name}")
    
    if activities_df.empty or "Lead ID" not in activities_df.columns:
        st.info("No activities recorded for this lead yet.")
        return
    
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

def display_lead_analytics(leads_df, activities_df):
    st.subheader("📊 Lead Analytics")
    
    if leads_df.empty:
        st.info("No leads data available for analytics.")
        return
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
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

def fuzzy_feature_match(row_features, selected_features):
    """Fuzzy match features with safety checks"""
    if not selected_features:
        return True
    
    row_features_str = str(row_features or "")
    row_features_list = [f.strip().lower() for f in row_features_str.split(",") if f.strip()]
    
    for sel in selected_features:
        if not sel:
            continue
        sel_lower = sel.strip().lower()
        # Exact match first
        if sel_lower in row_features_list:
            return True
        # Fuzzy match
        match = difflib.get_close_matches(sel_lower, row_features_list, n=1, cutoff=0.7)
        if match:
            return True
    return False

def update_plot_data(updated_row):
    """Update a specific plot row in Google Sheets"""
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        
        # Get all data to find the row
        all_data = sheet.get_all_records()
        row_num = updated_row.get("SheetRowNum")
        
        if row_num and row_num >= 2:
            # Update the specific row
            row_values = []
            headers = sheet.row_values(1)
            
            for header in headers:
                row_values.append(updated_row.get(header, ""))
            
            sheet.update(f"A{row_num}:{chr(64 + len(headers))}{row_num}", [row_values])
            st.cache_data.clear()  # Clear cache to refresh data
            return True
        else:
            st.error("Invalid row number for update")
            return False
            
    except Exception as e:
        st.error(f"Error updating plot data: {str(e)}")
        return False

def save_sold_data(df):
    """Save sold data to Google Sheets"""
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(SOLD_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=SOLD_SHEET, rows=100, cols=25)
            headers = [
                "ID", "Timestamp", "Sector", "Plot No", "Street No", "Plot Size", "Demand", 
                "Features", "Property Type", "Extracted Name", "Extracted Contact", 
                "Buyer Name", "Buyer Contact", "Sale Date", "Sale Price", "Commission",
                "Agent", "Notes", "Original Row Num"
            ]
            sheet.append_row(headers)
        
        sheet.clear()
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        for i in range(0, len(df), BATCH_SIZE):
            batch = df.iloc[i:i+BATCH_SIZE]
            rows = []
            for _, row in batch.iterrows():
                rows.append(row.tolist())
            sheet.append_rows(rows)
            time.sleep(API_DELAY)
            
        st.cache_data.clear()  # Clear cache to refresh data
        return True
    except Exception as e:
        st.error(f"Error saving sold data: {str(e)}")
        return False

def generate_sold_id():
    """Generate unique ID for sold listings"""
    return f"S{int(datetime.now().timestamp())}"
