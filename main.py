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
import chardet  # For encoding detection
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
BATCH_SIZE = 10  # Reduced batch size for Google Sheets API limits
API_DELAY = 1  # Delay between API calls in seconds

# Enums for Lead Management
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

# Streamlit setup
st.set_page_config(page_title="Al-Jazeera Real Estate Tool", layout="wide")
# --- Helpers ---
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
    try:
        df = df.copy()
        df = df.drop(columns=["ParsedDate", "ParsedPrice"], errors="ignore")
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
        return df
    except Exception as e:
        st.error(f"⚠️ Error displaying table: {e}")
        return pd.DataFrame()

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
    
    # Create a list of dealer names with serial numbers
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
    # Keep same encoding style you used, so links behave consistently
    return text.replace(" ", "%20").replace("\n", "%0A")

def _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800):
    """
    Given a list of text blocks, accumulate them into chunks that
    satisfy both plain text and encoded URL length limits.
    """
    chunks = []
    current = ""

    for block in blocks:
        candidate = current + block
        # Check both plain and encoded limits
        if len(candidate) > plain_limit or len(_url_encode_for_whatsapp(candidate)) > encoded_limit:
            if current:
                chunks.append(current.rstrip())
                current = ""

            # If single block is still too large, split by lines
            if len(block) > plain_limit or len(_url_encode_for_whatsapp(block)) > encoded_limit:
                lines = block.splitlines(keepends=True)
                small = ""
                for ln in lines:
                    cand2 = small + ln
                    if len(cand2) > plain_limit or len(_url_encode_for_whatsapp(cand2)) > encoded_limit:
                        if small:
                            chunks.append(small.rstrip())
                            small = ""
                        # handle very long single line (rare): hard split
                        if len(ln) > plain_limit or len(_url_encode_for_whatsapp(ln)) > encoded_limit:
                            # split the line at safe slice points
                            seg = ln
                            while seg:
                                # pick a safe slice size
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
        # Read the file content
        content = vcf_file.getvalue()
        
        # Try to detect encoding
        detected = chardet.detect(content)
        encoding = detected.get('encoding', 'utf-8')
        
        # Try to decode with detected encoding, fallback to latin-1 if needed
        try:
            text_content = content.decode(encoding)
        except UnicodeDecodeError:
            text_content = content.decode('latin-1')
        
        # Split into individual vCards
        vcard_texts = text_content.split('END:VCARD')
        
        for vcard_text in vcard_texts:
            if not vcard_text.strip():
                continue
                
            # Add the END:VCARD back for parsing
            vcard_text = vcard_text.strip() + 'END:VCARD'
            
            # Parse individual fields
            name = ""
            phone = ""
            
            # Extract FN field (Full Name)
            fn_match = re.search(r'FN:(.*?)(?:\n|$)', vcard_text, re.IGNORECASE)
            if fn_match:
                name = fn_match.group(1).strip()
            
            # Extract TEL;CELL field (Phone Number)
            tel_match = re.search(r'TEL;CELL:(.*?)(?:\n|$)', vcard_text, re.IGNORECASE)
            if not tel_match:
                # Fallback to any TEL field
                tel_match = re.search(r'TEL[^:]*:(.*?)(?:\n|$)', vcard_text, re.IGNORECASE)
            
            if tel_match:
                phone = tel_match.group(1).strip()
            
            # Only add if we have at least a name or phone
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
    
    # Check if required columns exist
    required_cols = ["Sector", "Plot No", "Street No", "Plot Size"]
    for col in required_cols:
        if col not in df.columns:
            st.warning(f"Cannot check duplicates: Missing column '{col}'")
            return None, pd.DataFrame()
    
    # FIXED: Changed .ast() to .astype() in the line below
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
# Google Sheets
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
            df["SheetRowNum"] = [i + 2 for i in range(len(df))]  # Start from row 2
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
        return df
    except Exception as e:
        st.error(f"Error loading contacts: {str(e)}")
        return pd.DataFrame()

# Lead Management Data Functions
@st.cache_data(ttl=300, show_spinner="Loading leads...")
def load_leads():
    try:
        client = get_gsheet_client()
        if not client:
            return pd.DataFrame()
            
        # Check if leads sheet exists, create if not
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(LEADS_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            # Create the sheet with headers
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
            
        # Check if activities sheet exists, create if not
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(ACTIVITIES_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            # Create the sheet with headers
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=ACTIVITIES_SHEET, rows=100, cols=20)
            headers = [
                "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
                "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
            ]
            sheet.append_row(headers)
            return pd.DataFrame(columns=headers)
            
        df = pd.DataFrame(sheet.get_all_records())
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
            
        # Check if tasks sheet exists, create if not
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(TASKS_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            # Create the sheet with headers
            spreadsheet = client.open(SPREADSHEET_NAME)
            sheet = spreadsheet.add_worksheet(title=TASKS_SHEET, rows=100, cols=20)
            headers = [
                "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
                "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
            ]
            sheet.append_row(headers)
            return pd.DataFrame(columns=headers)
            
        df = pd.DataFrame(sheet.get_all_records())
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
            
        # Check if appointments sheet exists, create if not
        try:
            sheet = client.open(SPREADSHEET_NAME).worksheet(APPOINTMENTS_SHEET)
        except gspread.exceptions.WorksheetNotFound:
            # Create the sheet with headers
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
        
        # Add headers
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        # Add data in batches
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
        
        # Add headers
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        # Add data in batches
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
        
        # Add headers
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        # Add data in batches
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
        
        # Add headers
        headers = df.columns.tolist()
        sheet.append_row(headers)
        
        # Add data in batches
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

def add_contact_to_sheet(contact_data):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        sheet.append_row(contact_data)
        time.sleep(API_DELAY)  # Rate limiting
        return True
    except Exception as e:
        st.error(f"Error adding contact: {str(e)}")
        return False

def add_contacts_batch(contacts_batch):
    """Add multiple contacts in a batch to respect API limits"""
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
                time.sleep(API_DELAY)  # Rate limiting
            except HttpError as e:
                if e.resp.status == 429:
                    st.warning("Google Sheets API quota exceeded. Waiting before retrying...")
                    time.sleep(10)  # Wait longer if we hit quota limits
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

def delete_contacts_from_sheet(row_numbers):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        
        valid_rows = [row_num for row_num in row_numbers if row_num > 1]
        if not valid_rows:
            return True
            
        valid_rows.sort(reverse=True)
        
        for i in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[i:i+BATCH_SIZE]
            for row_num in batch:
                try:
                    sheet.delete_rows(row_num)
                    time.sleep(API_DELAY)  # Rate limiting
                except HttpError as e:
                    if e.resp.status == 429:
                        st.warning("Google Sheets API quota exceeded. Waiting before retrying...")
                        time.sleep(10)  # Wait longer if we hit quota limits
                        try:
                            sheet.delete_rows(row_num)
                        except:
                            continue
                    else:
                        st.error(f"Error deleting row {row_num}: {str(e)}")
                        continue
                except Exception as e:
                    st.error(f"Error deleting row {row_num}: {str(e)}")
                    continue
                    
            time.sleep(API_DELAY)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error in delete operation: {str(e)}")
        return False

def delete_rows_from_sheet(row_numbers):
    try:
        client = get_gsheet_client()
        if not client:
            return False
            
        sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        
        valid_rows = [row_num for row_num in row_numbers if row_num > 1]
        if not valid_rows:
            return True
            
        valid_rows.sort(reverse=True)
        
        for i in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[i:i+BATCH_SIZE]
            for row_num in batch:
                try:
                    sheet.delete_rows(row_num)
                    time.sleep(API_DELAY)  # Rate limiting
                except HttpError as e:
                    if e.resp.status == 429:
                        st.warning("Google Sheets API quota exceeded. Waiting before retrying...")
                        time.sleep(10)  # Wait longer if we hit quota limits
                        try:
                            sheet.delete_rows(row_num)
                        except:
                            continue
                    else:
                        st.error(f"Error deleting row {row_num}: {str(e)}")
                        continue
                except Exception as e:
                    st.error(f"Error deleting row {row_num}: {str(e)}")
                    continue
                    
            time.sleep(API_DELAY)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error in delete operation: {str(e)}")
        return False
# WhatsApp message generation (sorted by Plot No asc, URL-safe chunking)
def generate_whatsapp_messages(df):
    if df.empty:
        return []
        
    # Build list of eligible rows (keep your intentional filters)
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

    # De-duplicate on (Sector, Plot No, Plot Size, Demand)
    seen = set()
    unique = []
    for row in filtered:
        key = (row["Sector"], row["Plot No"], row["Plot Size"], row["Demand"])
        if key not in seen:
            seen.add(key)
            unique.append(row)

    # Group by (Sector, Plot Size) as before
    grouped = {}
    for row in unique:
        key = (row["Sector"], row["Plot Size"])
        grouped.setdefault(key, []).append(row)

    # Build per-group message blocks with sorting by Plot No ascending
    blocks = []
    for (sector, size), listings in grouped.items():
        # Sort primarily by Plot No ascending (numeric-first)
        listings = sorted(
            listings,
            key=lambda x: (_extract_int(x["Plot No"]), str(x["Plot No"]))
        )

        lines = []
        for r in listings:
            if sector.startswith("I-15/"):
                # Keep your I-15 line format but ordering still by Plot No due to sort above
                lines.append(f"St: {r['Street No']} | P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")
            else:
                lines.append(f"P: {r['Plot No']} | S: {r['Plot Size']} | D: {r['Demand']}")

        header = f"*Available Options in {sector} Size: {size}*\n"
        block = header + "\n".join(lines) + "\n\n"
        blocks.append(block)

    # Split into URL-safe chunks
    # Conservative caps: plain <= 3000 chars, encoded <= 1800 chars
    messages = _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800)

    return messages

# Lead Management Utilities
def generate_lead_id():
    return f"L{int(datetime.now().timestamp())}"

def generate_activity_id():
    return f"A{int(datetime.now().timestamp())}"

def generate_task_id():
    return f"T{int(datetime.now().timestamp())}"

def generate_appointment_id():
    return f"AP{int(datetime.now().timestamp())}"

def calculate_lead_score(lead_data, activities_df):
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

def display_lead_timeline(lead_id, lead_name, lead_phone, activities_df):
    """Display timeline of activities for a lead"""
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
# --- Streamlit App ---
def main():
    st.title("🏡 Al-Jazeera Real Estate Tool")
    
    # Initialize session state for tab management
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Plots"
    if "selected_contact" not in st.session_state:
        st.session_state.selected_contact = None
    
    # Create tabs
    tabs = st.tabs(["Plots", "Contacts", "Leads Management"])
    
    # Load data
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()
    leads_df = load_leads()
    activities_df = load_lead_activities()
    tasks_df = load_tasks()
    appointments_df = load_appointments()
    
    # Add row numbers to contacts for deletion
    if not contacts_df.empty:
        contacts_df["SheetRowNum"] = [i + 2 for i in range(len(contacts_df))]
    
    # Tab 1: Plots
    with tabs[0]:
        all_features = get_all_unique_features(df)
        
        with st.sidebar:
            st.header("🔍 Filters")
            sector_filter = st.text_input("Sector")
            plot_size_filter = st.text_input("Plot Size")
            street_filter = st.text_input("Street No")
            plot_no_filter = st.text_input("Plot No")
            contact_filter = st.text_input("Phone Number (03xxxxxxxxx)")
            price_from = st.number_input("Price From (in Lacs)", min_value=0.0, value=0.0, step=1.0)
            price_to = st.number_input("Price To (in Lacs)", min_value=0.0, value=1000.0, step=1.0)
            selected_features = st.multiselect("Select Feature(s)", options=all_features)
            date_filter = st.selectbox("Date Range", ["All", "Last 7 Days", "Last 15 Days", "Last 30 Days", "Last 2 Months"])

            # Property Type filter
            prop_type_options = ["All"]
            if "Property Type" in df.columns:
                prop_type_options += sorted([str(v).strip() for v in df["Property Type"].dropna().astype(str).unique()])
            selected_prop_type = st.selectbox("Property Type", prop_type_options)

            dealer_names, contact_to_name = build_name_map(df)
            selected_dealer = st.selectbox("Dealer Name (by contact)", [""] + dealer_names)

            contact_names = [""] + sorted(contacts_df["Name"].dropna().unique()) if not contacts_df.empty else [""]
            
            # Pre-select contact if coming from Contacts tab
            if st.session_state.selected_contact:
                selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names, 
                                             index=contact_names.index(st.session_state.selected_contact) if st.session_state.selected_contact in contact_names else 0)
                # Reset after using
                st.session_state.selected_contact = None
            else:
                selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names)
        
        # Display dealer contact info if selected
        if selected_dealer:
            actual_name = selected_dealer.split(". ", 1)[1] if ". " in selected_dealer else selected_dealer
            
            # Find all numbers for this dealer
            dealer_numbers = []
            for contact, name in contact_to_name.items():
                if name == actual_name:
                    dealer_numbers.append(contact)
            
            if dealer_numbers:
                st.subheader(f"📞 Contact: {actual_name}")
                cols = st.columns(len(dealer_numbers))
                for i, num in enumerate(dealer_numbers):
                    formatted_num = format_phone_link(num)
                    cols[i].markdown(f'<a href="tel:{formatted_num}" style="display: inline-block; padding: 0.5rem 1rem; background-color: #25D366; color: white; text-decoration: none; border-radius: 0.5rem;">Call {num}</a>', 
                                    unsafe_allow_html=True)

        df_filtered = df.copy()

        if selected_dealer:
            actual_name = selected_dealer.split(". ", 1)[1] if ". " in selected_dealer else selected_dealer
            selected_contacts = [c for c, name in contact_to_name.items() if name == actual_name]
            df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
                lambda x: any(c in clean_number(x) for c in selected_contacts))]

        if selected_saved:
            row = contacts_df[contacts_df["Name"] == selected_saved].iloc[0] if not contacts_df.empty and not contacts_df[contacts_df["Name"] == selected_saved].empty else None
            selected_contacts = []
            if row is not None:
                for col in ["Contact1", "Contact2", "Contact3"]:
                    if col in row and pd.notna(row[col]):
                        selected_contacts.extend(extract_numbers(row[col]))
            df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
                lambda x: any(n in clean_number(x) for n in selected_contacts))]

        if sector_filter:
            df_filtered = df_filtered[df_filtered["Sector"].apply(lambda x: sector_matches(sector_filter, x))]
        if plot_size_filter:
            df_filtered = df_filtered[df_filtered["Plot Size"].str.contains(plot_size_filter, case=False, na=False)]
        
        # Enhanced Street No filter - match exact or partial matches
        if street_filter:
            street_pattern = re.compile(re.escape(street_filter), re.IGNORECASE)
            df_filtered = df_filtered[df_filtered["Street No"].apply(lambda x: bool(street_pattern.search(str(x))))]
        
        # Enhanced Plot No filter - match exact or partial matches
        if plot_no_filter:
            plot_pattern = re.compile(re.escape(plot_no_filter), re.IGNORECASE)
            df_filtered = df_filtered[df_filtered["Plot No"].apply(lambda x: bool(plot_pattern.search(str(x))))]
        
        if contact_filter:
            cnum = clean_number(contact_filter)
            df_filtered = df_filtered[df_filtered["Extracted Contact"].astype(str).apply(
                lambda x: any(cnum == clean_number(p) for p in x.split(",")))]

        # Apply Property Type filter if selected
        if "Property Type" in df_filtered.columns and selected_prop_type and selected_prop_type != "All":
            df_filtered = df_filtered[df_filtered["Property Type"].astype(str).str.strip() == selected_prop_type]

        df_filtered["ParsedPrice"] = df_filtered["Demand"].apply(parse_price)
        df_filtered = df_filtered[df_filtered["ParsedPrice"].notnull()]
        df_filtered = df_filtered[(df_filtered["ParsedPrice"] >= price_from) & (df_filtered["ParsedPrice"] <= price_to)]

        if selected_features:
            df_filtered = df_filtered[df_filtered["Features"].apply(lambda x: fuzzy_feature_match(x, selected_features))]

        df_filtered = filter_by_date(df_filtered, date_filter)

        # Move Timestamp column to the end
        if "Timestamp" in df_filtered.columns:
            cols = [col for col in df_filtered.columns if col != "Timestamp"] + ["Timestamp"]
            df_filtered = df_filtered[cols]

        st.subheader("📋 Filtered Listings")
        
        # Count WhatsApp eligible listings (same rules you had)
        whatsapp_eligible_count = 0
        for _, row in df_filtered.iterrows():
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
            whatsapp_eligible_count += 1
        
        st.info(f"📊 Total filtered listings: {len(df_filtered)} | ✅ WhatsApp eligible: {whatsapp_eligible_count}")
        
        # Row selection and deletion feature for main table
        if not df_filtered.empty:
            display_df = df_filtered.copy().reset_index(drop=True)
            display_df.insert(0, "Select", False)
            
            # Add "Select All" checkbox
            select_all = st.checkbox("Select All Rows", key="select_all_main")
            if select_all:
                display_df["Select"] = True
            
            # Configure columns for data editor
            column_config = {
                "Select": st.column_config.CheckboxColumn(required=True),
                "SheetRowNum": st.column_config.NumberColumn(disabled=True)
            }
            
            # Display editable dataframe with checkboxes
            edited_df = st.data_editor(
                display_df,
                column_config=column_config,
                hide_index=True,
                use_container_width=True,
                disabled=display_df.columns.difference(["Select"]).tolist()
            )
            
            # Get selected rows
            selected_rows = edited_df[edited_df["Select"]]
            
            if not selected_rows.empty:
                st.markdown(f"**{len(selected_rows)} row(s) selected**")
                
                # Show delete confirmation with progress bar
                if st.button("🗑️ Delete Selected Rows", type="primary", key="delete_button_main"):
                    row_nums = selected_rows["SheetRowNum"].tolist()
                    
                    # Show progress
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Delete with progress updates
                    success = delete_rows_from_sheet(row_nums)
                    
                    if success:
                        progress_bar.progress(100)
                        status_text.success(f"✅ Successfully deleted {len(selected_rows)} row(s)!")
                        # Clear cache and refresh
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        status_text.error("❌ Failed to delete some rows. Please try again.")
        else:
            st.info("No listings match your filters")
        
        st.markdown("---")
        st.subheader("👥 Duplicate Listings (Matching Sector, Plot No, Street No, Plot Size)")
        
        # Create and display grouped view with colors for duplicates
        if not df_filtered.empty:
            # Generate styled DataFrame with duplicate groups
            styled_duplicates_df, duplicates_df = create_duplicates_view(df_filtered)
            
            if duplicates_df.empty:
                st.info("No duplicate listings found")
            else:
                st.info("Showing only duplicate listings with matching Sector, Plot No, Street No and Plot Size")
                
                # Display the styled DataFrame (color-coded)
                st.dataframe(
                    styled_duplicates_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Create a copy for deletion with selection column
                duplicate_display = duplicates_df.copy().reset_index(drop=True)
                duplicate_display.insert(0, "Select", False)
                
                # Add "Select All" checkbox for duplicates
                select_all_duplicates = st.checkbox("Select All Duplicate Rows", key="select_all_duplicates")
                if select_all_duplicates:
                    duplicate_display["Select"] = True
                
                # Configure columns for data editor
                column_config = {
                    "Select": st.column_config.CheckboxColumn(required=True),
                    "SheetRowNum": st.column_config.NumberColumn(disabled=True)
                }
                
                # Display editable dataframe with checkboxes
                edited_duplicates = st.data_editor(
                    duplicate_display,
                    column_config=column_config,
                    hide_index=True,
                    use_container_width=True,
                    disabled=duplicate_display.columns.difference(["Select"]).tolist()
                )
                
                # Get selected rows
                selected_duplicates = edited_duplicates[edited_duplicates["Select"]]
                
                if not selected_duplicates.empty:
                    st.markdown(f"**{len(selected_duplicates)} duplicate row(s) selected**")
                    
                    # Show delete confirmation with progress bar
                    if st.button("🗑️ Delete Selected Duplicate Rows", type="primary", key="delete_button_duplicates"):
                        row_nums = selected_duplicates["SheetRowNum"].tolist()
                        
                        # Show progress
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # Delete with progress updates
                        success = delete_rows_from_sheet(row_nums)
                        
                        if success:
                            progress_bar.progress(100)
                            status_text.success(f"✅ Successfully deleted {len(selected_duplicates)} duplicate row(s)!")
                            # Clear cache and refresh
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            status_text.error("❌ Failed to delete some rows. Please try again.")
        else:
            st.info("No listings to analyze for duplicates")

        st.markdown("---")
        st.subheader("📤 Send WhatsApp Message")

        selected_name_whatsapp = st.selectbox("📱 Select Contact to Message", contact_names, key="wa_contact")
        manual_number = st.text_input("Or Enter WhatsApp Number (e.g. 0300xxxxxxx)")

        if st.button("Generate WhatsApp Message"):
            cleaned = ""
            if manual_number:
                cleaned = clean_number(manual_number)
            elif selected_name_whatsapp:
                contact_row = contacts_df[contacts_df["Name"] == selected_name_whatsapp].iloc[0] if not contacts_df.empty and not contacts_df[contacts_df["Name"] == selected_name_whatsapp].empty else None
                if contact_row is not None:
                    numbers = []
                    for col in ["Contact1", "Contact2", "Contact3"]:
                        if col in contact_row and pd.notna(contact_row[col]):
                            numbers.append(clean_number(contact_row[col]))
                    cleaned = numbers[0] if numbers else ""

            if not cleaned:
                st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
                st.stop()

            if len(cleaned) == 10 and cleaned.startswith("3"):
                wa_number = "92" + cleaned
            elif len(cleaned) == 11 and cleaned.startswith("03"):
                wa_number = "92" + cleaned[1:]
            elif len(cleaned) == 12 and cleaned.startswith("92"):
                wa_number = cleaned
            else:
                st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
                st.stop()

            # Use the same filtered dataframe as the main table with intentional filters
            messages = generate_whatsapp_messages(df_filtered)
            if not messages:
                st.warning("⚠️ No valid listings to include. Listings must have: Sector, Plot No, Size, Price; I-15 must have Street No; No 'series' plots.")
            else:
                st.success(f"📨 Generated {len(messages)} WhatsApp message(s)")
                
                # Show message previews and safe links
                for i, msg in enumerate(messages):
                    st.markdown(f"**Message {i+1}** ({len(msg)} characters):")
                    st.text_area(f"Preview Message {i+1}", msg, height=150, key=f"msg_preview_{i}")
                    
                    encoded = msg.replace(" ", "%20").replace("\n", "%0A")
                    link = f"https://wa.me/{wa_number}?text={encoded}"
                    st.markdown(f"[📩 Send Message {i+1}]({link})", unsafe_allow_html=True)
                    st.markdown("---")
    
    # Tab 2: Contacts
    with tabs[1]:
        st.header("📇 Contact Management")
        
        # Add new contact form
        with st.form("add_contact_form"):
            st.subheader("Add New Contact")
            col1, col2 = st.columns(2)
            name = col1.text_input("Name*", key="contact_name")
            contact1 = col1.text_input("Contact 1*", key="contact_1")
            contact2 = col2.text_input("Contact 2", key="contact_2")
            contact3 = col2.text_input("Contact 3", key="contact_3")
            email = col1.text_input("Email", key="contact_email")
            address = col2.text_input("Address", key="contact_address")
            
            submitted = st.form_submit_button("Add Contact")
            
            if submitted:
                if not name or not contact1:
                    st.error("Name and Contact 1 are required fields!")
                else:
                    contact_data = [name, contact1, contact2 or "", contact3 or "", email or "", address or ""]
                    if add_contact_to_sheet(contact_data):
                        st.success("Contact added successfully!")
                        # Clear cache to reload contacts
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Failed to add contact. Please try again.")
        
        st.markdown("---")
        
        # Import contacts from VCF
        st.subheader("Import Contacts from VCF")
        vcf_file = st.file_uploader("Upload VCF file", type=["vcf"], key="vcf_uploader")
        
        if vcf_file is not None:
            contacts = parse_vcf_file(vcf_file)
            if contacts:
                st.success(f"Found {len(contacts)} contacts in the VCF file")
                
                # Display contacts for review
                for i, contact in enumerate(contacts):
                    with st.expander(f"Contact {i+1}: {contact['Name']}"):
                        st.write(f"**Name:** {contact['Name']}")
                        st.write(f"**Contact 1:** {contact['Contact1']}")
                        st.write(f"**Contact 2:** {contact['Contact2']}")
                        st.write(f"**Contact 3:** {contact['Contact3']}")
                        st.write(f"**Email:** {contact['Email']}")
                
                # Button to import all contacts
                if st.button("Import All Contacts", key="import_all"):
                    success_count = 0
                    total_contacts = len(contacts)
                    
                    # Create progress bar and status
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Process in batches to respect API limits
                    for i in range(0, total_contacts, BATCH_SIZE):
                        batch = contacts[i:i+BATCH_SIZE]
                        batch_success = 0
                        
                        for contact in batch:
                            contact_data = [
                                contact["Name"],
                                contact["Contact1"],
                                contact["Contact2"],
                                contact["Contact3"],
                                contact["Email"],
                                contact["Address"]
                            ]
                            if add_contact_to_sheet(contact_data):
                                batch_success += 1
                                success_count += 1
                        
                        # Update progress
                        progress = min((i + len(batch)) / total_contacts, 1.0)
                        progress_bar.progress(progress)
                        status_text.text(f"Processed {i + len(batch)}/{total_contacts} contacts...")
                        
                        # Small delay between batches
                        time.sleep(API_DELAY)
                    
                    # Final status update
                    progress_bar.progress(1.0)
                    if success_count == total_contacts:
                        status_text.success(f"✅ Successfully imported all {success_count} contacts!")
                    else:
                        status_text.warning(f"⚠️ Imported {success_count} out of {total_contacts} contacts. Some may have failed due to API limits.")
                    
                    # Clear cache and refresh
                    st.cache_data.clear()
                    st.rerun()
        
        st.markdown("---")
        st.subheader("Saved Contacts")
        
        # Display existing contacts with selection for deletion
        if not contacts_df.empty:
            # Create a copy for editing
            contacts_display = contacts_df.copy().reset_index(drop=True)
            contacts_display.insert(0, "Select", False)
            
            # Add "Select All" checkbox
            select_all_contacts = st.checkbox("Select All Contacts", key="select_all_contacts")
            if select_all_contacts:
                contacts_display["Select"] = True
            
            # Configure columns for data editor
            column_config = {
                "Select": st.column_config.CheckboxColumn(required=True),
                "SheetRowNum": st.column_config.NumberColumn(disabled=True)
            }
            
            # Display editable dataframe with checkboxes
            edited_contacts = st.data_editor(
                contacts_display,
                column_config=column_config,
                hide_index=True,
                use_container_width=True,
                disabled=contacts_display.columns.difference(["Select"]).tolist()
            )
            
            # Get selected contacts
            selected_contacts = edited_contacts[edited_contacts["Select"]]
            
            if not selected_contacts.empty:
                st.markdown(f"**{len(selected_contacts)} contact(s) selected**")
                
                # Show delete confirmation
                if st.button("🗑️ Delete Selected Contacts", type="primary", key="delete_contacts"):
                    row_nums = selected_contacts["SheetRowNum"].tolist()
                    
                    # Show progress
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Delete with progress updates
                    success = delete_contacts_from_sheet(row_nums)
                    
                    if success:
                        progress_bar.progress(100)
                        status_text.success(f"✅ Successfully deleted {len(selected_contacts)} contact(s)!")
                        # Clear cache and refresh
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        status_text.error("❌ Failed to delete some contacts. Please try again.")
            
            # Display individual contacts with "Show Shared Listings" button
            for idx, row in contacts_df.iterrows():
                with st.expander(f"{row['Name']} - {row.get('Contact1', '')}"):
                    col1, col2 = st.columns(2)
                    col1.write(f"**Contact 1:** {row.get('Contact1', '')}")
                    col1.write(f"**Contact 2:** {row.get('Contact2', '')}")
                    col1.write(f"**Contact 3:** {row.get('Contact3', '')}")
                    col2.write(f"**Email:** {row.get('Email', '')}")
                    col2.write(f"**Address:** {row.get('Address', '')}")
                    
                    # Button to show shared listings
                    if st.button("Show Shared Listings", key=f"show_listings_{idx}"):
                        # Set the contact filter in session state and switch to Plots tab
                        st.session_state.selected_contact = row['Name']
                        st.session_state.active_tab = "Plots"
                        st.rerun()
        else:
            st.info("No contacts found. Add a new contact using the form above.")
    # Tab 3: Leads Management (Fixed version)
    with tabs[2]:
        st.header("👥 Lead Management CRM")
        
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
        
        with lead_tabs[1]:
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
        
        with lead_tabs[2]:
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
        
        with lead_tabs[3]:
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
        
        with lead_tabs[4]:
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
        
        with lead_tabs[5]:
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
        
        with lead_tabs[6]:
            display_lead_analytics(leads_df, activities_df)

if __name__ == "__main__":
    main()
