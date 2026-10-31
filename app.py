import streamlit as st
import pandas as pd
from datetime import datetime
import re

st.set_page_config(page_title="Business Clarity Workshop - Attendance Matrix", layout="wide")

st.title("Workshop Engagement & Clustering Data Prep")

default_exclude_list = [
    "ashutosh.goenka123@gmail.com",
    "bewithruchi@gmail.com",
    "ruchigoenka1@gmail.com"
]
default_exclude_str = "\n".join(default_exclude_list)

col1, col2, col3 = st.columns(3)
with col1:
    uploaded_files = st.file_uploader("Upload Zoom Data", type=['csv', 'xlsx'], accept_multiple_files=True)
with col2:
    official_start_time = st.time_input("Official Start Time (Applies to all)", value=pd.to_datetime("10:30").time())
with col3:
    exclude_emails_input = st.text_area(
        "Emails to Exclude (comma or line separated)", 
        value=default_exclude_str,
        placeholder="host@example.com\nadmin@example.com"
    )

def align_headers(df):
    cols_str = df.columns.astype(str).str.lower()
    if any('join' in c for c in cols_str) and any('time' in c for c in cols_str):
        return df
    
    for i, row in df.head(15).iterrows():
        row_str = row.astype(str).str.lower()
        if any('join' in val and 'time' in val for val in row_str):
            df.columns = row.tolist()
            return df.iloc[i+1:].reset_index(drop=True)
            
    return df

def calc_max_simultaneous(group_df, join_col, leave_col):
    """Calculates peak concurrent overlapping sessions for a single user."""
    events = []
    for _, row in group_df.iterrows():
        events.append((row[join_col], 1))
        events.append((row[leave_col], -1))
        
    events.sort(key=lambda x: (x[0], x[1]))
    
    current_logins = 0
    max_logins = 0
    for time, event_type in events:
        current_logins += event_type
        if current_logins > max_logins:
            max_logins = current_logins
            
    return max_logins

if uploaded_files:
    try:
        exclude_list = []
        if exclude_emails_input:
            exclude_list = [e.strip().lower() for e in re.split(r'[,\n]+', exclude_emails_input) if e.strip()]

        all_data = []
        
        for uploaded_file in uploaded_files:
            if uploaded_file.name.endswith('.csv'):
                # Added index_col=False to stop Pandas from shifting Zoom's trailing comma rows
                df = pd.read_csv(uploaded_file, index_col=False) 
            elif uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                continue
            
            df = align_headers(df)
            df.columns = df.columns.astype(str).str.strip().str.lower()
            
            name_col = next((col for col in df.columns if 'name' in col), None)
            email_col = next((col for col in df.columns if 'email' in col), None)
            join_col = next((col for col in df.columns if 'join' in col and 'time' in col), None)
            leave_col = next((col for col in df.columns if 'leave' in col and 'time' in col), None)
            
            if not join_col: join_col = next((col for col in df.columns if 'join' in col), None)
            if not leave_col: leave_col = next((col for col in df.columns if 'leave' in col), None)
            
            if not all([name_col, join_col, leave_col]):
                st.warning(f"File '{uploaded_file.name}' is missing standard Zoom columns. Skipping.")
                continue
                
            df[name_col] = df[name_col].astype(str).str.strip().str.title()
            if email_col:
                df[email_col] = df[email_col].astype(str).str.strip().str.lower()
            
            if email_col and exclude_list:
                df = df[~df[email_col].isin(exclude_list)]
            
            df[join_col] = pd.to_datetime(df[join_col], errors='coerce')
            df[leave_col] = pd.to_datetime(df[leave_col], errors='coerce')
            df = df.dropna(subset=[join_col, leave_col])
            
            if df.empty:
                continue
                
            df['Session Duration Mins'] = (df[leave_col] - df[join_col]).dt.total_seconds() / 60
            group_cols = [name_col, email_col] if email_col else [name_col]
            
            summary = df.groupby(group_cols).agg(
                first_join=(join_col, 'min'),
                last_leave=(leave_col, 'max'),
                actual_duration_mins=('Session Duration Mins', 'sum')
            ).reset_index()
            
            concurrency_df = df.groupby(group_cols).apply(
                lambda g: calc_max_simultaneous(g, join_col, leave_col)
            ).reset_index(name='max_simultaneous_logins')
            
            summary = pd.merge(summary, concurrency_df, on=group_cols)
            
            summary.rename(columns={name_col: 'User Name'}, inplace=True)
            if email_col:
                summary.rename(columns={email_col: 'User Email'}, inplace=True)
            
            summary['Workshop Date'] = summary['first_join'].dt.date
            summary['total_span_mins'] = (summary['last_leave'] - summary['first_join']).dt.total_seconds() / 60
            summary['time_away_mins'] = (summary['total_span_mins'] - summary['actual_duration_mins']).round(2).clip(lower=0)
            
            date_str = summary['Workshop Date'].astype(str)
            time_str = official_start_time.strftime("%H:%M:%S")
            summary['official_start_dt'] = pd.to_datetime(date_str + " " + time_str)
            
            summary['minutes_late'] = (summary['first_join'] - summary['official_start_dt']).dt.total_seconds() / 60
            summary['minutes_late'] = summary['minutes_late'].round(2)
            
            def categorize_arrival(mins):
                if mins < -5: return "Early"
                elif mins <= 5: return "On Time"
                else: return "Late"
                
            summary['arrival_category'] = summary['minutes_late'].apply(categorize_arrival)
            summary = summary.drop(columns=['official_start_dt'])
            all_data.append(summary)
            
        if all_data:
            final_matrix = pd.concat(all_data, ignore_index=True)
            
            cols = final_matrix.columns.tolist()
            if 'Workshop Date' in cols:
                insert_idx = 2 if 'User Email' in cols else 1
                cols.insert(insert_idx, cols.pop(cols.index('Workshop Date')))
                final_matrix = final_matrix[cols]
            
            st.subheader("Processed Participant Matrix")
            st.dataframe(final_matrix, use_container_width=True)
            
            csv_export = final_matrix.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Master Data for Clustering",
                data=csv_export,
                file_name="master_workshop_clustering_matrix.csv",
                mime="text/csv",
            )
        else:
            st.warning("No valid data found after applying exclusions.")
            
    except Exception as e:
        st.error(f"Error processing files. Details: {e}")
