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

# Constants
SPREADSHEET_NAME = "Al-Jazeera"
PLOTS_SHEET = "Plots"
CONTACTS_SHEET = "Contacts"
LEADS_SHEET = "Leads"
ACTIVITIES_SHEET = "LeadActivities"
TASKS_SHEET = "Tasks"
APPOINTMENTS_SHEET = "Appointments"

# Streamlit setup
st.set_page_config(page_title="Al-Jazeera Real Estate CRM", layout="wide")# --- Helpers ---
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
        return pd.DataFrame()# Google Sheets
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def load_plot_data():
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if not df.empty:
            df["SheetRowNum"] = [i + 2 for i in range(len(df))]  # Start from row 2
        else:
            df = pd.DataFrame(columns=["SheetRowNum"])
        return df
    except Exception as e:
        st.error(f"Error loading plot data: {str(e)}")
        return pd.DataFrame(columns=["SheetRowNum"])

def load_contacts():
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(CONTACTS_SHEET)
        return pd.DataFrame(sheet.get_all_records())
    except Exception as e:
        st.error(f"Error loading contacts: {str(e)}")
        return pd.DataFrame()

def load_leads():
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(LEADS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty:
            df = pd.DataFrame(columns=[
                "ID", "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
                "Priority", "Property Interest", "Budget", "Location Preference",
                "Last Contact", "Next Action", "Next Action Type", "Notes", 
                "Assigned To", "Lead Score", "Type", "Timeline"
            ])
        return df
    except gspread.exceptions.WorksheetNotFound:
        try:
            sheet = get_gsheet_client().open(SPREADSHEET_NAME)
            worksheet = sheet.add_worksheet(title=LEADS_SHEET, rows=100, cols=19)
            worksheet.append_row([
                "ID", "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
                "Priority", "Property Interest", "Budget", "Location Preference",
                "Last Contact", "Next Action", "Next Action Type", "Notes", 
                "Assigned To", "Lead Score", "Type", "Timeline"
            ])
            return pd.DataFrame(columns=[
                "ID", "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
                "Priority", "Property Interest", "Budget", "Location Preference",
                "Last Contact", "Next Action", "Next Action Type", "Notes", 
                "Assigned To", "Lead Score", "Type", "Timeline"
            ])
        except Exception as e:
            st.error(f"Error creating leads sheet: {str(e)}")
            return pd.DataFrame(columns=[
                "ID", "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
                "Priority", "Property Interest", "Budget", "Location Preference",
                "Last Contact", "Next Action", "Next Action Type", "Notes", 
                "Assigned To", "Lead Score", "Type", "Timeline"
            ])
    except Exception as e:
        st.error(f"Error loading leads: {str(e)}")
        return pd.DataFrame(columns=[
            "ID", "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
            "Priority", "Property Interest", "Budget", "Location Preference",
            "Last Contact", "Next Action", "Next Action Type", "Notes", 
            "Assigned To", "Lead Score", "Type", "Timeline"
        ])

def load_lead_activities():
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(ACTIVITIES_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty:
            df = pd.DataFrame(columns=[
                "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
                "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
            ])
        return df
    except gspread.exceptions.WorksheetNotFound:
        try:
            sheet = get_gsheet_client().open(SPREADSHEET_NAME)
            worksheet = sheet.add_worksheet(title=ACTIVITIES_SHEET, rows=100, cols=11)
            worksheet.append_row([
                "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
                "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
            ])
            return pd.DataFrame(columns=[
                "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
                "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
            ])
        except Exception as e:
            st.error(f"Error creating activities sheet: {str(e)}")
            return pd.DataFrame(columns=[
                "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
                "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
            ])
    except Exception as e:
        st.error(f"Error loading activities: {str(e)}")
        return pd.DataFrame(columns=[
            "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
            "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
        ])

def load_tasks():
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(TASKS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty:
            df = pd.DataFrame(columns=[
                "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
                "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
            ])
        return df
    except gspread.exceptions.WorksheetNotFound:
        try:
            sheet = get_gsheet_client().open(SPREADSHEET_NAME)
            worksheet = sheet.add_worksheet(title=TASKS_SHEET, rows=100, cols=11)
            worksheet.append_row([
                "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
                "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
            ])
            return pd.DataFrame(columns=[
                "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
                "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
            ])
        except Exception as e:
            st.error(f"Error creating tasks sheet: {str(e)}")
            return pd.DataFrame(columns=[
                "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
                "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
            ])
    except Exception as e:
        st.error(f"Error loading tasks: {str(e)}")
        return pd.DataFrame(columns=[
            "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
            "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
        ])

def load_appointments():
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(APPOINTMENTS_SHEET)
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty:
            df = pd.DataFrame(columns=[
                "ID", "Timestamp", "Title", "Description", "Date", "Time", 
                "Duration", "Attendees", "Location", "Status", "Related To", 
                "Related ID", "Outcome"
            ])
        return df
    except gspread.exceptions.WorksheetNotFound:
        try:
            sheet = get_gsheet_client().open(SPREADSHEET_NAME)
            worksheet = sheet.add_worksheet(title=APPOINTMENTS_SHEET, rows=100, cols=13)
            worksheet.append_row([
                "ID", "Timestamp", "Title", "Description", "Date", "Time", 
                "Duration", "Attendees", "Location", "Status", "Related To", 
                "Related ID", "Outcome"
            ])
            return pd.DataFrame(columns=[
                "ID", "Timestamp", "Title", "Description", "Date", "Time", 
                "Duration", "Attendees", "Location", "Status", "Related To", 
                "Related ID", "Outcome"
            ])
        except Exception as e:
            st.error(f"Error creating appointments sheet: {str(e)}")
            return pd.DataFrame(columns=[
                "ID", "Timestamp", "Title", "Description", "Date", "Time", 
                "Duration", "Attendees", "Location", "Status", "Related To", 
                "Related ID", "Outcome"
            ])
    except Exception as e:
        st.error(f"Error loading appointments: {str(e)}")
        return pd.DataFrame(columns=[
            "ID", "Timestamp", "Title", "Description", "Date", "Time", 
            "Duration", "Attendees", "Location", "Status", "Related To", 
            "Related ID", "Outcome"
        ])

def save_leads(df):
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(LEADS_SHEET)
        sheet.clear()
        sheet.append_row([
            "ID", "Timestamp", "Name", "Phone", "Email", "Source", "Status", 
            "Priority", "Property Interest", "Budget", "Location Preference",
            "Last Contact", "Next Action", "Next Action Type", "Notes", 
            "Assigned To", "Lead Score", "Type", "Timeline"
        ])
        for _, row in df.iterrows():
            sheet.append_row([
                row.get("ID", ""),
                row.get("Timestamp", ""),
                row.get("Name", ""),
                row.get("Phone", ""),
                row.get("Email", ""),
                row.get("Source", ""),
                row.get("Status", ""),
                row.get("Priority", ""),
                row.get("Property Interest", ""),
                row.get("Budget", ""),
                row.get("Location Preference", ""),
                row.get("Last Contact", ""),
                row.get("Next Action", ""),
                row.get("Next Action Type", ""),
                row.get("Notes", ""),
                row.get("Assigned To", ""),
                row.get("Lead Score", ""),
                row.get("Type", ""),
                row.get("Timeline", "")
            ])
        return True
    except Exception as e:
        st.error(f"Error saving leads: {str(e)}")
        return False

def save_lead_activity(df):
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(ACTIVITIES_SHEET)
        sheet.clear()
        sheet.append_row([
            "ID", "Timestamp", "Lead ID", "Lead Name", "Lead Phone", "Activity Type", 
            "Details", "Next Steps", "Follow-up Date", "Duration", "Outcome"
        ])
        for _, row in df.iterrows():
            sheet.append_row([
                row.get("ID", ""),
                row.get("Timestamp", ""),
                row.get("Lead ID", ""),
                row.get("Lead Name", ""),
                row.get("Lead Phone", ""),
                row.get("Activity Type", ""),
                row.get("Details", ""),
                row.get("Next Steps", ""),
                row.get("Follow-up Date", ""),
                row.get("Duration", ""),
                row.get("Outcome", "")
            ])
        return True
    except Exception as e:
        st.error(f"Error saving activities: {str(e)}")
        return False

def save_tasks(df):
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(TASKS_SHEET)
        sheet.clear()
        sheet.append_row([
            "ID", "Timestamp", "Title", "Description", "Due Date", "Priority", 
            "Status", "Assigned To", "Related To", "Related ID", "Completed Date"
        ])
        for _, row in df.iterrows():
            sheet.append_row([
                row.get("ID", ""),
                row.get("Timestamp", ""),
                row.get("Title", ""),
                row.get("Description", ""),
                row.get("Due Date", ""),
                row.get("Priority", ""),
                row.get("Status", ""),
                row.get("Assigned To", ""),
                row.get("Related To", ""),
                row.get("Related ID", ""),
                row.get("Completed Date", "")
            ])
        return True
    except Exception as e:
        st.error(f"Error saving tasks: {str(e)}")
        return False

def save_appointments(df):
    try:
        sheet = get_gsheet_client().open(SPREADSHEET_NAME).worksheet(APPOINTMENTS_SHEET)
        sheet.clear()
        sheet.append_row([
            "ID", "Timestamp", "Title", "Description", "Date", "Time", 
            "Duration", "Attendees", "Location", "Status", "Related To", 
            "Related ID", "Outcome"
        ])
        for _, row in df.iterrows():
            sheet.append_row([
                row.get("ID", ""),
                row.get("Timestamp", ""),
                row.get("Title", ""),
                row.get("Description", ""),
                row.get("Date", ""),
                row.get("Time", ""),
                row.get("Duration", ""),
                row.get("Attendees", ""),
                row.get("Location", ""),
                row.get("Status", ""),
                row.get("Related To", ""),
                row.get("Related ID", ""),
                row.get("Outcome", "")
            ])
        return True
    except Exception as e:
        st.error(f"Error saving appointments: {str(e)}")
        return False

def filter_by_date(df, label):
    if label == "All":
        return df
    days_map = {"Last 7 Days": 7, "Last 15 Days": 15, "Last 30 Days": 30, "Last 2 Months": 60}
    cutoff = datetime.now() - timedelta(days=days_map.get(label, 0))
    def try_parse(val):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            return None
    df["ParsedDate"] = df["Timestamp"].apply(try_parse)
    return df[df["ParsedDate"].notna() & (df["ParsedDate"] >= cutoff)]

def build_name_map(df):
    contact_to_name = {}
    for _, row in df.iterrows():
        name = str(row.get("Extracted Name")).strip()
        contacts = extract_numbers(row.get("Extracted Contact"))
        for c in contacts:
            if c and c not in contact_to_name:
                contact_to_name[c] = name
    name_groups = {}
    for c, name in contact_to_name.items():
        name_groups.setdefault(name, set()).add(c)
    merged = {}
    for name, numbers in name_groups.items():
        for c in numbers:
            merged[c] = name
    name_set = {}
    for _, row in df.iterrows():
        numbers = extract_numbers(row.get("Extracted Contact"))
        for c in numbers:
            if c in merged:
                name_set[merged[c]] = True
    
    # Create a list of dealer names with serial numbers
    numbered_dealers = []
    for i, name in enumerate(sorted(name_set.keys()), 1):
        numbered_dealers.append(f"{i}. {name}")
    
    return numbered_dealers, merged# ---------- WhatsApp utilities (split + encode aware) ----------
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

def _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800):
    chunks = []
    current = ""

    for block in blocks:
        candidate = current + block
        if len(candidate) > plain_limit or len(_url_encode_for_whatsapp(candidate)) > encoded_limit:
            if current:
                chunks.append(current.rstrip())
                current = ""

            if len(block) > plain_limit or len(_url_encode_for_whatsapp(block)) > encoded_limit:
                lines = block.splitlines(keepends=True)
                small = ""
                for ln in lines:
                    cand2 = small + ln
                    if len(candidate) > plain_limit or len(_url_encode_for_whatsapp(candidate)) > encoded_limit:
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

# WhatsApp message generation (sorted by Plot No asc, URL-safe chunking)
def generate_whatsapp_messages(df):
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

    messages = _split_blocks_for_limits(blocks, plain_limit=3000, encoded_limit=1800)
    return messages

# Delete rows from Google Sheet
def delete_rows_from_sheet(row_numbers):
    try:
        client = get_gsheet_client()
        sheet = client.open(SPREADSHEET_NAME).worksheet(PLOTS_SHEET)
        
        valid_rows = [row_num for row_num in row_numbers if row_num > 1]
        if not valid_rows:
            return True
            
        valid_rows.sort(reverse=True)
        
        BATCH_SIZE = 10
        for i in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[i:i+BATCH_SIZE]
            for row_num in batch:
                try:
                    sheet.delete_rows(row_num)
                except Exception as e:
                    st.error(f"Error deleting row {row_num}: {str(e)}")
                    continue
                    
            import time
            time.sleep(1)
            
        return True
    except Exception as e:
        st.error(f"Error in delete operation: {str(e)}")
        return False

def create_duplicates_view(df):
    if df.empty:
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
    return styled_df, duplicate_df# --- Enhanced Lead Management Functions ---
def generate_lead_id():
    return f"L{int(datetime.now().timestamp())}"

def generate_activity_id():
    return f"A{int(datetime.now().timestamp())}"

def generate_task_id():
    return f"T{int(datetime.now().timestamp())}"

def generate_appointment_id():
    return f"AP{int(datetime.now().timestamp())}"

def calculate_lead_score(lead_data, activities_df):
    score = 0
    
    # Score based on status
    status_scores = {
        "New": 10,
        "Contacted": 20,
        "Follow-up": 30,
        "Meeting Scheduled": 50,
        "Negotiation": 70,
        "Offer Made": 80,
        "Deal Closed (Won)": 100,
        "Not Interested (Lost)": 0
    }
    score += status_scores.get(lead_data.get("Status", "New"), 10)
    
    # Score based on priority
    priority_scores = {"Low": 5, "Medium": 10, "High": 20}
    score += priority_scores.get(lead_data.get("Priority", "Low"), 5)
    
    # Score based on activities count
    lead_activities = activities_df[activities_df["Lead ID"] == lead_data.get("ID", "")]
    score += min(len(lead_activities) * 5, 30)  # Max 30 points for activities
    
    # Score based on budget (if provided)
    if lead_data.get("Budget") and str(lead_data.get("Budget")).isdigit():
        budget = int(lead_data.get("Budget"))
        if budget > 5000000:  # Above 50 lakhs
            score += 20
        elif budget > 2000000:  # Above 20 lakhs
            score += 10
    
    return min(score, 100)  # Cap at 100

def display_lead_timeline(lead_id, lead_name, lead_phone):
    st.subheader(f"📋 Timeline for: {lead_name}")
    
    activities_df = load_lead_activities()
    lead_activities = activities_df[
        (activities_df["Lead ID"] == lead_id)
    ]
    
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
                    except:
                        pass
                
                if isinstance(timestamp, datetime):
                    st.write(timestamp.strftime("%b %d, %Y"))
                    st.write(timestamp.strftime("%I:%M %p"))
                else:
                    st.write(str(timestamp))
            
            with col2:
                activity_type = activity["Activity Type"]
                
                if activity_type == "Call":
                    st.markdown(f"**📞 Phone Call**")
                    color = "#E3F2FD"
                elif activity_type == "Meeting":
                    st.markdown(f"**👥 Meeting**")
                    color = "#E8F5E9"
                elif activity_type == "Email":
                    st.markdown(f"**📧 Email**")
                    color = "#FFF3E0"
                elif activity_type == "WhatsApp":
                    st.markdown(f"**💬 WhatsApp**")
                    color = "#E8F5E9"
                elif activity_type == "Site Visit":
                    st.markdown(f"**🏠 Site Visit**")
                    color = "#E0F2F1"
                elif activity_type == "Status Update":
                    st.markdown(f"**🔄 Status Update**")
                    color = "#F3E5F5"
                else:
                    st.markdown(f"**📝 Note**")
                    color = "#F5F5F5"
                
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
            except:
                st.info("No lead score data available.")
        else:
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
        except:
            st.info("No activities data available.")
    else:
        st.info("No activities data available.")# --- Phone number formatting for dialer ---
def format_phone_number(phone):
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

def create_dialer_link(phone):
    """Create tel: link for phone number"""
    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return ""
    
    return f"tel:{formatted_phone}"

def display_phone_with_dialer(phone):
    """Display phone number with dialer link"""
    if not phone:
        return ""
    
    dialer_link = create_dialer_link(phone)
    if dialer_link:
        return f'<a href="{dialer_link}" style="color: #1f77b4; text-decoration: none;">{phone}</a>'
    else:
        return phone

def format_contact_column(contact_str):
    """Format Extracted Contact column with dialer links for each number"""
    if not contact_str:
        return ""
    
    numbers = extract_numbers(contact_str)
    formatted_numbers = []
    
    for num in numbers:
        dialer_link = create_dialer_link(num)
        if dialer_link:
            formatted_numbers.append(f'<a href="{dialer_link}" style="color: #1f77b4; text-decoration: none;">{num}</a>')
        else:
            formatted_numbers.append(num)
    
    return ", ".join(formatted_numbers)def leads_page():
    st.header("👥 Lead Management CRM")
    
    # Load data
    leads_df = load_leads()
    activities_df = load_lead_activities()
    tasks_df = load_tasks()
    appointments_df = load_appointments()
    
    # Calculate metrics for dashboard
    total_leads = len(leads_df)
    
    status_counts = leads_df["Status"].value_counts() if "Status" in leads_df.columns else pd.Series()
    new_leads = status_counts.get("New", 0)
    contacted_leads = status_counts.get("Contacted", 0) + status_counts.get("Follow-up", 0)
    negotiation_leads = status_counts.get("Negotiation", 0) + status_counts.get("Offer Made", 0)
    won_leads = status_counts.get("Deal Closed (Won)", 0)
    
    # Count overdue actions
    today = datetime.now().date()
    overdue_tasks = 0
    if "Due Date" in tasks_df.columns and "Status" in tasks_df.columns:
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
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Dashboard", "All Leads", "Add New Lead", "Lead Timeline", 
        "Tasks", "Appointments", "Analytics"
    ])
    
    with tab1:
        st.subheader("🏠 CRM Dashboard")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Quick stats
            st.info("**Quick Stats**")
            st.write(f"📞 Total Activities: {len(activities_df)}")
            st.write(f"✅ Completed Tasks: {len(tasks_df[tasks_df['Status'] == 'Completed'])}")
            st.write(f"🔄 Active Tasks: {len(tasks_df[tasks_df['Status'] == 'In Progress'])}")
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
    
    with tab2:
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
            if status_filter != "All":
                filtered_leads = filtered_leads[filtered_leads["Status"] == status_filter]
            if priority_filter != "All":
                filtered_leads = filtered_leads[filtered_leads["Priority"] == priority_filter]
            if source_filter != "All":
                filtered_leads = filtered_leads[filtered_leads["Source"] == source_filter]
            if assigned_filter != "All":
                filtered_leads = filtered_leads[filtered_leads["Assigned To"] == assigned_filter]
            
            # Display leads table with phone numbers as clickable links
            display_df = filtered_leads.copy()
            if "Phone" in display_df.columns:
                display_df["Phone"] = display_df["Phone"].apply(lambda x: display_phone_with_dialer(x) if pd.notna(x) else "")
            
            st.markdown(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)
            
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
                                        last_contact_date = datetime.strptime(lead_data.get("Last Contact"), "%Y-%m-%d").date()
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
                            
                            if st.form_submit_button("Update Lead"):
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
                                        st.rerun()
                                    else:
                                        st.error("Failed to update lead. Please try again.")
                                else:
                                    st.error("Lead not found in database. Please try again.")
    
    with tab3:
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
            
            if st.form_submit_button("Add Lead"):
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
                        if save_lead_activity(activities_df):
                            st.success("Lead added successfully!")
                            st.rerun()
                        else:
                            st.error("Lead added but failed to create activity. Please check activities sheet.")
                    else:
                        st.error("Failed to add lead. Please try again.")
    
    with tab4:
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
                    
                    # Display timeline
                    display_lead_timeline(lead_id, lead_name, lead_phone)
                    
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
                        
                        if st.form_submit_button("Add Activity"):
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
                                if save_lead_activity(activities_df):
                                    # Update last contact date in leads sheet
                                    idx = leads_df[leads_df["ID"] == lead_id].index
                                    if len(idx) > 0:
                                        idx = idx[0]
                                        leads_df.at[idx, "Last Contact"] = datetime.now().strftime("%Y-%m-%d")
                                        
                                        # Update lead score
                                        leads_df.at[idx, "Lead Score"] = calculate_lead_score(leads_df.iloc[idx], activities_df)
                                        
                                        if save_leads(leads_df):
                                            st.success("Activity added successfully!")
                                            st.rerun()
                                        else:
                                            st.error("Activity added but failed to update lead. Please check leads sheet.")
                                    else:
                                        st.error("Lead not found in database. Please try again.")
                                else:
                                    st.error("Failed to add activity. Please try again.")
    
    with tab5:
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
                
                if st.form_submit_button("Add Task"):
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
            if task_status_filter != "All":
                filtered_tasks = filtered_tasks[filtered_tasks["Status"] == task_status_filter]
            
            if filtered_tasks.empty:
                st.info("No tasks found.")
            else:
                for _, task in filtered_tasks.iterrows():
                    with st.expander(f"{task['Title']} - {task['Status']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Due Date:** {task['Due Date']}")
                            st.write(f"**Priority:** {task['Priority']}")
                            st.write(f"**Assigned To:** {task['Assigned To']}")
                        with col2:
                            st.write(f"**Related To:** {task['Related To']}")
                            st.write(f"**Status:** {task['Status']}")
                            if task['Status'] == "Completed" and task['Completed Date']:
                                st.write(f"**Completed On:** {task['Completed Date']}")
                        
                        st.write(f"**Description:** {task['Description']}")
                        
                        # Update task status
                        new_status = st.selectbox("Update Status", 
                                                options=["Not Started", "In Progress", "Completed"],
                                                index=["Not Started", "In Progress", "Completed"].index(task['Status']),
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
                                    st.rerun()
                                else:
                                    st.error("Failed to update task. Please try again.")
                            else:
                                st.error("Task not found in database. Please try again.")
    
    with tab6:
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
                    status = st.selectbox("Status", options=["Scheduled", "Confirmed", "Completed", "Cancelled"])
                    location = st.text_input("Location", placeholder="Meeting location")
                
                description = st.text_area("Description")
                attendees = st.text_input("Attendees", placeholder="Names of attendees")
                
                if st.form_submit_button("Add Appointment"):
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
            if appointment_status_filter != "All":
                filtered_appointments = filtered_appointments[filtered_appointments["Status"] == appointment_status_filter]
            
            if filtered_appointments.empty:
                st.info("No appointments found.")
            else:
                for _, appointment in filtered_appointments.iterrows():
                    with st.expander(f"{appointment['Title']} - {appointment['Status']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Date:** {appointment['Date']}")
                            st.write(f"**Time:** {appointment['Time']}")
                            st.write(f"**Duration:** {appointment['Duration']} minutes")
                            st.write(f"**Location:** {appointment['Location']}")
                        with col2:
                            st.write(f"**Related To:** {appointment['Related To']}")
                            st.write(f"**Status:** {appointment['Status']}")
                            st.write(f"**Attendees:** {appointment['Attendees']}")
                        
                        st.write(f"**Description:** {appointment['Description']}")
                        
                        # Update appointment status
                        new_status = st.selectbox("Update Status", 
                                                options=["Scheduled", "Confirmed", "Completed", "Cancelled"],
                                                index=["Scheduled", "Confirmed", "Completed", "Cancelled"].index(appointment['Status']),
                                                key=f"status_{appointment['ID']}")
                        
                        if st.button("Update", key=f"update_{appointment['ID']}"):
                            idx = appointments_df[appointments_df["ID"] == appointment['ID']].index
                            if len(idx) > 0:
                                idx = idx[0]
                                appointments_df.at[idx, "Status"] = new_status
                                if save_appointments(appointments_df):
                                    st.success("Appointment updated successfully!")
                                    st.rerun()
                                else:
                                    st.error("Failed to update appointment. Please try again.")
                            else:
                                st.error("Appointment not found in database. Please try again.")
    
    with tab7:
        display_lead_analytics(leads_df, activities_df)# --- Plots Page (Updated with direct dialing) ---
def plots_page():
    st.header("🏡 Property Listings")
    
    # Load data
    df = load_plot_data().fillna("")
    contacts_df = load_contacts()

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

        contact_names = [""] + sorted(contacts_df["Name"].dropna().unique())
        selected_saved = st.selectbox("📇 Saved Contact (by number)", contact_names)

    df_filtered = df.copy()

    if selected_dealer:
        actual_name = selected_dealer.split(". ", 1)[1] if ". " in selected_dealer else selected_dealer
        selected_contacts = [c for c, name in contact_to_name.items() if name == actual_name]
        df_filtered = df_filtered[df_filtered["Extracted Contact"].apply(
            lambda x: any(c in clean_number(x) for c in selected_contacts))]

    if selected_saved:
        row = contacts_df[contacts_df["Name"] == selected_saved].iloc[0] if not contacts_df[contacts_df["Name"] == selected_saved].empty else None
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
    if street_filter:
        df_filtered = df_filtered[df_filtered["Street No"].str.contains(street_filter, case=False, na=False)]
    if plot_no_filter:
        df_filtered = df_filtered[df_filtered["Plot No"].str.contains(plot_no_filter, case=False, na=False)]
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
    
    # Count WhatsApp eligible listings
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
    
    # Format the Extracted Contact column with dialer links
    display_df = df_filtered.copy()
    if "Extracted Contact" in display_df.columns:
        display_df["Extracted Contact"] = display_df["Extracted Contact"].apply(format_contact_column)
    
    # Row selection and deletion feature for main table
    if not df_filtered.empty:
        display_df = display_df.reset_index(drop=True)
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
            
            # Format the Extracted Contact column with dialer links for duplicates
            duplicates_display = duplicates_df.copy()
            if "Extracted Contact" in duplicates_display.columns:
                duplicates_display["Extracted Contact"] = duplicates_display["Extracted Contact"].apply(format_contact_column)
            
            # Display the styled DataFrame (color-coded)
            st.dataframe(
                duplicates_display,
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
            contact_row = contacts_df[contacts_df["Name"] == selected_name_whatsapp]
            if not contact_row.empty:
                row = contact_row.iloc[0]
                numbers = []
                for col in ["Contact1", "Contact2", "Contact3"]:
                    if col in row and pd.notna(row[col]):
                        numbers.append(clean_number(row[col]))
                cleaned = numbers[0] if numbers else ""

        if not cleaned:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
            return

        if len(cleaned) == 10 and cleaned.startswith("3"):
            wa_number = "92" + cleaned
        elif len(cleaned) == 11 and cleaned.startswith("03"):
            wa_number = "92" + cleaned[1:]
        elif len(cleaned) == 12 and cleaned.startswith("92"):
            wa_number = cleaned
        else:
            st.error("❌ Invalid number. Use 0300xxxxxxx format or select from contact.")
            return

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
                st.markdown("---")# --- Main App ---
def main():
    st.title("🏡 Al-Jazeera Real Estate CRM")
    
    # Navigation
    page = st.sidebar.selectbox("Navigate", ["Plots", "Leads"])
    
    if page == "Plots":
        plots_page()
    else:
        leads_page()

if __name__ == "__main__":
    main()
